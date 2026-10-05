from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


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


class MenuBoard(Base):
    """The current menu board of a bar; at most one per bar."""

    __tablename__ = "menu_boards"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bar_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bars.id"), nullable=False, unique=True
    )
    # References menu_imports.id; the FK is added together with the AI menu import tables.
    last_import_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
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
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    menu_board_entry_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("menu_board_entries.id"), nullable=False
    )
    # References extracted_options.id; the FK is added together with the AI menu import tables.
    source_extracted_option_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    option_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pour_ml: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    price_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    entry: Mapped[MenuBoardEntry] = relationship(back_populates="options")
