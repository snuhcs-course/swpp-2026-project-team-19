"""Encryption of stored business registration numbers, and their lookup values.

A number is stored as two values, each made with its own key from the environment:

- a Fernet token (`cryptography.fernet`: AES-128-CBC with a random IV, then HMAC-SHA256 over the
  whole token), which the server decrypts for the operator screens and the NTS recheck. The same
  number gives a different token each time, so tokens cannot be compared;
- a lookup value, HMAC-SHA256 of the number under a separate key. The same number always gives the
  same value, so pending duplicates and shared numbers are found by comparing it. The key matters: a
  number has only about a billion possible values, so a plain hash could be reversed by trying them.

Keys (both base64url of 32 random bytes, as `Fernet.generate_key()` prints):

- BUSINESS_NUMBER_ENCRYPTION_KEYS: one key, or several separated by commas. The first encrypts; all
  of them decrypt, so a new key can be put first while rows written with the old one are rotated.
- BUSINESS_NUMBER_HMAC_KEY: the lookup key. It must differ from the encryption keys.

The server does not start without valid keys (app.main), and nothing here logs a number or a key.
"""

import base64
import binascii
import hashlib
import hmac
import os
from dataclasses import dataclass, replace
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

ENCRYPTION_KEYS_ENV = "BUSINESS_NUMBER_ENCRYPTION_KEYS"
HMAC_KEY_ENV = "BUSINESS_NUMBER_HMAC_KEY"
# Prefixed to the number, so this key cannot give the same value for another kind of input.
LOOKUP_CONTEXT = b"bottlemap.business_registration_number:"
KEY_BYTES = 32
GENERATE_KEY_COMMAND = (
    'uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
)


class BusinessNumberKeyError(RuntimeError):
    """A key setting is missing or invalid. The message names the setting, never a key value."""


class BusinessNumberDecryptError(RuntimeError):
    """A stored token that none of the keys can read: a lost key, or a changed row."""


@dataclass(frozen=True)
class BusinessNumberCipher:
    fernet: MultiFernet
    hmac_key: bytes
    # The raw encryption keys, newest first; kept only to check a new lookup key against them.
    encryption_keys: tuple[bytes, ...] = ()

    def encrypt(self, number: str) -> bytes:
        """A Fernet token for the 10-digit number, made with the first key."""
        return self.fernet.encrypt(_digits(number).encode("ascii"))

    def decrypt(self, token: bytes) -> str:
        """The number in a token made with any of the keys."""
        try:
            return self.fernet.decrypt(bytes(token)).decode("ascii")
        except InvalidToken:
            raise _undecryptable() from None

    def rotate(self, token: bytes) -> bytes:
        """The same number encrypted again with the first key (for a key change)."""
        try:
            return self.fernet.rotate(bytes(token))
        except InvalidToken:
            raise _undecryptable() from None

    def lookup(self, number: str) -> bytes:
        """The 32-byte lookup value: equal numbers give equal values."""
        return hmac.new(self.hmac_key, LOOKUP_CONTEXT + _digits(number).encode("ascii"), hashlib.sha256).digest()

    def with_lookup_key(self, raw_key: str, setting: str) -> "BusinessNumberCipher":
        """The same encryption keys with a new lookup key (scripts/rotate_business_number_keys.py). `setting`
        names where the key came from, for the error message."""
        key = _decode_key(raw_key.strip(), setting)
        if key == self.hmac_key:
            raise BusinessNumberKeyError(f"{setting} is the current {HMAC_KEY_ENV}; generate a new key")
        if key in self.encryption_keys:
            raise BusinessNumberKeyError(f"{setting} must differ from the keys in {ENCRYPTION_KEYS_ENV}")
        return replace(self, hmac_key=key)


def _undecryptable() -> BusinessNumberDecryptError:
    return BusinessNumberDecryptError("A stored business number cannot be decrypted with the configured keys")


def _digits(number: str) -> str:
    # Callers pass validated numbers (app.core.business_number); anything else is a programming error.
    if len(number) != 10 or not number.isascii() or not number.isdigit():
        raise ValueError("A business registration number is 10 digits")
    return number


def _decode_key(value: str, setting: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(value.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        key = b""
    if len(key) != KEY_BYTES:
        raise BusinessNumberKeyError(
            f"{setting} must be base64url of {KEY_BYTES} random bytes; generate one with: {GENERATE_KEY_COMMAND}"
        )
    return key


def load_business_number_cipher() -> BusinessNumberCipher:
    """The cipher from the environment; BusinessNumberKeyError when a key is missing or invalid."""
    raw_keys = [value.strip() for value in os.getenv(ENCRYPTION_KEYS_ENV, "").split(",") if value.strip()]
    if not raw_keys:
        raise BusinessNumberKeyError(f"{ENCRYPTION_KEYS_ENV} is not set; generate a key with: {GENERATE_KEY_COMMAND}")
    raw_hmac_key = os.getenv(HMAC_KEY_ENV, "").strip()
    if not raw_hmac_key:
        raise BusinessNumberKeyError(f"{HMAC_KEY_ENV} is not set; generate a key with: {GENERATE_KEY_COMMAND}")
    encryption_keys = [_decode_key(value, ENCRYPTION_KEYS_ENV) for value in raw_keys]
    hmac_key = _decode_key(raw_hmac_key, HMAC_KEY_ENV)
    if len(set(encryption_keys)) != len(encryption_keys):
        raise BusinessNumberKeyError(f"{ENCRYPTION_KEYS_ENV} lists the same key twice")
    if hmac_key in encryption_keys:
        raise BusinessNumberKeyError(f"{HMAC_KEY_ENV} must differ from the keys in {ENCRYPTION_KEYS_ENV}")
    return BusinessNumberCipher(
        fernet=MultiFernet([Fernet(base64.urlsafe_b64encode(key)) for key in encryption_keys]),
        hmac_key=hmac_key,
        encryption_keys=tuple(encryption_keys),
    )


@lru_cache(maxsize=1)
def get_business_number_cipher() -> BusinessNumberCipher:
    """The process's cipher, loaded once. The server loads it at start-up, so bad keys stop it there."""
    return load_business_number_cipher()
