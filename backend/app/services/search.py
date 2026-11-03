"""Customer product search: bars that currently sell the products a query or a productId resolves to (API spec, section 3.10)."""

import math
from collections import Counter
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.errors import validation_failed
from app.core.normalize import normalize
from app.models import Bar, BarMenuItem, BarStatus, MenuBoard, MenuBoardEntry, Product, SearchSource
from app.schemas.search import (
    MatchedProductResponse,
    SearchBarsResponse,
    SearchOptionResponse,
    SearchResultItem,
)
from app.services.bar_menu import discount_response
from app.services.bar_photo_links import cover_photo_id, cover_thumbnail_url
from app.services.request_limits import kst_date
from app.services.search_counts import record_product_search, record_unmatched_search
from app.services.search_query import QueryResolution, resolve_search_query

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


def validate_search_input(
    query: str | None, product_id: UUID | None, lat: float | None, lng: float | None
) -> str | None:
    """Checks FastAPI's Query constraints cannot express, in the order of spec 3.10.5. Returns the
    trimmed query, or None for a productId search."""
    if (query is None) == (product_id is None):
        raise validation_failed(
            "productId", "EXACTLY_ONE_REQUIRED", "검색어와 상품 ID 중 하나만 보내야 합니다."
        )
    trimmed = validate_query_text(query) if query is not None else None
    if (lat is None) != (lng is None):
        missing = "lng" if lng is None else "lat"
        raise validation_failed(missing, "LAT_LNG_REQUIRED_TOGETHER", "위도와 경도는 함께 보내야 합니다.")
    return trimmed


def on_sale(statement: Select) -> Select:
    """`statement` over the menu board entries customers can find (spec 3.10.2): on an active bar's
    current board and not sold out. Search rows and the popular whiskies' barCount (3.17.2) both
    use it, so a card's "바 N곳" is the number of bars its search shows."""
    return (
        statement.select_from(MenuBoardEntry)
        .join(MenuBoard, MenuBoard.id == MenuBoardEntry.menu_board_id)
        .join(BarMenuItem, BarMenuItem.id == MenuBoardEntry.bar_menu_item_id)
        .join(Bar, Bar.id == MenuBoard.bar_id)
        .where(
            BarMenuItem.bar_id == MenuBoard.bar_id,
            # Sold-out items are hidden from every caller of these public APIs.
            BarMenuItem.sold_out_at.is_(None),
            Bar.status == BarStatus.ACTIVE,
        )
    )


def _selling_entries(session: Session, product_ids: list[UUID]):
    """(entry with options, product_id, bar, published_at, cover photo id or None) for products on sale on an
    active bar's current board."""
    query = on_sale(
        select(MenuBoardEntry, BarMenuItem.product_id, Bar, MenuBoard.published_at, cover_photo_id())
    ).where(
        BarMenuItem.product_id.in_(product_ids)
    )
    return session.execute(query.options(selectinload(MenuBoardEntry.options))).all()


def _active_product(session: Session, product_id: UUID) -> Product | None:
    query = select(Product).where(Product.id == product_id, Product.is_active).options(joinedload(Product.brand))
    return session.scalar(query)


def _sort_key(item: SearchResultItem, *, by_distance: bool, exact_product_ids: frozenset[UUID]) -> tuple:
    """Rows of exact product-alias matches first (they matter in brand results); then distance
    ascending with a location, else newest menu first; then bar name (spec), then product name and
    ids so ties always come back in the same order."""
    primary = item.distanceMeters if by_distance else -item.menuUpdatedAt.timestamp()
    exact_first = item.productId not in exact_product_ids
    return (exact_first, primary, item.barName, item.productDisplayName, str(item.barId), str(item.productId))


def search_bars(
    session: Session,
    query: str | None = None,
    *,
    product_id: UUID | None = None,
    lat: float | None = None,
    lng: float | None = None,
    limit: int = 50,
    source: SearchSource = SearchSource.INPUT,
    base_url: str,
) -> SearchBarsResponse:
    """Search by `query` or by `product_id` (exactly one), then count the search (spec 3.10.6)."""
    trimmed = validate_search_input(query, product_id, lat, lng)
    if trimmed is None:
        # No resolution steps: a productId search is that product or nothing (spec 3.10.1).
        product = _active_product(session, product_id)
        resolution = QueryResolution(None, "product", [product]) if product else QueryResolution(None, "none", [])
    else:
        require_searchable(trimmed)
        resolution = resolve_search_query(session, trimmed)

    products = {product.id: product for product in resolution.products}
    rows = _selling_entries(session, list(products)) if products else []
    now = datetime.now(timezone.utc)

    items = [
        SearchResultItem(
            barId=bar.id,
            barName=bar.name,
            address=bar.address,
            latitude=float(bar.latitude),
            longitude=float(bar.longitude),
            coverThumbnailUrl=cover_thumbnail_url(cover_id, base_url),
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
                    discount=discount_response(option, now),
                    sortOrder=option.sort_order,
                )
                for option in entry.options
            ],
            menuUpdatedAt=published_at,
        )
        for entry, product_id, bar, published_at, cover_id in rows
    ]
    items.sort(
        key=lambda item: _sort_key(
            item, by_distance=lat is not None, exact_product_ids=resolution.exact_product_ids
        )
    )

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
    response = SearchBarsResponse(
        query=trimmed,
        matchType=resolution.match_type,
        matchedProducts=matched,
        items=items[:limit],
        truncated=len(items) > limit,
    )
    # After the response is built: the count commits the session, which expires the loaded rows.
    _count_search(session, kst_date(now), resolution, trimmed, source)
    return response


def _count_search(
    session: Session, today: date, resolution: QueryResolution, trimmed: str | None, source: SearchSource
) -> None:
    """Only searches that resolved to one product count for it; brand, partial and several exact
    matches would raise several products at once (spec 3.10.6). Similar products count nowhere, like
    partial: they are not the product typed, and the query was not unrecognized either."""
    if resolution.match_type == "product" or (
        resolution.match_type == "alias_exact" and len(resolution.products) == 1
    ):
        record_product_search(session, today, resolution.products[0].id, source)
    elif resolution.match_type == "none" and trimmed is not None:
        record_unmatched_search(session, today, trimmed, resolution.normalized_query)
