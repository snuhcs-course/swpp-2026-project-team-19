"""The phone customers see when a bar has none: its owner's contact phone, only with their consent
(API spec 3.9, 3.6, 3.11.2; migration 3a8f2d6c1e97).

The bar's own phone always comes first. The contact phone is read through the bar's current owner, so a
removed owner's number, and the number of an application that was never approved, are never shown.
"""

import os
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.api import deps
from app.main import app
from app.models import BarOwnerApplication, OwnerApplicationStatus, UserType
from app.services.business_check import RecentBusinessChecks
from app.services.request_limits import InMemoryDailyLimiter
from tests.conftest import BACKEND_DIR
from tests.factories import make_application, make_bar, make_owner, make_user
from tests.sql_support import recorded_statements

OWNER_SUBJECT = "owner-subject"
OPERATOR_SUBJECT = "operator-subject"
BAR_PHONE = "02-000-0000"
CONTACT = "010-1234-5678"


@pytest.fixture
def operator(db_session):
    return make_user(db_session, OPERATOR_SUBJECT, user_type=UserType.OPERATOR)


@pytest.fixture
def owner_user(db_session):
    return make_user(db_session, OWNER_SUBJECT)


def bearer(supabase, subject: str) -> dict:
    return {"Authorization": f"Bearer {supabase.token(sub=subject)}"}


def no_phone_bar(db_session, name: str = "번호 없는 바"):
    bar = make_bar(db_session, name)
    bar.phone = None
    db_session.flush()
    return bar


def customer_phone(client, bar) -> tuple[str | None, str | None]:
    """`phone` and `phoneSource` of the public bar menu (3.9), read without a token."""
    body = client.get(f"/api/bars/{bar.id}/menu").json()
    return body["phone"], body["phoneSource"]


def managed_phones(client, headers, bar) -> tuple[str | None, str | None, str | None]:
    """`phone`, `customerPhone` and `customerPhoneSource` of the bar detail (3.6)."""
    body = client.get(f"/api/bars/{bar.id}", headers=headers).json()
    return body["phone"], body["customerPhone"], body["customerPhoneSource"]


# ---- the customer bar menu (3.9) ----


def test_a_consented_contact_phone_is_shown_when_the_bar_has_no_phone(client, db_session, owner_user, operator):
    bar = no_phone_bar(db_session)
    make_owner(db_session, owner_user, bar, operator, contact_phone=CONTACT, contact_phone_public=True)

    assert customer_phone(client, bar) == (CONTACT, "owner_contact")


def test_without_consent_the_contact_phone_is_not_shown(client, db_session, owner_user, operator):
    bar = no_phone_bar(db_session)
    make_owner(db_session, owner_user, bar, operator, contact_phone=CONTACT, contact_phone_public=False)

    assert customer_phone(client, bar) == (None, None)


@pytest.mark.parametrize("consented", [True, False])
def test_the_bar_phone_comes_first_whatever_the_consent(client, db_session, owner_user, operator, consented):
    bar = make_bar(db_session)
    make_owner(db_session, owner_user, bar, operator, contact_phone=CONTACT, contact_phone_public=consented)

    assert customer_phone(client, bar) == (BAR_PHONE, "bar")


def test_a_bar_phone_without_an_owner_is_from_the_bar(client, db_session):
    assert customer_phone(client, make_bar(db_session)) == (BAR_PHONE, "bar")


def test_a_blank_bar_phone_counts_as_none(client, db_session, owner_user, operator):
    bar = make_bar(db_session)
    bar.phone = ""
    make_owner(db_session, owner_user, bar, operator, contact_phone=CONTACT, contact_phone_public=True)

    assert customer_phone(client, bar) == (CONTACT, "owner_contact")


def test_the_phone_disappears_when_the_owner_is_removed(client, db_session, supabase, owner_user, operator):
    bar = no_phone_bar(db_session)
    make_owner(db_session, owner_user, bar, operator, contact_phone=CONTACT, contact_phone_public=True)
    assert customer_phone(client, bar) == (CONTACT, "owner_contact")

    response = client.delete(f"/api/bars/{bar.id}/owner", headers=bearer(supabase, OPERATOR_SUBJECT))

    assert response.status_code == 204, response.text
    assert customer_phone(client, bar) == (None, None)


@pytest.mark.parametrize(("consented", "expected"), [(True, ("010-9999-8888", "owner_contact")), (False, (None, None))])
def test_a_new_owner_uses_only_their_own_consent(client, db_session, owner_user, operator, consented, expected):
    bar = no_phone_bar(db_session)
    former = make_owner(db_session, owner_user, bar, operator, contact_phone=CONTACT, contact_phone_public=True)
    former.revoked_at, former.revoked_by_user_id = former.created_at, operator.id
    db_session.flush()
    successor = make_user(db_session, "successor-subject")

    make_owner(db_session, successor, bar, operator, contact_phone="010-9999-8888", contact_phone_public=consented)

    assert customer_phone(client, bar) == expected


