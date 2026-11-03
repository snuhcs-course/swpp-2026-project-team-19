from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_base_url
from app.db.session import get_session
from app.schemas.errors import error_responses
from app.models import SearchSource
from app.schemas.search import (
    BarNamesResponse,
    MapBarsResponse,
    NearbyBarsResponse,
    PopularProductsResponse,
    SearchBarsResponse,
)
from app.services.bar_name_search import DEFAULT_LIMIT, MAX_LIMIT, search_bar_names
from app.services.map_bars import MAX_SPAN_DEGREES, find_map_bars
from app.services.nearby_bars import DEFAULT_RADIUS_METERS, MAX_RADIUS_METERS, find_nearby_bars
from app.services.popular_products import DEFAULT_LIMIT as POPULAR_DEFAULT_LIMIT
from app.services.popular_products import MAX_LIMIT as POPULAR_MAX_LIMIT
from app.services.popular_products import popular_products
from app.services.request_limits import kst_date
from app.services.search import search_bars

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get(
    "/bars",
    response_model=SearchBarsResponse,
    summary="Bars currently selling the whisky a query or a productId names",
    description=(
        "Public; no token is needed. The location is used only to compute distance and is not stored.\n\n"
        "Send exactly one of `query` (the search box) and `productId` (a popular-whisky card, "
        "`GET /api/search/popular-products`).\n\n"
        "**Query resolution.** The query is normalized with the same function used for catalog aliases "
        "(no model or LLM call). Steps run in order and stop at the first that finds an active product:\n"
        "1. `brand`: a brand alias equals the query; all active products of that brand, even when a "
        "product alias equals it too, so every spelling of a brand name gives the same products. "
        "Products whose alias equals the query (of any brand) are included and come first.\n"
        "2. `alias_exact`: a searchable product alias equals the query.\n"
        "3. `partial`: searchable product aliases containing the query; at most 10 products, "
        "those with the shortest matching alias first.\n"
        "4. `none`. While the server has `SEARCH_SIMILAR_ENABLED=true`, step 5 is tried first:\n"
        "5. `similar`: no alias matched, so up to 5 active products whose display name or a searchable "
        "alias is most similar to the query (character TF-IDF in the server, no model call; similarity at "
        "least `SEARCH_SIMILAR_MIN_SIMILARITY`, default 0.38), most similar first. They are suggestions, "
        "not the product typed.\n\n"
        "A `productId` search skips these steps: `product` with that product when it is active, "
        "otherwise `none` (also for an unknown id, never `404`). `query` is then null.\n\n"
        "**Results.** One row per bar x product, for products on an active bar's current menu board and not sold out. "
        "Rows of products whose alias equals the query come first; within each group, sorted by "
        "`distanceMeters` when lat/lng are sent, otherwise by `menuUpdatedAt` (newest first); "
        "ties by bar name, then product name. At most `limit` rows; `truncated` tells whether more matched. "
        "`options[].discount` is the same as on the bar menu: only discounts that have not ended, and "
        "`priceKrw` is always the list price.\n\n"
        "**Empty results** are `200`: `matchedProducts: []` means the name was not recognized (or the "
        "product of `productId` is gone); `items: []` with products means no bar currently sells them.\n\n"
        "**Search counts.** A `200` search is counted per Seoul date for the popular whiskies: a `product` "
        "search, or an `alias_exact` search with exactly one product, adds 1 for that product and `source`; "
        "`brand`, `partial`, `similar` and several-product searches count nowhere; "
        "a `query` search with `none` adds 1 for the normalized query, unless it contains `@` or 7 or more "
        "digits in a row. Nothing else is stored: no query text for found products, time of day, location, "
        "user or token. A failed count does not fail the search. Calling again counts again, so show a "
        "result already received instead of searching again."
    ),
    responses=error_responses(
        (
            422,
            "`VALIDATION_FAILED`. Format and range errors come together: `productId` `UUID_PARSING`; "
            "`source` `LITERAL_ERROR`; `lat`/`lng` `FLOAT_PARSING`, `GREATER_THAN_EQUAL` or `LESS_THAN_EQUAL`; "
            "`limit` `INT_PARSING`, `GREATER_THAN_EQUAL` or `LESS_THAN_EQUAL`. Then one at a time: `productId` "
            "`EXACTLY_ONE_REQUIRED` (both or neither of `query` and `productId`), `query` `BLANK` (only "
            "spaces), `STRING_TOO_LONG` (over 100 characters after trimming), `lat`/`lng` "
            "`LAT_LNG_REQUIRED_TOGETHER`, `query` `NOT_SEARCHABLE` (nothing left after normalization).",
        ),
    ),
)
def read_search_bars(
    query: Annotated[
        str | None, Query(description="Whisky name; 1-100 characters after trimming. Not with productId.")
    ] = None,
    product_id: Annotated[
        UUID | None, Query(alias="productId", description="One product, from a popular-whisky card. Not with query.")
    ] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90, description="Customer latitude; send with lng")] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180, description="Customer longitude; send with lat")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of result rows")] = 50,
    source: Annotated[
        Literal["input", "recent", "popular"],
        Query(
            description="Where the search started: the search box, a recent search, or a popular-whisky "
            "card. Only for the search counts; the results do not depend on it."
        ),
    ] = "input",
    session: Session = Depends(get_session),
    base_url: str = Depends(get_base_url),
) -> SearchBarsResponse:
    return search_bars(
        session,
        query,
        product_id=product_id,
        lat=lat,
        lng=lng,
        limit=limit,
        source=SearchSource(source),
        base_url=base_url,
    )


