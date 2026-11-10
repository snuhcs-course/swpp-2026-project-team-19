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


def _keys():
    """(MultiFernet of the encryption keys, HMAC key); RuntimeError naming the setting when one is missing."""
    from cryptography.fernet import Fernet, MultiFernet

    raw_keys = os.getenv("BUSINESS_NUMBER_ENCRYPTION_KEYS", "").split(",")
    encryption = [value.strip() for value in raw_keys if value.strip()]
    lookup = os.getenv("BUSINESS_NUMBER_HMAC_KEY", "").strip()
    if not encryption or not lookup:
        raise RuntimeError(
            "BUSINESS_NUMBER_ENCRYPTION_KEYS and BUSINESS_NUMBER_HMAC_KEY must be set to migrate the stored "
            "business registration numbers (see backend/.env.example)"
        )
    lookup_key = base64.urlsafe_b64decode(lookup.encode("ascii"))
    if len(lookup_key) != 32:
        raise RuntimeError("BUSINESS_NUMBER_HMAC_KEY must be base64url of 32 bytes")
    return MultiFernet([Fernet(key) for key in encryption]), lookup_key


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