@pytest.mark.parametrize(
    "status", [OwnerApplicationStatus.PENDING, OwnerApplicationStatus.REJECTED, OwnerApplicationStatus.CANCELED]
)
def test_an_application_not_approved_is_never_shown(client, db_session, owner_user, operator, status):
    bar = no_phone_bar(db_session)
    make_application(
        db_session,
        owner_user,
        bar,
        status=status,
        reviewer=operator,
        contact_phone=CONTACT,
        contact_phone_public=True,
    )

    assert customer_phone(client, bar) == (None, None)


def test_a_pending_consent_of_someone_else_does_not_replace_the_owners_choice(
    client, db_session, owner_user, operator
):
    bar = no_phone_bar(db_session)
    make_owner(db_session, owner_user, bar, operator, contact_phone=CONTACT, contact_phone_public=False)
    make_application(
        db_session, make_user(db_session, "other-subject"), bar, contact_phone="010-5555-6666", contact_phone_public=True
    )

    assert customer_phone(client, bar) == (None, None)


def test_each_bar_of_an_owner_follows_the_application_that_won_it(client, db_session, owner_user, operator):
    shown, hidden = no_phone_bar(db_session, "A 바"), no_phone_bar(db_session, "B 바")
    make_owner(db_session, owner_user, shown, operator, contact_phone=CONTACT, contact_phone_public=True)
    make_owner(db_session, owner_user, hidden, operator, contact_phone=CONTACT, contact_phone_public=False)

    assert customer_phone(client, shown) == (CONTACT, "owner_contact")
    assert customer_phone(client, hidden) == (None, None)


def test_a_bar_with_its_own_phone_costs_no_owner_query(client, db_session, owner_user, operator):
    bar = make_bar(db_session)
    make_owner(db_session, owner_user, bar, operator, contact_phone_public=True)

    with recorded_statements(db_session) as statements:
        assert client.get(f"/api/bars/{bar.id}/menu").status_code == 200

    assert [sql for sql in statements if "bar_owner" in sql] == []


# ---- what the bar's managers see (3.6, 3.7, 3.11.9) ----


def test_the_owner_sees_the_phone_customers_see(client, db_session, supabase, owner_user, operator):
    bar = no_phone_bar(db_session)
    make_owner(db_session, owner_user, bar, operator, contact_phone=CONTACT, contact_phone_public=True)

    # `phone` stays the bar's own phone, which the edit form sends back; the contact phone is not copied into it.
    assert managed_phones(client, bearer(supabase, OWNER_SUBJECT), bar) == (None, CONTACT, "owner_contact")
    assert managed_phones(client, bearer(supabase, OPERATOR_SUBJECT), bar) == (None, CONTACT, "owner_contact")
    [mine] = client.get("/api/me/bars", headers=bearer(supabase, OWNER_SUBJECT)).json()["items"]
    assert (mine["phone"], mine["customerPhone"], mine["customerPhoneSource"]) == (None, CONTACT, "owner_contact")


def test_without_consent_the_owner_sees_that_customers_get_no_phone(client, db_session, supabase, owner_user, operator):
    bar = no_phone_bar(db_session)
    make_owner(db_session, owner_user, bar, operator, contact_phone=CONTACT, contact_phone_public=False)

    assert managed_phones(client, bearer(supabase, OWNER_SUBJECT), bar) == (None, None, None)


