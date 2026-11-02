"""Catalog rows created by a review submission (flow doc, chapter 16) or a manual menu add
(API spec 3.14.3): new brands, new products, and their aliases. Runs inside the caller's
transaction, and records the user who asked for them.

Before creating anything the database is checked again for the same brand or product,
since another review may have created it after this one's candidates were made:

- brand: the canonical name, or any submitted name, equals an existing brand alias
  (after normalization) or canonical name
- product: any submitted name equals an existing product alias after normalization, or
  a product has the same brand, category, age and normalized edition. Inactive products
  count too, so a product is never created twice.

A match with an existing row is a 409 for the caller to pick the existing entry. A match
with a row this submission created earlier (two lines of one new product, two products of
one new brand) reuses that row, since the reviewer had no way to select it. A manual add
creates one product, so only a review can reuse a row.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.normalize import normalize
from app.models import Brand, BrandAlias, MenuImport, Product, ProductAlias
from app.schemas.menu_review import (
    BrandDecision,
    CreateProduct,
    NewBrand,
    NewProduct,
    ProductAliasInput,
    SelectExistingProduct,
)
from app.services.menu_review_validation import ValidatedReview


@dataclass
class CatalogResult:
    # Product of every product decision, selected or created, by extracted item id.
    product_ids: dict[UUID, UUID] = field(default_factory=dict)
    created_brands: int = 0
    created_products: int = 0


def _review_url(menu_import: MenuImport) -> str:
    return f"/api/menu-imports/{menu_import.id}"


def _brand_names(decision: NewBrand) -> set[str]:
    return {normalize(decision.canonicalName), *(normalize(a.aliasText) for a in decision.aliases)}


def _product_names(product: NewProduct, aliases: list[ProductAliasInput]) -> set[str]:
    return {normalize(product.displayName), *(normalize(a.aliasText) for a in aliases)}


def _same_edition(a: str | None, b: str | None) -> bool:
    return (normalize(a) if a else None) == (normalize(b) if b else None)


class _CatalogWriter:
    def __init__(self, session: Session, created_by_user_id: UUID | None) -> None:
        self.session = session
        self.created_by_user_id = created_by_user_id
        self.created_brand_ids: set[UUID] = set()
        self.created_product_ids: set[UUID] = set()

    # ---- duplicate lookups ----

    def _find_brand(self, decision: NewBrand) -> Brand | None:
        matched = select(BrandAlias.brand_id).where(BrandAlias.normalized_alias.in_(_brand_names(decision)))
        query = (
            select(Brand)
            .where(or_(Brand.id.in_(matched), Brand.canonical_name == decision.canonicalName))
            .order_by(Brand.canonical_name, Brand.id)
        )
        return self.session.scalars(query).first()

    def _find_product(self, product: NewProduct, aliases: list[ProductAliasInput], brand_id: UUID) -> Product | None:
        names = _product_names(product, aliases)
        by_alias = select(ProductAlias.product_id).where(ProductAlias.normalized_alias.in_(names))
        found = self.session.scalars(
            select(Product).where(Product.id.in_(by_alias)).order_by(Product.display_name, Product.id)
        ).first()
        if found is not None:
            return found
        same_attributes = self.session.scalars(
            select(Product)
            .where(
                Product.brand_id == brand_id,
                Product.category == product.category,
                Product.age_years.is_not_distinct_from(product.ageYears),
            )
            .order_by(Product.display_name, Product.id)
        )
        return next((p for p in same_attributes if _same_edition(p.edition_name, product.editionName)), None)

    def _duplicate_brand(self, brand: Brand, details: dict) -> ApiError:
        return ApiError(
            409,
            "DUPLICATE_BRAND_FOUND",
            "같은 브랜드가 이미 등록되어 있습니다. 기존 브랜드를 선택해 주세요.",
            details={**details, "existingBrand": {"brandId": str(brand.id), "canonicalName": brand.canonical_name}},
        )

    def _duplicate_product(self, product: Product, details: dict) -> ApiError:
        brand = self.session.get(Brand, product.brand_id)
        return ApiError(
            409,
            "DUPLICATE_PRODUCT_FOUND",
            "같은 상품이 이미 등록되어 있습니다. 기존 상품을 선택해 주세요.",
            details={
                **details,
                "existingProduct": {
                    "productId": str(product.id),
                    "displayName": product.display_name,
                    "brandId": str(product.brand_id),
                    "brandName": brand.canonical_name,
                    "category": product.category,
                    "ageYears": product.age_years,
                    "editionName": product.edition_name,
                    "isActive": product.is_active,
                },
            },
        )

    # ---- writes ----

    def _add_brand_aliases(self, brand_id: UUID, aliases: list[tuple[str, str | None]]) -> None:
        existing = set(self.session.scalars(select(BrandAlias.normalized_alias).where(BrandAlias.brand_id == brand_id)))
        for text, language in aliases:
            normalized = normalize(text)
            if normalized not in existing:
                existing.add(normalized)
                self.session.add(
                    BrandAlias(brand_id=brand_id, alias_text=text, normalized_alias=normalized, language_code=language)
                )
        self.session.flush()

    def add_product_aliases(self, product_id: UUID, aliases: list[ProductAliasInput]) -> None:
        existing = set(
            self.session.scalars(select(ProductAlias.normalized_alias).where(ProductAlias.product_id == product_id))
        )
        for alias in aliases:
            normalized = normalize(alias.aliasText)
            if normalized not in existing:
                existing.add(normalized)
                self.session.add(
                    ProductAlias(
                        product_id=product_id,
                        alias_text=alias.aliasText,
                        normalized_alias=normalized,
                        language_code=alias.languageCode,
                        is_searchable=alias.isSearchable,
                    )
                )
        self.session.flush()

    def _brand_for(self, decision: BrandDecision, details: dict) -> UUID:
        if decision.type == "existing":
            return decision.brandId
        aliases = [(decision.canonicalName, None), *((a.aliasText, a.languageCode) for a in decision.aliases)]
        found = self._find_brand(decision)
        if found is not None:
            if found.id not in self.created_brand_ids:
                raise self._duplicate_brand(found, details)
            self._add_brand_aliases(found.id, aliases)
            return found.id
        brand = Brand(canonical_name=decision.canonicalName, created_by_user_id=self.created_by_user_id)
        self.session.add(brand)
        self.session.flush()
        self._add_brand_aliases(brand.id, aliases)
        self.created_brand_ids.add(brand.id)
        return brand.id

    def create_product(
        self,
        brand: BrandDecision,
        product: NewProduct,
        aliases: list[ProductAliasInput],
        *,
        details: dict,
        extracted_item_id: UUID | None = None,
    ) -> UUID:
        """The new product's id, or the one this writer already created for the same product.
        `details` go into a duplicate's 409 next to the existing row."""
        brand_id = self._brand_for(brand, details)
        aliases = [ProductAliasInput(aliasText=product.displayName), *aliases]
        found = self._find_product(product, aliases, brand_id)
        if found is not None:
            if found.id not in self.created_product_ids:
                raise self._duplicate_product(found, details)
            self.add_product_aliases(found.id, aliases)
            return found.id
        row = Product(
            category=product.category,
            display_name=product.displayName,
            brand_id=brand_id,
            age_years=product.ageYears,
            edition_name=product.editionName,
            abv=Decimal(str(product.abv)) if product.abv is not None else None,
            is_active=True,
            created_from_extracted_item_id=extracted_item_id,
            created_by_user_id=self.created_by_user_id,
        )
        self.session.add(row)
        self.session.flush()
        self.add_product_aliases(row.id, aliases)
        self.created_product_ids.add(row.id)
        return row.id


