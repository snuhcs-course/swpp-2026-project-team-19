"""encrypt the business registration numbers of owner applications

Revision ID: bec46a7503af
Revises: 9c2e7a4b1d38
Create Date: 2026-11-10 12:00:00.000000

The plaintext column becomes a Fernet token and an HMAC-SHA256 lookup value, made with the keys in
BUSINESS_NUMBER_ENCRYPTION_KEYS and BUSINESS_NUMBER_HMAC_KEY. The pending new_bar index compares the
lookup value. Existing rows are converted in the same transaction, so a failure leaves the plaintext
table as it was.

The keys are read only when there are rows to convert: an empty database migrates without them. The
token and lookup formats are written out here instead of imported from app/core/business_number_crypto.py,
so this migration keeps producing the same values if that module changes later.
"""
import base64
import binascii
import hashlib
import hmac
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bec46a7503af'
down_revision: Union[str, None] = '9c2e7a4b1d38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "bar_owner_applications"
LOOKUP_CONTEXT = b"bottlemap.business_registration_number:"
PENDING_NEW_BAR = "status = 'pending' AND application_type = 'new_bar'"


ENCRYPTION_KEYS_ENV = "BUSINESS_NUMBER_ENCRYPTION_KEYS"
HMAC_KEY_ENV = "BUSINESS_NUMBER_HMAC_KEY"
KEY_BYTES = 32
GENERATE_KEY_COMMAND = (
    'uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
)


def _decode_key(value: str, setting: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(value.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        key = b""
    if len(key) != KEY_BYTES:
        raise RuntimeError(
            f"{setting} must be base64url of {KEY_BYTES} random bytes; generate one with: {GENERATE_KEY_COMMAND}"
        )
    return key


def _keys():
    """(MultiFernet of the encryption keys, HMAC key).

    The same checks, in the same order and with the same messages, as load_business_number_cipher() in
    app/core/business_number_crypto.py, so the migration never converts rows with keys the server would then
    refuse to start with (tests/test_business_number_storage.py compares the two). RuntimeError names the
    setting, never a key.
    """
    from cryptography.fernet import Fernet, MultiFernet

    raw_keys = [value.strip() for value in os.getenv(ENCRYPTION_KEYS_ENV, "").split(",") if value.strip()]
    if not raw_keys:
        raise RuntimeError(f"{ENCRYPTION_KEYS_ENV} is not set; generate a key with: {GENERATE_KEY_COMMAND}")
    raw_hmac_key = os.getenv(HMAC_KEY_ENV, "").strip()
    if not raw_hmac_key:
        raise RuntimeError(f"{HMAC_KEY_ENV} is not set; generate a key with: {GENERATE_KEY_COMMAND}")
    encryption_keys = [_decode_key(value, ENCRYPTION_KEYS_ENV) for value in raw_keys]
    hmac_key = _decode_key(raw_hmac_key, HMAC_KEY_ENV)
    if len(set(encryption_keys)) != len(encryption_keys):
        raise RuntimeError(f"{ENCRYPTION_KEYS_ENV} lists the same key twice")
    if hmac_key in encryption_keys:
        raise RuntimeError(f"{HMAC_KEY_ENV} must differ from the keys in {ENCRYPTION_KEYS_ENV}")
    return MultiFernet([Fernet(base64.urlsafe_b64encode(key)) for key in encryption_keys]), hmac_key


def _lookup(key: bytes, number: str) -> bytes:
    return hmac.new(key, LOOKUP_CONTEXT + number.encode("ascii"), hashlib.sha256).digest()


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("business_registration_number_ciphertext", sa.LargeBinary(), nullable=True))
    op.add_column(TABLE, sa.Column("business_registration_number_hmac", sa.LargeBinary(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text(f"SELECT id, business_registration_number FROM {TABLE}")).all()
    if rows:
        fernet, lookup_key = _keys()
        for application_id, number in rows:
            conn.execute(
                sa.text(
                    f"UPDATE {TABLE} SET business_registration_number_ciphertext = :token, "
                    "business_registration_number_hmac = :lookup WHERE id = :id"
                ),
                {
                    "token": fernet.encrypt(number.encode("ascii")),
                    "lookup": _lookup(lookup_key, number),
                    "id": application_id,
                },
            )

    op.alter_column(TABLE, "business_registration_number_ciphertext", nullable=False)
    op.alter_column(TABLE, "business_registration_number_hmac", nullable=False)
    op.drop_index("uq_bar_owner_applications_pending_new_bar", table_name=TABLE)
    op.drop_constraint("ck_bar_owner_applications_business_registration_number", TABLE, type_="check")
    op.drop_column(TABLE, "business_registration_number")
    op.create_check_constraint(
        "ck_bar_owner_applications_business_registration_number_hmac",
        TABLE,
        "octet_length(business_registration_number_hmac) = 32",
    )
    op.create_index(
        "uq_bar_owner_applications_pending_new_bar",
        TABLE,
        ["applicant_user_id", "business_registration_number_hmac"],
        unique=True,
        postgresql_where=sa.text(PENDING_NEW_BAR),
    )
    op.create_index(
        "ix_bar_owner_applications_business_registration_number_hmac", TABLE, ["business_registration_number_hmac"]
    )


def downgrade() -> None:
    """Back to the plaintext column; needs the encryption keys when there are rows."""
    op.add_column(TABLE, sa.Column("business_registration_number", sa.CHAR(length=10), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text(f"SELECT id, business_registration_number_ciphertext FROM {TABLE}")).all()
    if rows:
        fernet, _ = _keys()
        for application_id, token in rows:
            conn.execute(
                sa.text(f"UPDATE {TABLE} SET business_registration_number = :number WHERE id = :id"),
                {"number": fernet.decrypt(bytes(token)).decode("ascii"), "id": application_id},
            )

    op.alter_column(TABLE, "business_registration_number", nullable=False)
    op.drop_index("ix_bar_owner_applications_business_registration_number_hmac", table_name=TABLE)
    op.drop_index("uq_bar_owner_applications_pending_new_bar", table_name=TABLE)
    op.drop_constraint("ck_bar_owner_applications_business_registration_number_hmac", TABLE, type_="check")
    op.drop_column(TABLE, "business_registration_number_hmac")
    op.drop_column(TABLE, "business_registration_number_ciphertext")
    op.create_check_constraint(
        "ck_bar_owner_applications_business_registration_number",
        TABLE,
        "business_registration_number ~ '^[0-9]{10}$'",
    )
    op.create_index(
        "uq_bar_owner_applications_pending_new_bar",
        TABLE,
        ["applicant_user_id", "business_registration_number"],
        unique=True,
        postgresql_where=sa.text(PENDING_NEW_BAR),
    )