@router.get(
    "/popular-products",
    response_model=PopularProductsResponse,
    summary="The popular whiskies for the customer home screen",
    description=(
        "Public; the Authorization header is not read, so every caller gets the same result.\n\n"
        "- Only active products that at least one active bar sells now, not sold out. `barCount` is the "
        "number of those bars, the same bars a `productId` search shows.\n"
        "- Products searched at least 3 times in the last 30 Seoul dates (today included, every `source`) "
        "come first, most searched first; ties by `barCount` (most first), `displayName`, `productId`. "
        "The rest of the list is filled with the other products by `barCount`, `displayName`, `productId`.\n"
        "- Search counts are not sent.\n"
        "- No product sold anywhere is `200` with `items: []`; hide the section then.\n"
        "- Sent with `Cache-Control: public, max-age=600`."
    ),
    responses=error_responses(
        (
            422,
            "`VALIDATION_FAILED`: `limit` `GREATER_THAN_EQUAL`, `LESS_THAN_EQUAL` or `INT_PARSING`.",
        ),
    ),
)
def read_popular_products(
    response: Response,
    limit: Annotated[
        int, Query(ge=1, le=POPULAR_MAX_LIMIT, description="Maximum number of products")
    ] = POPULAR_DEFAULT_LIMIT,
    session: Session = Depends(get_session),
) -> PopularProductsResponse:
    response.headers["Cache-Control"] = "public, max-age=600"
    return popular_products(session, kst_date(datetime.now(timezone.utc)), limit)


@router.get(
    "/nearby-bars",
    response_model=NearbyBarsResponse,
    summary="Every active bar within a radius of the customer",
    description=(
        "Public; the Authorization header is not read, so every caller gets the same result. "
        "The location is used only to compute distance and is not stored; the access log drops `lat` "
        "and `lng` from the URL, so it is not logged either.\n\n"
        "- Only active bars, including bars without a published menu or whose menu has no items.\n"
        "- `distanceMeters` is the haversine distance rounded to whole meters, as in `/api/search/bars`. "
        "A bar is included when that rounded distance is at most `radiusMeters`, a bar exactly at the "
        "radius too, so no item is farther than the radius. The app must not filter again.\n"
        "- All matching bars, with no paging or truncation, nearest first; ties by `barId`.\n"
        "- No bar nearby is `200` with `items: []`."
    ),
    responses=error_responses(
        (
            422,
            "`VALIDATION_FAILED`: `lat` or `lng` `MISSING`; `lat`, `lng` or `radiusMeters` "
            "`GREATER_THAN_EQUAL` or `LESS_THAN_EQUAL` (also for `nan` and `inf`); `FLOAT_PARSING` "
            "(`lat`, `lng`) or `INT_PARSING` (`radiusMeters`, decimals included).",
        ),
    ),
)
def read_nearby_bars(
    lat: Annotated[float, Query(ge=-90, le=90, description="Customer latitude (WGS84)")],
    lng: Annotated[float, Query(ge=-180, le=180, description="Customer longitude (WGS84)")],
    radius_meters: Annotated[
        int, Query(alias="radiusMeters", ge=1, le=MAX_RADIUS_METERS, description="Radius in meters")
    ] = DEFAULT_RADIUS_METERS,
    session: Session = Depends(get_session),
    base_url: str = Depends(get_base_url),
) -> NearbyBarsResponse:
    return find_nearby_bars(session, lat, lng, radius_meters, base_url=base_url)


