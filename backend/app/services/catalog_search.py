# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #12). Reviewed by Haeul Yang.
"""Brand and product lookup for the menu review screen (API spec, sections 6 and 7).

The query is normalized with the same function as catalog aliases and compared with
`normalized_alias`: exact matches first, then aliases that contain the query, those with
the shortest matching alias first. Unlike customer search, every alias counts (including
non-searchable ones) and inactive products can be included, because the point is to find
an existing entry before creating a new one.
"""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Brand, BrandAlias, Product, ProductAlias
from app.schemas.catalog import (
    CatalogBrandItem,
    CatalogBrandsResponse,
    CatalogProductItem,
    CatalogProductsResponse,
)
from app.services.search import require_searchable, validate_query_text


def _best_aliases(rows: Iterable[tuple[UUID, str, str]], normalized: str) -> dict[UUID, tuple[tuple, str]]:
    """For each owner id, the (rank, alias text) of its closest alias.

    rank sorts an exact match first, then a shorter normalized alias, then the alias text.
    """
    best: dict[UUID, tuple[tuple, str]] = {}
    for owner_id, alias_text, normalized_alias in rows:
        rank = (normalized_alias != normalized, len(normalized_alias), alias_text)
        if owner_id not in best or rank < best[owner_id][0]:
            best[owner_id] = (rank, alias_text)
    return best


def search_brands(session: Session, query: str, *, limit: int = 20) -> CatalogBrandsResponse:
    normalized = require_searchable(validate_query_text(query))
    rows = session.execute(
        select(BrandAlias.brand_id, BrandAlias.alias_text, BrandAlias.normalized_alias).where(
            BrandAlias.normalized_alias.contains(normalized, autoescape=True)
        )
    ).all()
    best = _best_aliases(rows, normalized)
    brands = {brand.id: brand for brand in session.scalars(select(Brand).where(Brand.id.in_(best)))}
    ordered = sorted(best, key=lambda brand_id: (best[brand_id][0][:2], brands[brand_id].canonical_name, str(brand_id)))
    return CatalogBrandsResponse(
        items=[
            CatalogBrandItem(brandId=brand_id, canonicalName=brands[brand_id].canonical_name, matchedAlias=best[brand_id][1])
            for brand_id in ordered[:limit]
        ]
    )


def search_products(
    session: Session,
    query: str,
    *,
    brand_id: UUID | None = None,
    include_inactive: bool = True,
    limit: int = 20,
) -> CatalogProductsResponse:
    normalized = require_searchable(validate_query_text(query))
    alias_query = (
        select(ProductAlias.product_id, ProductAlias.alias_text, ProductAlias.normalized_alias)
        .join(Product, Product.id == ProductAlias.product_id)
        .where(ProductAlias.normalized_alias.contains(normalized, autoescape=True))
    )
    if brand_id is not None:
        alias_query = alias_query.where(Product.brand_id == brand_id)
    if not include_inactive:
        alias_query = alias_query.where(Product.is_active)
    best = _best_aliases(session.execute(alias_query).all(), normalized)
    products = {
        product.id: product
        for product in session.scalars(select(Product).where(Product.id.in_(best)).options(joinedload(Product.brand)))
    }
    ordered = sorted(
        best, key=lambda product_id: (best[product_id][0][:2], products[product_id].display_name, str(product_id))
    )
    return CatalogProductsResponse(
        items=[
            CatalogProductItem(
                productId=product.id,
                displayName=product.display_name,
                brandId=product.brand_id,
                brandName=product.brand.canonical_name,
                category=product.category,
                ageYears=product.age_years,
                editionName=product.edition_name,
                abv=float(product.abv) if product.abv is not None else None,
                isActive=product.is_active,
                matchedAlias=best[product.id][1],
            )
            for product in (products[product_id] for product_id in ordered[:limit])
        ]
    )
