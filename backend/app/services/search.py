# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9, #12). Reviewed by Haeul Yang.
"""Customer product search: bars that currently sell the products a query resolves to (API spec, section 3.10)."""

import math
from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import validation_failed
from app.core.normalize import normalize
from app.models import Bar, BarMenuItem, BarStatus, MenuBoard, MenuBoardEntry
from app.schemas.search import (
    MatchedProductResponse,
    SearchBarsResponse,
    SearchOptionResponse,
    SearchResultItem,
)
from app.services.search_query import resolve_search_query

MAX_QUERY_LENGTH = 100
EARTH_RADIUS_METERS = 6_371_008.8


def distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """Great-circle (haversine) distance, rounded to whole meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return round(2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a)))


def validate_query_text(query: str) -> str:
    """Blank and length checks FastAPI's Query constraints cannot express. Returns the trimmed query."""
    trimmed = query.strip()
    if not trimmed:
        raise validation_failed("query", "BLANK", "검색어를 입력해 주세요.")
    if len(trimmed) > MAX_QUERY_LENGTH:
        raise validation_failed("query", "STRING_TOO_LONG", f"검색어는 {MAX_QUERY_LENGTH}자 이하여야 합니다.")
    return trimmed


def require_searchable(trimmed: str) -> str:
    """The normalized query; rejects one with nothing left after normalization (e.g. "!!!")."""
    normalized = normalize(trimmed)
    if not normalized:
        raise validation_failed("query", "NOT_SEARCHABLE", "검색할 수 있는 문자가 없습니다.")
    return normalized


def validate_search_input(query: str, lat: float | None, lng: float | None) -> str:
    """Checks FastAPI's Query constraints cannot express. Returns the trimmed query."""
    trimmed = validate_query_text(query)
    if (lat is None) != (lng is None):
        missing = "lng" if lng is None else "lat"
        raise validation_failed(missing, "LAT_LNG_REQUIRED_TOGETHER", "위도와 경도는 함께 보내야 합니다.")
    return trimmed


def _selling_entries(session: Session, product_ids: list[UUID]):
    """(entry with options, product_id, bar, published_at) for products on an active bar's current board."""
    query = (
        select(MenuBoardEntry, BarMenuItem.product_id, Bar, MenuBoard.published_at)
        .join(MenuBoard, MenuBoard.id == MenuBoardEntry.menu_board_id)
        .join(BarMenuItem, BarMenuItem.id == MenuBoardEntry.bar_menu_item_id)
        .join(Bar, Bar.id == MenuBoard.bar_id)
        .where(
            BarMenuItem.product_id.in_(product_ids),
            BarMenuItem.bar_id == MenuBoard.bar_id,
            Bar.status == BarStatus.ACTIVE,
        )
        .options(selectinload(MenuBoardEntry.options))
    )
    return session.execute(query).all()


def _sort_key(item: SearchResultItem, *, by_distance: bool) -> tuple:
    """Distance ascending with a location, else newest menu first; then bar name (spec),
    then product name and ids so ties always come back in the same order."""
    primary = item.distanceMeters if by_distance else -item.menuUpdatedAt.timestamp()
    return (primary, item.barName, item.productDisplayName, str(item.barId), str(item.productId))


def search_bars(
    session: Session, query: str, *, lat: float | None = None, lng: float | None = None, limit: int = 50
) -> SearchBarsResponse:
    trimmed = validate_search_input(query, lat, lng)
    require_searchable(trimmed)
    resolution = resolve_search_query(session, trimmed)

    products = {product.id: product for product in resolution.products}
    rows = _selling_entries(session, list(products)) if products else []

    items = [
        SearchResultItem(
            barId=bar.id,
            barName=bar.name,
            address=bar.address,
            latitude=float(bar.latitude),
            longitude=float(bar.longitude),
            distanceMeters=(
                distance_meters(lat, lng, float(bar.latitude), float(bar.longitude)) if lat is not None else None
            ),
            productId=product_id,
            productDisplayName=products[product_id].display_name,
            menuDisplayName=entry.display_name,
            options=[
                SearchOptionResponse(
                    optionLabel=option.option_label,
                    pourMl=option.pour_ml,
                    priceKrw=option.price_krw,
                    sortOrder=option.sort_order,
                )
                for option in entry.options
            ],
            menuUpdatedAt=published_at,
        )
        for entry, product_id, bar, published_at in rows
    ]
    items.sort(key=lambda item: _sort_key(item, by_distance=lat is not None))

    counts = Counter(item.productId for item in items)
    matched = [
        MatchedProductResponse(
            productId=product.id,
            displayName=product.display_name,
            brandName=product.brand.canonical_name,
            ageYears=product.age_years,
            editionName=product.edition_name,
            resultCount=counts[product.id],
        )
        for product in resolution.products
    ]
    return SearchBarsResponse(
        query=trimmed,
        matchType=resolution.match_type,
        matchedProducts=matched,
        items=items[:limit],
        truncated=len(items) > limit,
    )
