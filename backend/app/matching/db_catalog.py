# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #11); Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P22). Reviewed by Haeul Yang.
"""`CatalogLookup` backed by the catalog tables, used when processing a menu import."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.types import ProductInfo
from app.models import BrandAlias, Product, ProductAlias


class DbCatalog:
    """Reads active products and all their aliases, including ones hidden from customer search.

    Unsearchable aliases (e.g. menu typos) are kept because they exist precisely so that
    menu lines match. Lookups are cached per instance, so create one per processing run.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._products: dict[UUID, ProductInfo | None] = {}
        self._aliases: dict[UUID, list[str]] = {}
        self._brand_products: dict[UUID, list[UUID]] = {}
        self._all_aliases: list[tuple[str, UUID]] | None = None
        self._all_brand_aliases: list[tuple[str, UUID]] | None = None

    def find_product_ids_by_alias(self, normalized_alias: str) -> list[UUID]:
        query = (
            select(ProductAlias.product_id)
            .join(Product, Product.id == ProductAlias.product_id)
            .where(ProductAlias.normalized_alias == normalized_alias, Product.is_active)
            .distinct()
            .order_by(ProductAlias.product_id)
        )
        return list(self._session.scalars(query))

    def get_product(self, product_id: UUID) -> ProductInfo | None:
        if product_id not in self._products:
            product = self._session.get(Product, product_id)
            self._products[product_id] = (
                ProductInfo(
                    product_id=product.id,
                    display_name=product.display_name,
                    age_years=product.age_years,
                    edition_name=product.edition_name,
                    brand_id=product.brand_id,
                )
                if product is not None and product.is_active
                else None
            )
        return self._products[product_id]

    def get_normalized_aliases(self, product_id: UUID) -> list[str]:
        if product_id not in self._aliases:
            query = (
                select(ProductAlias.normalized_alias)
                .where(ProductAlias.product_id == product_id)
                .order_by(ProductAlias.normalized_alias)
            )
            self._aliases[product_id] = list(self._session.scalars(query))
        return self._aliases[product_id]

    def find_brand_ids_by_alias(self, normalized_alias: str) -> list[UUID]:
        query = (
            select(BrandAlias.brand_id)
            .where(BrandAlias.normalized_alias == normalized_alias)
            .distinct()
            .order_by(BrandAlias.brand_id)
        )
        return list(self._session.scalars(query))

    def get_brand_product_ids(self, brand_id: UUID) -> list[UUID]:
        if brand_id not in self._brand_products:
            query = (
                select(Product.id)
                .where(Product.brand_id == brand_id, Product.is_active)
                .order_by(Product.display_name, Product.id)
            )
            self._brand_products[brand_id] = list(self._session.scalars(query))
        return self._brand_products[brand_id]

    def list_normalized_aliases(self) -> list[tuple[str, UUID]]:
        if self._all_aliases is None:
            query = (
                select(ProductAlias.normalized_alias, ProductAlias.product_id)
                .join(Product, Product.id == ProductAlias.product_id)
                .where(Product.is_active)
                .order_by(ProductAlias.product_id, ProductAlias.normalized_alias)
            )
            self._all_aliases = [(alias, product_id) for alias, product_id in self._session.execute(query)]
        return self._all_aliases

    def list_normalized_brand_aliases(self) -> list[tuple[str, UUID]]:
        if self._all_brand_aliases is None:
            query = select(BrandAlias.normalized_alias, BrandAlias.brand_id).order_by(
                BrandAlias.brand_id, BrandAlias.normalized_alias
            )
            self._all_brand_aliases = [(alias, brand_id) for alias, brand_id in self._session.execute(query)]
        return self._all_brand_aliases