def test_a_bar_phone_the_owner_enters_replaces_the_contact_phone(client, db_session, supabase, owner_user, operator):
    bar = no_phone_bar(db_session)
    make_owner(db_session, owner_user, bar, operator, contact_phone=CONTACT, contact_phone_public=True)
    headers = bearer(supabase, OWNER_SUBJECT)

    response = client.patch(f"/api/bars/{bar.id}", headers=headers, json={"phone": "02-111-2222"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["phone"], body["customerPhone"], body["customerPhoneSource"]) == ("02-111-2222", "02-111-2222", "bar")
    assert customer_phone(client, bar) == ("02-111-2222", "bar")

    # Removing the bar phone again brings back the consented contact phone.
    response = client.patch(f"/api/bars/{bar.id}", headers=headers, json={"phone": None})

    assert (response.json()["phone"], response.json()["customerPhone"]) == (None, CONTACT)
    assert customer_phone(client, bar) == (CONTACT, "owner_contact")


# ---- the consent in the application (3.11.2) ----


@pytest.fixture
def applying():
    """No NTS key, so applications are stored as `unavailable` without calling anything."""
    app.dependency_overrides[deps.get_business_verifier] = lambda: None
    limiter = InMemoryDailyLimiter()
    app.dependency_overrides[deps.get_request_limiter] = lambda: limiter
    recent = RecentBusinessChecks()
    app.dependency_overrides[deps.get_recent_business_checks] = lambda: recent
    yield
    for dependency in (deps.get_business_verifier, deps.get_request_limiter, deps.get_recent_business_checks):
        app.dependency_overrides.pop(dependency, None)


def application_body(bar, **changes) -> dict:
    body = {
        "applicationType": "existing_bar",
        "barId": str(bar.id),
        "businessRegistrationNumber": "123-45-67891",
        "representativeName": "김사장",
        "openingDate": "2020-03-02",
        "contactPhone": CONTACT,
    }
    return body | changes


def test_consent_given_when_applying_shows_the_phone_after_approval(
    client, db_session, supabase, owner_user, operator, applying
):
    bar = no_phone_bar(db_session)

    response = client.post(
        "/api/owner-applications",
        headers=bearer(supabase, OWNER_SUBJECT),
        json=application_body(bar, contactPhonePublic=True),
    )

    assert response.status_code == 201, response.text
    application_id = response.json()["applicationId"]
    assert response.json()["contactPhonePublic"] is True
    assert db_session.get(BarOwnerApplication, UUID(application_id)).contact_phone_public is True
    # Not shown while the application waits.
    assert customer_phone(client, bar) == (None, None)
    detail = client.get(f"/api/owner-applications/{application_id}", headers=bearer(supabase, OPERATOR_SUBJECT))
    assert detail.json()["contactPhonePublic"] is True

    approved = client.post(
        f"/api/owner-applications/{application_id}/approve", headers=bearer(supabase, OPERATOR_SUBJECT)
    )

    assert approved.status_code == 200, approved.text
    assert customer_phone(client, bar) == (CONTACT, "owner_contact")


def test_a_new_bar_application_carries_the_consent(client, db_session, supabase, owner_user, applying):
    body = application_body(make_bar(db_session), contactPhonePublic=True)
    del body["barId"]
    body |= {"applicationType": "new_bar", "proposedBar": {"name": "신림 몰트 하우스", "address": "서울 관악구 신림로 2"}}

    response = client.post("/api/owner-applications", headers=bearer(supabase, OWNER_SUBJECT), json=body)

    assert response.status_code == 201, response.text
    assert response.json()["contactPhonePublic"] is True


def test_consent_left_out_is_no_consent(client, db_session, supabase, owner_user, applying):
    response = client.post(
        "/api/owner-applications", headers=bearer(supabase, OWNER_SUBJECT), json=application_body(make_bar(db_session))
    )

    assert response.status_code == 201, response.text
    assert response.json()["contactPhonePublic"] is False
    assert db_session.get(BarOwnerApplication, UUID(response.json()["applicationId"])).contact_phone_public is False


@pytest.mark.parametrize("value", ["true", 1, 0, None, "yes", [], {}])
def test_consent_must_be_a_json_boolean(client, db_session, supabase, owner_user, applying, value):
    response = client.post(
        "/api/owner-applications",
        headers=bearer(supabase, OWNER_SUBJECT),
        json=application_body(make_bar(db_session), contactPhonePublic=value),
    )

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert [(e["path"], e["code"]) for e in error["fieldErrors"]] == [("contactPhonePublic", "BOOL_TYPE")]
    assert db_session.query(BarOwnerApplication).count() == 0


# ---- the migration (3a8f2d6c1e97) ----

BEFORE = "7d1e4b9a2c63"


@pytest.fixture
def migrations(monkeypatch):
    monkeypatch.setenv("POSTGRES_DATABASE", os.environ["POSTGRES_TEST_DATABASE"])
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    try:
        yield config
    finally:
        command.upgrade(config, "head")


def test_applications_made_before_the_migration_get_no_consent(db_engine, migrations):
    command.downgrade(migrations, BEFORE)
    try:
        with db_engine.begin() as conn:
            user_id = conn.scalar(
                text("INSERT INTO users (id, auth_subject, user_type) VALUES (gen_random_uuid(), 'migration-subject', "
                     "'customer') RETURNING id")
            )
            conn.execute(
                text(
                    "INSERT INTO bar_owner_applications (id, applicant_user_id, application_type, proposed_bar_name,"
                    " proposed_address, business_registration_number_ciphertext, business_registration_number_hmac,"
                    " representative_name, opening_date, business_verification_result, business_checked_at,"
                    " contact_phone) VALUES (gen_random_uuid(), :user, 'new_bar', '바', '주소', '\\x00', :hmac,"
                    " '김사장', '2020-03-02', 'unavailable', now(), '010-1234-5678')"
                ),
                {"user": user_id, "hmac": b"\x00" * 32},
            )

        command.upgrade(migrations, "head")

        with db_engine.connect() as conn:
            stored = conn.scalars(
                text("SELECT contact_phone_public FROM bar_owner_applications WHERE applicant_user_id = :user"),
                {"user": user_id},
            ).all()
            column = conn.execute(
                text(
                    "SELECT is_nullable, column_default FROM information_schema.columns "
                    "WHERE table_name = 'bar_owner_applications' AND column_name = 'contact_phone_public'"
                )
            ).one()
        assert stored == [False]
        assert tuple(column) == ("NO", "false")

        command.downgrade(migrations, BEFORE)
        with db_engine.connect() as conn:
            columns = set(
                conn.scalars(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'bar_owner_applications'"
                    )
                )
            )
        assert "contact_phone_public" not in columns
    finally:
        command.upgrade(migrations, "head")
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM bar_owner_applications WHERE applicant_user_id IN "
                    "(SELECT id FROM users WHERE auth_subject = 'migration-subject')"
                )
            )
            conn.execute(text("DELETE FROM users WHERE auth_subject = 'migration-subject'"))
