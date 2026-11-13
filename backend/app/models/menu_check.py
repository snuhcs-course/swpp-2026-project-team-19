"""Menu item checks: menu items an operator should look at (API spec 3.18, schema guide 7.7 and 7.8).

A check is raised for a whisky published without a product, or for a link the owner's review changed in
a way a person should confirm. An operator resolves it by linking a product, creating one and linking it,
keeping the current link, or marking the item as non-whisky. Each reason keeps the review line that raised
it, so a later reason never replaces the evidence of an earlier one.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum as SQLAlchemyEnum, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class CheckReason(str, Enum):
    UNLINKED = "unlinked"
    RELINKED_BY_NAME = "relinked_by_name"
    UNLINKED_BY_NAME = "unlinked_by_name"
    ATTRIBUTE_CONFLICT = "attribute_conflict"
    PRICE_CONFLICT = "price_conflict"


class CheckStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class CheckResolution(str, Enum):
    LINK_EXISTING = "link_existing"
    CREATE_AND_LINK = "create_and_link"
    KEEP = "keep"
    MARK_AS_OTHER = "mark_as_other"


def _pg_enum(enum_class: type[Enum], name: str) -> SQLAlchemyEnum:
    """Store enum values (not member names), like the other models."""
    return SQLAlchemyEnum(enum_class, name=name, values_callable=lambda enum: [member.value for member in enum])


class MenuItemCheck(Base):
    """One menu item an operator should look at.

    While open, `bar_menu_item_id` follows the board line: a rename or rematch that moves the line moves
    or merges the open check with it. A check an operator resolved stays on the item it was resolved on.
    """

    __tablename__ = "menu_item_checks"
    __table_args__ = (
        # At most one open check per item; closed checks of the same item can be many.
        Index(
            "uq_menu_item_checks_open_bar_menu_item_id",
            "bar_menu_item_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_menu_item_checks_status_created_at", "status", "created_at"),
        Index("ix_menu_item_checks_bar_id_status", "bar_id", "status"),
        CheckConstraint("(status = 'resolved') = (resolution IS NOT NULL)", name="ck_menu_item_checks_resolution"),
        CheckConstraint("(status = 'open') = (resolved_at IS NULL)", name="ck_menu_item_checks_resolved_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bar_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bars.id"), nullable=False)
    bar_menu_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bar_menu_items.id"), nullable=False
    )
    # The name shown on the board, kept here because board entries are deleted when the line leaves.
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[CheckStatus] = mapped_column(
        _pg_enum(CheckStatus, "menu_item_check_status"),
        nullable=False,
        default=CheckStatus.OPEN,
        server_default=text("'open'"),
    )
    # Options the server dropped when merging lines with conflicting prices (price_conflict); the only
    # place those prices are kept. Each: optionLabel, pourMl, priceKrw, displayName, extractedItemId.
    discarded_options: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolution: Mapped[CheckResolution | None] = mapped_column(
        _pg_enum(CheckResolution, "menu_item_check_resolution"), nullable=True
    )
    resolved_product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id"), nullable=True
    )
    # Null for a temporary-login operator without a users row, and for dismissed checks.
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reasons: Mapped[list["MenuItemCheckReason"]] = relationship(
        back_populates="check", order_by="MenuItemCheckReason.added_at", cascade="all, delete-orphan"
    )


class MenuItemCheckReason(Base):
    """One reason of a check, with the review line that raised it (null for manual adds and edits).

    A check has at least one reason, also after it is closed. Merging checks copies the closing check's
    rows to the remaining check, so a dismissed check keeps its own reasons.
    """

    __tablename__ = "menu_item_check_reasons"
    __table_args__ = (
        Index("ix_menu_item_check_reasons_check_id_added_at", "check_id", "added_at"),
        CheckConstraint(
            "(source_menu_import_id IS NULL) = (source_extracted_item_id IS NULL)",
            name="ck_menu_item_check_reasons_source_complete",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    check_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("menu_item_checks.id"), nullable=False)
    reason: Mapped[CheckReason] = mapped_column(_pg_enum(CheckReason, "menu_item_check_reason"), nullable=False)
    source_menu_import_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("menu_imports.id"), nullable=True
    )
    source_extracted_item_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extracted_items.id"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    check: Mapped[MenuItemCheck] = relationship(back_populates="reasons")
