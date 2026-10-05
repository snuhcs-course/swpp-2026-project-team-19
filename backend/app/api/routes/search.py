from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.search import SearchBarsResponse
from app.services.search import search_bars

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get(
    "/bars",
    response_model=SearchBarsResponse,
    summary="Bars currently selling the whisky a query names",
    description=(
        "Public. Results are bar x product rows, sorted by distance when lat/lng are given, "
        "otherwise by menu update time (newest first). An empty result is still 200."
    ),
)
def read_search_bars(
    query: Annotated[str, Query(description="Whisky name; 1-100 characters after trimming")],
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    session: Session = Depends(get_session),
) -> SearchBarsResponse:
    return search_bars(session, query, lat=lat, lng=lng, limit=limit)
