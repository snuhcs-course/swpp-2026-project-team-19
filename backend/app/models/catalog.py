# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #8, #11). Reviewed by Haeul Yang.
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    canonical_name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    aliases: Mapped[list["BrandAlias"]] = relationship(back_populates="brand")
    products: Mapped[list["Product"]] = relationship(back_populates="brand")


class BrandAlias(Base):
    __tablename__ = "brand_aliases"
    __table_args__ = (
        UniqueConstraint(
            "brand_id",
            "normalized_alias",
            name="uq_brand_aliases_brand_id_normalized_alias",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    brand_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("brands.id"), nullable=False
    )
    alias_text: Mapped[str] = mapped_column(String(120), nullable=False)
    # Filled by app.core.normalize.normalize(); regenerated for every row when the rule changes.
    normalized_alias: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    brand: Mapped[Brand] = relationship(back_populates="aliases")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_brand_id_age_years", "brand_id", "age_years"),
        Index("ix_products_brand_id_edition_name", "brand_id", "edition_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default="whisky", server_default=text("'whisky'")
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    brand_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("brands.id"), nullable=False
    )
    age_years: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    edition_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    abv: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # The extracted item whose review created this product; null for pre-registered products.
    created_from_extracted_item_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extracted_items.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    brand: Mapped[Brand] = relationship(back_populates="products")
    aliases: Mapped[list["ProductAlias"]] = relationship(back_populates="product")


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "normalized_alias",
            name="uq_product_aliases_product_id_normalized_alias",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id"), nullable=False
    )
    alias_text: Mapped[str] = mapped_column(String(200), nullable=False)
    # Not globally unique: an ambiguous spelling may point to several products.
    normalized_alias: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_searchable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="aliases")
