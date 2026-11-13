"""Bar-local menu items are not catalog products and never enter whisky search.

A pending whisky item is visible on its own bar menu until an operator links it
to an approved canonical product. Other categories remain local permanently.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class BarLocalMenuItem(Base):
    __tablename__ = "bar_local_menu_items"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bar_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bars.id"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    # MenuOptions are stored only here; no products / aliases row is created.
    options: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    sold_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now())