@router.get(
    "/bar-names",
    response_model=BarNamesResponse,
    summary="Active bars whose name or address contains the query",
    description=(
        "Public; the Authorization header is not read, so every caller gets the same result. Used to "
        "pick one's bar in an owner application and to find a bar on the customer map.\n\n"
        "- The query, trimmed, is matched as a part of the bar's name or address, ignoring letter case. "
        "It is not normalized: spaces count, and `%` and `_` are plain characters.\n"
        "- Only active bars, sorted by name (ties by `barId`), at most `limit`; `truncated` tells "
        "whether more matched. No paging.\n"
        "- `hasOwner` is true when the bar has a current owner; a pending application does not count.\n"
        "- No match is `200` with `items: []`."
    ),
    responses=error_responses(
        (
            422,
            "`VALIDATION_FAILED` with one `fieldErrors` entry: `query` `MISSING`, `BLANK` (only spaces) or "
            "`STRING_TOO_LONG` (over 100 characters after trimming); `limit` `GREATER_THAN_EQUAL`, "
            "`LESS_THAN_EQUAL` or `INT_PARSING`.",
        ),
    ),
)
def read_bar_names(
    query: Annotated[str, Query(description="Part of a bar name or address; 1-100 characters after trimming")],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Maximum number of bars")] = DEFAULT_LIMIT,
    session: Session = Depends(get_session),
    base_url: str = Depends(get_base_url),
) -> BarNamesResponse:
    return search_bar_names(session, query, limit, base_url=base_url)


@router.get(
    "/map-bars",
    response_model=MapBarsResponse,
    summary="Every active bar inside the area shown on the map",
    description=(
        "Public; the Authorization header is not read, so every caller gets the same result. The area "
        "is used only to select bars and is not stored; it is also removed from the server's access log.\n\n"
        "- Active bars with `south <= latitude <= north` and `west <= longitude <= east`, edges included, "
        "with or without a published menu.\n"
        "- All of them, with no paging or truncation, sorted by `barId`.\n"
        f"- `north - south` and `east - west` must each be at most {MAX_SPAN_DEGREES} degrees. Areas "
        "across the antimeridian (`west > east`) are not accepted.\n"
        "- No bar in the area is `200` with `items: []`."
    ),
    responses=error_responses(
        (
            422,
            "`VALIDATION_FAILED`: `south`, `west`, `north` or `east` `MISSING`, `GREATER_THAN_EQUAL` or "
            "`LESS_THAN_EQUAL` (also for `nan` and `inf`) or `FLOAT_PARSING`, possibly several at once. "
            "Then, one at a time: `north` or `east` `BOUNDS_INVERTED` (south above north, west east of "
            f"east), then `north` or `east` `BOUNDS_TOO_LARGE` (wider than {MAX_SPAN_DEGREES} degrees).",
        ),
    ),
)
def read_map_bars(
    south: Annotated[float, Query(ge=-90, le=90, description="Southern edge latitude (WGS84)")],
    west: Annotated[float, Query(ge=-180, le=180, description="Western edge longitude (WGS84)")],
    north: Annotated[float, Query(ge=-90, le=90, description="Northern edge latitude (WGS84)")],
    east: Annotated[float, Query(ge=-180, le=180, description="Eastern edge longitude (WGS84)")],
    session: Session = Depends(get_session),
    base_url: str = Depends(get_base_url),
) -> MapBarsResponse:
    return find_map_bars(session, south, west, north, east, base_url=base_url)
