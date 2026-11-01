from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.errors import error_responses
from app.schemas.search import BarNamesResponse, MapBarsResponse, NearbyBarsResponse, SearchBarsResponse
from app.services.bar_name_search import DEFAULT_LIMIT, MAX_LIMIT, search_bar_names
from app.services.map_bars import MAX_SPAN_DEGREES, find_map_bars
from app.services.nearby_bars import DEFAULT_RADIUS_METERS, MAX_RADIUS_METERS, find_nearby_bars
from app.services.search import search_bars

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get(
    "/bars",
    response_model=SearchBarsResponse,
    summary="Bars currently selling the whisky a query names",
    description=(
        "Public; no token is needed. The location is used only to compute distance and is not stored.\n\n"
        "**Query resolution.** The query is normalized with the same function used for catalog aliases "
        "(no embedding or LLM). Steps run in order and stop at the first that finds an active product:\n"
        "1. `brand`: a brand alias equals the query; all active products of that brand, even when a "
        "product alias equals it too, so every spelling of a brand name gives the same products. "
        "Products whose alias equals the query (of any brand) are included and come first.\n"
        "2. `alias_exact`: a searchable product alias equals the query.\n"
        "3. `partial`: searchable product aliases containing the query; at most 10 products, "
        "those with the shortest matching alias first.\n"
        "4. `none`.\n\n"
        "**Results.** One row per bar x product, for products on an active bar's current menu board. "
        "Rows of products whose alias equals the query come first; within each group, sorted by "
        "`distanceMeters` when lat/lng are sent, otherwise by `menuUpdatedAt` (newest first); "
        "ties by bar name, then product name. At most `limit` rows; `truncated` tells whether more matched.\n\n"
        "**Empty results** are `200`: `matchedProducts: []` means the name was not recognized; "
        "`items: []` with products means no bar currently sells them."
    ),
    responses=error_responses(
        (
            422,
            "`VALIDATION_FAILED` with one `fieldErrors` entry: `query` `MISSING`, `BLANK` (only spaces), "
            "`STRING_TOO_LONG` (over 100 characters after trimming) or `NOT_SEARCHABLE` (nothing left "
            "after normalization); `lat`/`lng` `LAT_LNG_REQUIRED_TOGETHER`, `GREATER_THAN_EQUAL` or "
            "`LESS_THAN_EQUAL`; `limit` `GREATER_THAN_EQUAL` or `LESS_THAN_EQUAL`.",
        ),
    ),
)
def read_search_bars(
    query: Annotated[str, Query(description="Whisky name; 1-100 characters after trimming")],
    lat: Annotated[float | None, Query(ge=-90, le=90, description="Customer latitude; send with lng")] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180, description="Customer longitude; send with lat")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of result rows")] = 50,
    session: Session = Depends(get_session),
) -> SearchBarsResponse:
    return search_bars(session, query, lat=lat, lng=lng, limit=limit)


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
) -> NearbyBarsResponse:
    return find_nearby_bars(session, lat, lng, radius_meters)


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
) -> BarNamesResponse:
    return search_bar_names(session, query, limit)


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
) -> MapBarsResponse:
    return find_map_bars(session, south, west, north, east)
