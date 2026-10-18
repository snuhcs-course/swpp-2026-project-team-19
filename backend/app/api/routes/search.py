# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9); Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-18). Reviewed by Haeul Yang.
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.errors import error_responses
from app.schemas.search import NearbyBarsResponse, SearchBarsResponse
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
        "The location is used only to compute distance and is not stored, but it is part of the URL "
        "and so appears in the server's access log.\n\n"
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
