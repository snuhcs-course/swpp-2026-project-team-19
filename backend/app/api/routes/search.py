from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.errors import error_responses
from app.schemas.search import SearchBarsResponse
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
        "1. `alias_exact`: a searchable product alias equals the query.\n"
        "2. `brand`: a brand alias equals the query; all active products of that brand.\n"
        "3. `partial`: searchable product aliases containing the query; at most 10 products, "
        "those with the shortest matching alias first.\n"
        "4. `none`.\n\n"
        "**Results.** One row per bar x product, for products on an active bar's current menu board. "
        "Sorted by `distanceMeters` when lat/lng are sent, otherwise by `menuUpdatedAt` (newest first); "
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
