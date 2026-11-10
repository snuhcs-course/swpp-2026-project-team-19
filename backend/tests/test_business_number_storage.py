"""Business registration numbers are stored encrypted, with a lookup value (migration bec46a7503af).

The migration tests move the test database's schema down one revision and back up, with committed rows,
so they use their own connections instead of `db_session`, and always leave the schema at head.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.business_number_crypto import ENCRYPTION_KEYS_ENV, HMAC_KEY_ENV, get_business_number_cipher
from app.models import BarOwnerApplication, User
from tests.crypto_support import TEST_BUSINESS_NUMBER_ENCRYPTION_KEY, TEST_BUSINESS_NUMBER_HMAC_KEY
from tests.factories import make_application, make_user

BACKEND_DIR = Path(__file__).resolve().parents[1]
BEFORE = "9c2e7a4b1d38"
NUMBER = "1234567891"
OTHER_NUMBER = "1234567800"
SUBJECT = "business-number-migration"


def test_a_stored_number_is_neither_plaintext_nor_unreadable(db_session):
    application = make_application(db_session, make_user(db_session), business_registration_number=NUMBER)

    token, lookup = db_session.execute(
        text(
            "SELECT business_registration_number_ciphertext, business_registration_number_hmac "
            "FROM bar_owner_applications WHERE id = :id"
        ),
        {"id": application.id},
    ).one()

    assert NUMBER.encode() not in bytes(token)
    assert get_business_number_cipher().decrypt(token) == NUMBER
    assert bytes(lookup) == get_business_number_cipher().lookup(NUMBER)
    db_session.expire(application)
    assert application.business_registration_number == NUMBER


def test_changing_the_number_changes_both_values(db_session):
    application = make_application(db_session, make_user(db_session), business_registration_number=NUMBER)
    lookup = application.business_registration_number_hmac

    application.business_registration_number = OTHER_NUMBER
    db_session.flush()

    assert application.business_registration_number == OTHER_NUMBER
    assert application.business_registration_number_hmac != lookup
    assert application.business_registration_number_hmac == get_business_number_cipher().lookup(OTHER_NUMBER)


def test_a_number_is_found_by_its_lookup_value(db_session):
    applicant = make_user(db_session)
    first = make_application(db_session, applicant, business_registration_number=NUMBER)
    make_application(db_session, make_user(db_session, "other-subject"), business_registration_number=OTHER_NUMBER)

    found = db_session.scalars(
        select(BarOwnerApplication.id).where(
            BarOwnerApplication.business_registration_number_hmac == get_business_number_cipher().lookup(NUMBER)
        )
    ).all()

    assert found == [first.id]


@pytest.fixture
def migrations(db_engine, monkeypatch):
    """Move the test database between revisions; the schema is back at head and the rows gone afterwards."""
    monkeypatch.setenv("POSTGRES_DATABASE", os.environ["POSTGRES_TEST_DATABASE"])
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    with Session(db_engine) as session:
        user_id = make_user(session, SUBJECT).id
        session.commit()

    class Migrations:
        applicant_id = user_id

        def down(self) -> None:
            command.downgrade(config, BEFORE)

        def up(self) -> None:
            command.upgrade(config, "head")

    try:
        yield Migrations()
    finally:
        # Put the keys back first: a test may have removed them, and rows may be left to convert.
        monkeypatch.setenv(ENCRYPTION_KEYS_ENV, TEST_BUSINESS_NUMBER_ENCRYPTION_KEY)
        monkeypatch.setenv(HMAC_KEY_ENV, TEST_BUSINESS_NUMBER_HMAC_KEY)
        command.upgrade(config, "head")
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM bar_owner_applications WHERE applicant_user_id = :id"), {"id": user_id})
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


def insert_plaintext(db_engine, applicant_id, number: str, status: str = "pending") -> None:
    """A new_bar application in the schema before the migration."""
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO bar_owner_applications (id, applicant_user_id, application_type, proposed_bar_name, "
                "proposed_address, business_registration_number, representative_name, opening_date, "
                "business_verification_result, business_checked_at, contact_phone, status) VALUES "
                "(gen_random_uuid(), :applicant, 'new_bar', 'New Bar', 'New Bar address', :number, '김사장', "
                "'2020-03-02', 'unavailable', now(), '010-1234-5678', :status)"
            ),
            {"applicant": applicant_id, "number": number, "status": status},
        )


def columns(db_engine) -> set[str]:
    with db_engine.connect() as conn:
        return set(
            conn.scalars(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'bar_owner_applications'")
            )
        )


def test_the_migration_encrypts_existing_numbers(db_engine, migrations):
    migrations.down()
    insert_plaintext(db_engine, migrations.applicant_id, NUMBER)
    insert_plaintext(db_engine, migrations.applicant_id, NUMBER, status="canceled")
    insert_plaintext(db_engine, migrations.applicant_id, OTHER_NUMBER, status="canceled")

    migrations.up()

    assert "business_registration_number" not in columns(db_engine)
    cipher = get_business_number_cipher()
    with Session(db_engine) as session:
        applications = session.scalars(
            select(BarOwnerApplication).where(BarOwnerApplication.applicant_user_id == migrations.applicant_id)
        ).all()
        assert sorted(a.business_registration_number for a in applications) == [OTHER_NUMBER, NUMBER, NUMBER]
        for application in applications:
            number = application.business_registration_number
            assert number.encode() not in application.business_registration_number_ciphertext
            assert application.business_registration_number_hmac == cipher.lookup(number)


def test_the_migrated_index_still_keeps_one_pending_new_bar_application(db_engine, migrations):
    migrations.down()
    insert_plaintext(db_engine, migrations.applicant_id, NUMBER)
    migrations.up()

    with db_engine.connect() as conn:
        definition = conn.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_bar_owner_applications_pending_new_bar'")
        )
    assert "business_registration_number_hmac" in definition
    with Session(db_engine) as session:
        user = session.get(User, migrations.applicant_id)
        with pytest.raises(IntegrityError, match="uq_bar_owner_applications_pending_new_bar"):
            make_application(session, user, business_registration_number=NUMBER)
        session.rollback()


def test_the_downgrade_decrypts_the_numbers(db_engine, migrations):
    with Session(db_engine) as session:
        make_application(session, session.get(User, migrations.applicant_id), business_registration_number=NUMBER)
        session.commit()

    migrations.down()

    with db_engine.connect() as conn:
        stored = conn.scalars(
            text("SELECT business_registration_number FROM bar_owner_applications WHERE applicant_user_id = :id"),
            {"id": migrations.applicant_id},
        ).all()
    assert stored == [NUMBER]


def test_rows_cannot_be_migrated_without_the_keys(db_engine, migrations, monkeypatch):
    migrations.down()
    insert_plaintext(db_engine, migrations.applicant_id, NUMBER)
    monkeypatch.delenv(ENCRYPTION_KEYS_ENV)

    with pytest.raises(RuntimeError, match=ENCRYPTION_KEYS_ENV):
        migrations.up()

    # The whole migration was rolled back: the plaintext is still there, at the old revision.
    assert "business_registration_number" in columns(db_engine)
    assert "business_registration_number_ciphertext" not in columns(db_engine)
    with db_engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == BEFORE


def test_an_empty_table_migrates_without_the_keys(db_engine, migrations, monkeypatch):
    with db_engine.connect() as conn:
        if conn.scalar(text("SELECT count(*) FROM bar_owner_applications")):
            pytest.fail("bar_owner_applications should be empty between tests")
    monkeypatch.delenv(ENCRYPTION_KEYS_ENV)
    monkeypatch.delenv(HMAC_KEY_ENV)

    migrations.down()
    migrations.up()

    assert "business_registration_number_hmac" in columns(db_engine)
