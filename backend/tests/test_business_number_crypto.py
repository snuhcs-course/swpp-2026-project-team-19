"""Encryption keys and lookup values for stored business registration numbers."""

import pytest
from fastapi.testclient import TestClient

from app.core.business_number_crypto import (
    ENCRYPTION_KEYS_ENV,
    HMAC_KEY_ENV,
    BusinessNumberDecryptError,
    BusinessNumberKeyError,
    get_business_number_cipher,
    load_business_number_cipher,
)
from tests.crypto_support import (
    INVALID_KEY_SETTINGS,
    TEST_BUSINESS_NUMBER_ENCRYPTION_KEY,
    TEST_BUSINESS_NUMBER_HMAC_KEY,
    TEST_BUSINESS_NUMBER_NEXT_KEY,
)

NUMBER = "1234567891"


def cipher_with(monkeypatch, encryption_keys: str, hmac_key: str = TEST_BUSINESS_NUMBER_HMAC_KEY):
    monkeypatch.setenv(ENCRYPTION_KEYS_ENV, encryption_keys)
    monkeypatch.setenv(HMAC_KEY_ENV, hmac_key)
    return load_business_number_cipher()


def test_a_number_comes_back_from_its_token():
    cipher = get_business_number_cipher()

    token = cipher.encrypt(NUMBER)

    assert cipher.decrypt(token) == NUMBER
    assert NUMBER.encode() not in token
    # Stored in bytea, the value is read back as a memoryview.
    assert cipher.decrypt(memoryview(token)) == NUMBER


def test_the_same_number_gives_a_new_token_each_time():
    cipher = get_business_number_cipher()

    assert cipher.encrypt(NUMBER) != cipher.encrypt(NUMBER)


def test_lookup_values_are_equal_only_for_equal_numbers():
    cipher = get_business_number_cipher()

    assert cipher.lookup(NUMBER) == cipher.lookup(NUMBER)
    assert len(cipher.lookup(NUMBER)) == 32
    assert cipher.lookup(NUMBER) != cipher.lookup("1234567800")


def test_lookup_values_depend_on_the_key(monkeypatch):
    current = get_business_number_cipher().lookup(NUMBER)
    other = cipher_with(monkeypatch, TEST_BUSINESS_NUMBER_ENCRYPTION_KEY, hmac_key=TEST_BUSINESS_NUMBER_NEXT_KEY)

    assert other.lookup(NUMBER) != current


@pytest.mark.parametrize("number", ["123456789", "12345678901", "123-45-6789", "１２３４５６７８９１"])
def test_only_ten_digit_numbers_are_accepted(number):
    cipher = get_business_number_cipher()

    with pytest.raises(ValueError):
        cipher.encrypt(number)
    with pytest.raises(ValueError):
        cipher.lookup(number)


def test_a_new_first_key_still_reads_tokens_of_the_old_key(monkeypatch):
    old_token = get_business_number_cipher().encrypt(NUMBER)
    rotated = cipher_with(monkeypatch, f"{TEST_BUSINESS_NUMBER_NEXT_KEY},{TEST_BUSINESS_NUMBER_ENCRYPTION_KEY}")

    assert rotated.decrypt(old_token) == NUMBER
    new_token = rotated.rotate(old_token)
    # The rotated token needs only the new key.
    assert cipher_with(monkeypatch, TEST_BUSINESS_NUMBER_NEXT_KEY).decrypt(new_token) == NUMBER
    # The lookup value does not change with the encryption keys.
    assert rotated.lookup(NUMBER) == get_business_number_cipher().lookup(NUMBER)


def test_a_token_without_its_key_cannot_be_read(monkeypatch):
    token = get_business_number_cipher().encrypt(NUMBER)
    other = cipher_with(monkeypatch, TEST_BUSINESS_NUMBER_NEXT_KEY)

    with pytest.raises(BusinessNumberDecryptError) as raised:
        other.decrypt(token)
    with pytest.raises(BusinessNumberDecryptError):
        other.rotate(token)
    assert NUMBER not in str(raised.value)


def test_a_changed_token_cannot_be_read():
    cipher = get_business_number_cipher()
    token = bytearray(cipher.encrypt(NUMBER))
    token[-5] = ord("A") if token[-5] != ord("A") else ord("B")

    with pytest.raises(BusinessNumberDecryptError):
        cipher.decrypt(bytes(token))


@pytest.mark.parametrize(("encryption_keys", "hmac_key", "message"), INVALID_KEY_SETTINGS)
def test_invalid_keys_are_refused_without_showing_them(monkeypatch, encryption_keys, hmac_key, message):
    with pytest.raises(BusinessNumberKeyError, match=message) as raised:
        cipher_with(monkeypatch, encryption_keys, hmac_key)

    for key in (TEST_BUSINESS_NUMBER_ENCRYPTION_KEY, TEST_BUSINESS_NUMBER_NEXT_KEY, TEST_BUSINESS_NUMBER_HMAC_KEY):
        assert key not in str(raised.value)


def test_spaces_around_keys_are_ignored(monkeypatch):
    current = get_business_number_cipher()
    keys = f" {TEST_BUSINESS_NUMBER_NEXT_KEY} , {TEST_BUSINESS_NUMBER_ENCRYPTION_KEY} ,"
    cipher = cipher_with(monkeypatch, keys, f"  {TEST_BUSINESS_NUMBER_HMAC_KEY} ")

    assert cipher.decrypt(current.encrypt(NUMBER)) == NUMBER
    assert cipher.lookup(NUMBER) == current.lookup(NUMBER)


def test_the_server_does_not_start_without_the_keys(monkeypatch):
    from app.main import app

    monkeypatch.delenv(ENCRYPTION_KEYS_ENV)
    get_business_number_cipher.cache_clear()

    with pytest.raises(BusinessNumberKeyError, match=ENCRYPTION_KEYS_ENV):
        with TestClient(app):
            pass


def test_the_server_starts_with_the_keys():
    from app.main import app

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
