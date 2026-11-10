"""Rotating the keys of stored business registration numbers (scripts/rotate_business_number_keys.py)."""

import pytest
from sqlalchemy import select

from app.core.business_number_crypto import (
    ENCRYPTION_KEYS_ENV,
    HMAC_KEY_ENV,
    BusinessNumberDecryptError,
    BusinessNumberKeyError,
    get_business_number_cipher,
    load_business_number_cipher,
)
from app.models import BarOwnerApplication
from scripts.rotate_business_number_keys import NEW_HMAC_KEY_ENV, run
from tests.crypto_support import (
    TEST_BUSINESS_NUMBER_ENCRYPTION_KEY,
    TEST_BUSINESS_NUMBER_HMAC_KEY,
    TEST_BUSINESS_NUMBER_NEXT_HMAC_KEY,
    TEST_BUSINESS_NUMBER_NEXT_KEY,
)
from tests.factories import make_application, make_user

NUMBERS = ("1234567891", "1234567800")
NEW_HMAC_KEY = TEST_BUSINESS_NUMBER_NEXT_HMAC_KEY


@pytest.fixture
def applications(db_session):
    """Two applications stored with the test keys."""
    applicant = make_user(db_session)
    return [make_application(db_session, applicant, business_registration_number=number) for number in NUMBERS]


def use_keys(monkeypatch, encryption_keys: str, hmac_key: str = TEST_BUSINESS_NUMBER_HMAC_KEY) -> None:
    monkeypatch.setenv(ENCRYPTION_KEYS_ENV, encryption_keys)
    monkeypatch.setenv(HMAC_KEY_ENV, hmac_key)
    get_business_number_cipher.cache_clear()


def stored(db_session) -> list[tuple[bytes, bytes]]:
    db_session.expire_all()
    return [
        (bytes(token), bytes(lookup))
        for token, lookup in db_session.execute(
            select(
                BarOwnerApplication.business_registration_number_ciphertext,
                BarOwnerApplication.business_registration_number_hmac,
            ).order_by(BarOwnerApplication.id)
        )
    ]


def test_reencrypting_moves_every_number_to_the_first_key(db_session, applications, monkeypatch):
    before = stored(db_session)
    use_keys(monkeypatch, f"{TEST_BUSINESS_NUMBER_NEXT_KEY},{TEST_BUSINESS_NUMBER_ENCRYPTION_KEY}")

    message = run(db_session, hmac=False, apply=True)

    assert message.startswith("2 numbers re-encrypted")
    after = stored(db_session)
    # The old key is no longer needed, and the lookup values did not change.
    use_keys(monkeypatch, TEST_BUSINESS_NUMBER_NEXT_KEY)
    new_only = get_business_number_cipher()
    assert sorted(new_only.decrypt(token) for token, _ in after) == sorted(NUMBERS)
    assert [lookup for _, lookup in after] == [lookup for _, lookup in before]
    with pytest.raises(BusinessNumberDecryptError):
        new_only.decrypt(before[0][0])


def test_recomputing_lookups_uses_the_new_key(db_session, applications, monkeypatch):
    before = stored(db_session)

    message = run(db_session, hmac=True, apply=True, new_hmac_key=NEW_HMAC_KEY)

    assert message.startswith("2 lookup values recomputed")
    after = stored(db_session)
    assert [token for token, _ in after] == [token for token, _ in before]
    # Once the server uses the new key, numbers are found by their lookup values again.
    use_keys(monkeypatch, TEST_BUSINESS_NUMBER_ENCRYPTION_KEY, NEW_HMAC_KEY)
    cipher = get_business_number_cipher()
    assert sorted(lookup for _, lookup in after) == sorted(cipher.lookup(number) for number in NUMBERS)
    lookup = cipher.lookup(NUMBERS[0])
    found = db_session.scalar(
        select(BarOwnerApplication.id).where(BarOwnerApplication.business_registration_number_hmac == lookup)
    )
    assert found == applications[0].id


@pytest.mark.parametrize("hmac", [False, True])
def test_a_dry_run_changes_nothing(db_session, applications, monkeypatch, hmac):
    use_keys(monkeypatch, f"{TEST_BUSINESS_NUMBER_NEXT_KEY},{TEST_BUSINESS_NUMBER_ENCRYPTION_KEY}")
    before = stored(db_session)

    message = run(db_session, hmac=hmac, apply=False, new_hmac_key=NEW_HMAC_KEY)

    assert message.startswith("dry run: 2 ")
    assert stored(db_session) == before
    # The rows the test made are still there: only the run was rolled back.
    assert db_session.get(BarOwnerApplication, applications[0].id) is not None


@pytest.mark.parametrize(
    ("new_key", "message"),
    [
        pytest.param(None, f"{NEW_HMAC_KEY_ENV} is not set", id="missing"),
        pytest.param("  ", f"{NEW_HMAC_KEY_ENV} is not set", id="blank"),
        pytest.param("not-a-key", NEW_HMAC_KEY_ENV, id="invalid"),
        pytest.param(TEST_BUSINESS_NUMBER_HMAC_KEY, "is the current", id="the current key"),
        pytest.param(TEST_BUSINESS_NUMBER_ENCRYPTION_KEY, "must differ", id="an encryption key"),
    ],
)
def test_the_new_lookup_key_is_checked_before_anything_changes(db_session, applications, new_key, message):
    before = stored(db_session)

    with pytest.raises(BusinessNumberKeyError, match=message) as raised:
        run(db_session, hmac=True, apply=True, new_hmac_key=new_key)

    assert stored(db_session) == before
    assert TEST_BUSINESS_NUMBER_HMAC_KEY not in str(raised.value)


def test_a_row_without_its_key_stops_the_whole_run(db_session, applications, monkeypatch):
    before = stored(db_session)
    # The current key is missing from the list, so no row can be read.
    use_keys(monkeypatch, TEST_BUSINESS_NUMBER_NEXT_KEY)

    with pytest.raises(BusinessNumberDecryptError):
        run(db_session, hmac=False, apply=True)

    # Rolled back as a whole: the rows still hold what the old key reads.
    assert stored(db_session) == before
    use_keys(monkeypatch, TEST_BUSINESS_NUMBER_ENCRYPTION_KEY)
    assert sorted(load_business_number_cipher().decrypt(token) for token, _ in before) == sorted(NUMBERS)
