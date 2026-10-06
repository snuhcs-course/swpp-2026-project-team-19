"""Resolve a customer search query to catalog products (API spec, section 3.10.1).

The steps run in order and stop at the first one that finds an active product:
alias_exact -> brand -> partial -> none. No embedding or LLM is used at search time.
"""

from dataclasses import dataclass
from typing import Literal

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
    # Each with `brand` loaded. Sorted by display name, except partial (closest alias first).
    products: list[Product]


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
    for match_type, step in (("alias_exact", _alias_exact), ("brand", _brand), ("partial", _partial)):
        products = step(session, normalized)
        if products:
            return QueryResolution(normalized, match_type, products)
    return QueryResolution(normalized, "none", [])