def create_catalog_entries(
    session: Session, menu_import: MenuImport, review: ValidatedReview, *, created_by_user_id: UUID | None
) -> CatalogResult:
    """Create the brands, products and aliases a validated review asks for, in menu order."""
    writer = _CatalogWriter(session, created_by_user_id)
    result = CatalogResult()
    for entry in review.items:
        decision = entry.decision
        if isinstance(decision, SelectExistingProduct):
            writer.add_product_aliases(decision.productId, decision.aliasesToAdd)
            result.product_ids[entry.item.id] = decision.productId
        elif isinstance(decision, CreateProduct):
            result.product_ids[entry.item.id] = writer.create_product(
                decision.brand,
                decision.product,
                decision.aliases,
                details={"extractedItemId": str(entry.item.id), "reviewUrl": _review_url(menu_import)},
                extracted_item_id=entry.item.id,
            )
    result.created_brands = len(writer.created_brand_ids)
    result.created_products = len(writer.created_product_ids)
    return result


def create_new_product(
    session: Session,
    brand: BrandDecision,
    product: NewProduct,
    aliases: list[ProductAliasInput],
    *,
    created_by_user_id: UUID | None,
) -> UUID:
    """A manual add's new product (API spec 3.14.3). A duplicate's 409 has no review fields."""
    return _CatalogWriter(session, created_by_user_id).create_product(brand, product, aliases, details={})
