"""create bar owner tables

Revision ID: f9c1f2752a77
Revises: a753618f55f5
Create Date: 2026-10-28 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f9c1f2752a77'
down_revision: Union[str, None] = 'a753618f55f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUMS = {
    "owner_application_type": ("existing_bar", "new_bar"),
    "owner_application_status": ("pending", "approved", "rejected", "canceled"),
    "business_verification_result": ("matched", "not_matched", "unavailable"),
    "business_status": ("active", "suspended", "closed"),
}


def enum(name: str) -> postgresql.ENUM:
    # Types are created once in upgrade().
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def timestamp(name: str, *, nullable: bool = False, default_now: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()") if default_now else None,
        nullable=nullable,
    )


def uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=False)

    op.create_table(
        "bar_owner_applications",
        uuid("id"),
        uuid("applicant_user_id"),
        sa.Column("application_type", enum("owner_application_type"), nullable=False),
        uuid("bar_id", nullable=True),
        sa.Column("proposed_bar_name", sa.String(length=150), nullable=True),
        sa.Column("proposed_address", sa.String(length=500), nullable=True),
        sa.Column("proposed_phone", sa.String(length=30), nullable=True),
        sa.Column("business_registration_number", sa.CHAR(length=10), nullable=False),
        sa.Column("representative_name", sa.String(length=100), nullable=False),
        sa.Column("opening_date", sa.Date(), nullable=False),
        sa.Column("business_verification_result", enum("business_verification_result"), nullable=False),
        sa.Column("business_status", enum("business_status"), nullable=True),
        timestamp("business_checked_at"),
        sa.Column("contact_phone", sa.String(length=30), nullable=False),
        sa.Column("applicant_note", sa.String(length=500), nullable=True),
        sa.Column(
            "status", enum("owner_application_status"), server_default=sa.text("'pending'"), nullable=False
        ),
        uuid("reviewed_by_user_id", nullable=True),
        timestamp("reviewed_at", nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        timestamp("created_at", default_now=True),
        timestamp("updated_at", default_now=True),
        sa.CheckConstraint(
            "(application_type = 'existing_bar' AND bar_id IS NOT NULL AND proposed_bar_name IS NULL"
            " AND proposed_address IS NULL AND proposed_phone IS NULL)"
            " OR (application_type = 'new_bar' AND proposed_bar_name IS NOT NULL AND proposed_address IS NOT NULL"
            " AND (bar_id IS NOT NULL) = (status = 'approved'))",
            name="ck_bar_owner_applications_type_fields",
        ),
        sa.CheckConstraint(
            "business_registration_number ~ '^[0-9]{10}$'",
            name="ck_bar_owner_applications_business_registration_number",
        ),
        sa.CheckConstraint(
            "(rejection_reason IS NOT NULL) = (status = 'rejected')",
            name="ck_bar_owner_applications_rejection_reason",
        ),
        sa.CheckConstraint(
            "(reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL) = (status IN ('approved', 'rejected'))"
            " AND (reviewed_by_user_id IS NULL) = (reviewed_at IS NULL)",
            name="ck_bar_owner_applications_review",
        ),
        sa.CheckConstraint(
            "business_status IS NULL OR business_verification_result = 'matched'",
            name="ck_bar_owner_applications_business_status",
        ),
        sa.ForeignKeyConstraint(["applicant_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["bar_id"], ["bars.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bar_owner_applications_status_created_at", "bar_owner_applications", ["status", "created_at"]
    )
    op.create_index(
        "ix_bar_owner_applications_applicant_user_id_created_at",
        "bar_owner_applications",
        ["applicant_user_id", "created_at"],
    )
    op.create_index("ix_bar_owner_applications_bar_id", "bar_owner_applications", ["bar_id"])
    op.create_index(
        "uq_bar_owner_applications_pending_existing_bar",
        "bar_owner_applications",
        ["applicant_user_id", "bar_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND application_type = 'existing_bar'"),
    )
    op.create_index(
        "uq_bar_owner_applications_pending_new_bar",
        "bar_owner_applications",
        ["applicant_user_id", "business_registration_number"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND application_type = 'new_bar'"),
    )

    op.create_table(
        "bar_owners",
        uuid("id"),
        uuid("bar_id"),
        uuid("user_id"),
        uuid("application_id"),
        timestamp("created_at", default_now=True),
        timestamp("revoked_at", nullable=True),
        uuid("revoked_by_user_id", nullable=True),
        sa.CheckConstraint("(revoked_at IS NULL) = (revoked_by_user_id IS NULL)", name="ck_bar_owners_revoked"),
        sa.ForeignKeyConstraint(["bar_id"], ["bars.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["application_id"], ["bar_owner_applications.id"]),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id"),
    )
    op.create_index(
        "uq_bar_owners_current_bar_id",
        "bar_owners",
        ["bar_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index("ix_bar_owners_user_id", "bar_owners", ["user_id"])


def downgrade() -> None:
    op.drop_table("bar_owners")
    op.drop_table("bar_owner_applications")
    bind = op.get_bind()
    for name in ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
