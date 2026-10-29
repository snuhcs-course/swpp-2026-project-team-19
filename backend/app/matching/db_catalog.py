"""`CatalogLookup` backed by the catalog tables, used when processing a menu import."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.llm_layer import ProductMeta, bottler_of
from app.matching.types import ProductInfo
from app.models import Brand, BrandAlias, Product, ProductAlias


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


class CatalogSnapshot:
    """The whole active catalog read once, answering like `DbCatalog` (for active products) without further queries.

    The LLM matching layer looks things up between model calls that take seconds, so it uses
    this snapshot instead of a session that would hold a transaction open the whole time.
    Every list keeps the order of the matching `DbCatalog` query. `meta` holds what the layer
    needs about each product (`ProductMeta`): an independent bottling is a product whose brand's
    canonical name is a P17 bottler (`bottler_of`).
    """

    def __init__(self, session: Session) -> None:
        self._products: dict[UUID, ProductInfo] = {}
        self._brand_products: dict[UUID, list[UUID]] = {}
        self.meta: dict[UUID, ProductMeta] = {}
        rows = session.execute(
            select(Product, Brand.canonical_name)
            .join(Brand, Brand.id == Product.brand_id)
            .where(Product.is_active)
            .order_by(Product.display_name, Product.id)
        )
        bottlers: dict[UUID, str | None] = {}
        for product, brand_name in rows:
            self._products[product.id] = ProductInfo(
                product_id=product.id,
                display_name=product.display_name,
                age_years=product.age_years,
                edition_name=product.edition_name,
                brand_id=product.brand_id,
            )
            self._brand_products.setdefault(product.brand_id, []).append(product.id)
            bottlers[product.id] = bottler_of(brand_name)

        self._all_aliases: list[tuple[str, UUID]] = []
        self._aliases: dict[UUID, list[str]] = {}
        self._products_by_alias: dict[str, list[UUID]] = {}
        alias_texts: dict[UUID, list[str]] = {}
        query = (
            select(ProductAlias.normalized_alias, ProductAlias.product_id, ProductAlias.alias_text)
            .join(Product, Product.id == ProductAlias.product_id)
            .where(Product.is_active)
            .order_by(ProductAlias.product_id, ProductAlias.normalized_alias)
        )
        for alias, product_id, text in session.execute(query):
            self._all_aliases.append((alias, product_id))
            self._aliases.setdefault(product_id, []).append(alias)
            # (product, normalized alias) is unique, so each product appears once per alias.
            self._products_by_alias.setdefault(alias, []).append(product_id)
            alias_texts.setdefault(product_id, []).append(text)

        query = select(BrandAlias.normalized_alias, BrandAlias.brand_id).order_by(
            BrandAlias.brand_id, BrandAlias.normalized_alias
        )
        self._all_brand_aliases = [(alias, brand_id) for alias, brand_id in session.execute(query)]
        self._brands_by_alias: dict[str, list[UUID]] = {}
        for alias, brand_id in self._all_brand_aliases:  # (brand, normalized alias) is unique too
            self._brands_by_alias.setdefault(alias, []).append(brand_id)

        for product_id, info in self._products.items():
            self.meta[product_id] = ProductMeta(
                display_name=info.display_name,
                age_years=info.age_years,
                edition_name=info.edition_name,
                bottler=bottlers[product_id],
                aliases=tuple(alias_texts.get(product_id, ())),
            )

    def find_product_ids_by_alias(self, normalized_alias: str) -> list[UUID]:
        return list(self._products_by_alias.get(normalized_alias, []))

    def get_product(self, product_id: UUID) -> ProductInfo | None:
        return self._products.get(product_id)

    def get_normalized_aliases(self, product_id: UUID) -> list[str]:
        return list(self._aliases.get(product_id, []))

    def find_brand_ids_by_alias(self, normalized_alias: str) -> list[UUID]:
        return list(self._brands_by_alias.get(normalized_alias, []))

    def get_brand_product_ids(self, brand_id: UUID) -> list[UUID]:
        return list(self._brand_products.get(brand_id, []))

    def list_normalized_aliases(self) -> list[tuple[str, UUID]]:
        return self._all_aliases

    def list_normalized_brand_aliases(self) -> list[tuple[str, UUID]]:
        return self._all_brand_aliases
