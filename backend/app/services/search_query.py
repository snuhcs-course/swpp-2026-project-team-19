"""Resolve a customer search query to catalog products (API spec, section 3.10.1).

The steps run in order and stop at the first one that finds an active product:
brand -> alias_exact -> partial -> none. No embedding or LLM is used at search time.

The brand step comes first so that a brand name always shows the whole brand. A flagship
product often has the brand name as an alias too (Royal Brackla 12 as "Royal Brackla"); with
the product step first, "Royal Brackla" would show only the 12 while "로얄브라클라" showed every
Royal Brackla, so the result would depend on which spelling the customer typed. The products
whose alias equals the query still come first, and a product of another brand with that alias is
included, so the brand step never hides an exact product match.
"""

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.normalize import normalize
from app.models import BrandAlias, Product, ProductAlias

MatchType = Literal["alias_exact", "brand", "partial", "none"]

PARTIAL_LIMIT = 10


@dataclass
class QueryResolution:
    normalized_query: str
    match_type: MatchType
    # Each with `brand` loaded. Sorted by display name, except that exact product-alias matches come
    # first in the brand step and partial matches are sorted closest alias first.
    products: list[Product]
    # Products with a searchable alias equal to the query: all of them for alias_exact, the ones
    # the brand step puts first, none for partial. Callers list their rows first too.
    exact_product_ids: frozenset[UUID] = field(default_factory=frozenset)


def _active_products() -> Select[tuple[Product]]:
    return select(Product).where(Product.is_active).options(joinedload(Product.brand))


def _alias_exact(session: Session, normalized: str) -> list[Product]:
    matched = select(ProductAlias.product_id).where(
        ProductAlias.normalized_alias == normalized, ProductAlias.is_searchable
    )
    query = _active_products().where(Product.id.in_(matched)).order_by(Product.display_name, Product.id)
    return list(session.scalars(query))


def _brand(session: Session, normalized: str) -> list[Product]:
    matched = select(BrandAlias.brand_id).where(BrandAlias.normalized_alias == normalized)
    query = _active_products().where(Product.brand_id.in_(matched)).order_by(Product.display_name, Product.id)
    return list(session.scalars(query))


def _partial(session: Session, normalized: str) -> list[Product]:
    # A shorter matching alias means the query covers more of it, so it ranks first.
    closest = (
        select(ProductAlias.product_id, func.min(func.length(ProductAlias.normalized_alias)).label("alias_length"))
        .where(ProductAlias.normalized_alias.contains(normalized, autoescape=True), ProductAlias.is_searchable)
        .group_by(ProductAlias.product_id)
        .subquery()
    )
    query = (
        _active_products()
        .join(closest, closest.c.product_id == Product.id)
        .order_by(closest.c.alias_length, Product.display_name, Product.id)
        .limit(PARTIAL_LIMIT)
    )
    return list(session.scalars(query))


def resolve_search_query(session: Session, query: str) -> QueryResolution:
    """Callers reject queries that normalize to an empty string before calling this."""
    normalized = normalize(query)
    exact = _alias_exact(session, normalized)
    exact_ids = frozenset(product.id for product in exact)

    brand = _brand(session, normalized)
    if brand:
        # Exact product matches first (of any brand), then the rest of the brand.
        rest = [product for product in brand if product.id not in exact_ids]
        return QueryResolution(normalized, "brand", exact + rest, exact_ids)
    if exact:
        return QueryResolution(normalized, "alias_exact", exact, exact_ids)
    partial = _partial(session, normalized)
    if partial:
        return QueryResolution(normalized, "partial", partial)
    return QueryResolution(normalized, "none", [])
