"""Bar owners: a user's application to own a bar, and the ownership an operator grants (spec 3.11).

Ownership is a user-to-bar relationship, not a user type. The tables follow docs/schema_draft.dbml;
the CHECK constraints and partial unique indexes below are the rules of docs/schema_guide.md 5.3 and 5.4.
"""

from datetime import date, datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class OwnerApplicationType(str, Enum):
    EXISTING_BAR = "existing_bar"
    NEW_BAR = "new_bar"


class OwnerApplicationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"


class BusinessVerificationResult(str, Enum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    UNAVAILABLE = "unavailable"


class BusinessStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


def _pg_enum(enum_class: type[Enum], name: str) -> SQLAlchemyEnum:
    """Store enum values (not member names), like the other models."""
    return SQLAlchemyEnum(enum_class, name=name, values_callable=lambda enum: [member.value for member in enum])


class BarOwnerApplication(Base):
    """A user's request to own an existing bar, or to register a new bar and own it."""

    __tablename__ = "bar_owner_applications"
    __table_args__ = (
        # existing_bar names a bar and proposes nothing; new_bar proposes a bar and gets bar_id only on approval.
        CheckConstraint(
            "(application_type = 'existing_bar' AND bar_id IS NOT NULL AND proposed_bar_name IS NULL"
            " AND proposed_address IS NULL AND proposed_phone IS NULL)"
            " OR (application_type = 'new_bar' AND proposed_bar_name IS NOT NULL AND proposed_address IS NOT NULL"
            " AND (bar_id IS NOT NULL) = (status = 'approved'))",
            name="ck_bar_owner_applications_type_fields",
        ),
        CheckConstraint(
            "business_registration_number ~ '^[0-9]{10}$'",
            name="ck_bar_owner_applications_business_registration_number",
        ),
        CheckConstraint(
            "(rejection_reason IS NOT NULL) = (status = 'rejected')",
            name="ck_bar_owner_applications_rejection_reason",
        ),
        CheckConstraint(
            "(reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL) = (status IN ('approved', 'rejected'))"
            " AND (reviewed_by_user_id IS NULL) = (reviewed_at IS NULL)",
            name="ck_bar_owner_applications_review",
        ),
        CheckConstraint(
            "business_status IS NULL OR business_verification_result = 'matched'",
            name="ck_bar_owner_applications_business_status",
        ),
        Index("ix_bar_owner_applications_status_created_at", "status", "created_at"),
        Index("ix_bar_owner_applications_applicant_user_id_created_at", "applicant_user_id", "created_at"),
        Index("ix_bar_owner_applications_bar_id", "bar_id"),
        # One pending application per user and bar, or per user and business number for new bars;
        # enforced here too so concurrent submissions cannot both pass the service check.
        Index(
            "uq_bar_owner_applications_pending_existing_bar",
            "applicant_user_id",
            "bar_id",
            unique=True,
            postgresql_where=text("status = 'pending' AND application_type = 'existing_bar'"),
        ),
        Index(
            "uq_bar_owner_applications_pending_new_bar",
            "applicant_user_id",
            "business_registration_number",
            unique=True,
            postgresql_where=text("status = 'pending' AND application_type = 'new_bar'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    applicant_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    application_type: Mapped[OwnerApplicationType] = mapped_column(
        _pg_enum(OwnerApplicationType, "owner_application_type"), nullable=False
    )
    bar_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bars.id"), nullable=True)
    proposed_bar_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    proposed_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    proposed_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    business_registration_number: Mapped[str] = mapped_column(CHAR(10), nullable=False)
    representative_name: Mapped[str] = mapped_column(String(100), nullable=False)
    opening_date: Mapped[date] = mapped_column(Date, nullable=False)
    business_verification_result: Mapped[BusinessVerificationResult] = mapped_column(
        _pg_enum(BusinessVerificationResult, "business_verification_result"), nullable=False
    )
    business_status: Mapped[BusinessStatus | None] = mapped_column(
        _pg_enum(BusinessStatus, "business_status"), nullable=True
    )
    # When the stored result was obtained; a failed operator recheck changes neither (spec 3.11.13).
    business_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    applicant_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[OwnerApplicationStatus] = mapped_column(
        _pg_enum(OwnerApplicationStatus, "owner_application_status"),
        nullable=False,
        default=OwnerApplicationStatus.PENDING,
        server_default=text("'pending'"),
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BarOwner(Base):
    """An approved owner of a bar. The row with revoked_at null is the bar's current owner."""

    __tablename__ = "bar_owners"
    __table_args__ = (
        CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by_user_id IS NULL)",
            name="ck_bar_owners_revoked",
        ),
        # At most one current owner per bar; also serves lookups by bar.
        Index(
            "uq_bar_owners_current_bar_id",
            "bar_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_bar_owners_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bar_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bars.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bar_owner_applications.id"), nullable=False, unique=True
    )
    # When the application was approved.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
