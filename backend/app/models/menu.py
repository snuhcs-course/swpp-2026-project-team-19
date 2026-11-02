from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.catalog import Product


class BarMenuItem(Base):
    """A product a bar has sold. Kept when a later board drops it; board membership decides visibility."""

    __tablename__ = "bar_menu_items"
    __table_args__ = (
        UniqueConstraint("bar_id", "product_id", name="uq_bar_menu_items_bar_id_product_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bar_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bars.id"), nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    product: Mapped[Product] = relationship()


class MenuBoard(Base):
    """The current menu board of a bar; at most one per bar."""

    __tablename__ = "menu_boards"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_menu_boards_version"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bar_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bars.id"), nullable=False, unique=True
    )
    # The import that last changed this board; null for boards loaded from seed data.
    last_import_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("menu_imports.id"), nullable=True
    )
    # Raised by every review publish and manual edit; a manual edit must send the version it read.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    entries: Mapped[list["MenuBoardEntry"]] = relationship(
        back_populates="menu_board",
        order_by="MenuBoardEntry.sort_order",
        cascade="all, delete-orphan",
    )


class MenuBoardEntry(Base):
    __tablename__ = "menu_board_entries"
    __table_args__ = (
        UniqueConstraint(
            "menu_board_id", "sort_order", name="uq_menu_board_entries_menu_board_id_sort_order"
        ),
        UniqueConstraint(
            "menu_board_id",
            "bar_menu_item_id",
            name="uq_menu_board_entries_menu_board_id_bar_menu_item_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    menu_board_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("menu_boards.id"), nullable=False
    )
    bar_menu_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bar_menu_items.id"), nullable=False
    )
    # The name as written on the bar's menu, not the canonical product name.
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    menu_board: Mapped[MenuBoard] = relationship(back_populates="entries")
    bar_menu_item: Mapped[BarMenuItem] = relationship()
    options: Mapped[list["MenuEntryOption"]] = relationship(
        back_populates="entry",
        order_by="MenuEntryOption.sort_order",
        cascade="all, delete-orphan",
    )


class MenuEntryOption(Base):
    """One price and pour-size choice of a menu board entry."""

    __tablename__ = "menu_entry_options"
    __table_args__ = (
        UniqueConstraint(
            "menu_board_entry_id",
            "sort_order",
            name="uq_menu_entry_options_menu_board_entry_id_sort_order",
        ),
        Index("ix_menu_entry_options_price_krw", "price_krw"),
        CheckConstraint(
            "(discount_price_krw IS NULL) = (discount_starts_at IS NULL) "
            "AND (discount_starts_at IS NULL) = (discount_ends_at IS NULL)",
            name="ck_menu_entry_options_discount_complete",
        ),
        CheckConstraint(
            "discount_price_krw BETWEEN 1 AND price_krw - 1", name="ck_menu_entry_options_discount_price"
        ),
        CheckConstraint("discount_ends_at > discount_starts_at", name="ck_menu_entry_options_discount_period"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    menu_board_entry_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("menu_board_entries.id"), nullable=False
    )
    # The reviewed extracted option this was published from; null for manual or seed entries.
    source_extracted_option_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extracted_options.id"), nullable=True
    )
    option_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pour_ml: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # The list price, also while a discount is running.
    price_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    # At most one time-limited discount, applied in [starts_at, ends_at); all three set or all null.
    discount_price_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discount_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    entry: Mapped[MenuBoardEntry] = relationship(back_populates="options")
