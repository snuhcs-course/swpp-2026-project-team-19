"""Active bars inside the area shown on the customer's map (API spec, section 3.13), and every
active bar for the app to place on the device (section 3.19).

Every bar inside the area, edges included, in one query and without truncation: the size limit on
the area keeps the response small instead. Areas across the antimeridian are rejected; the service
is in Korea. Both APIs build their items here, so the two responses cannot differ for the same bar.
"""

from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.core.errors import validation_failed
from app.models import Bar
from app.schemas.search import AllBarsResponse, MapBarItem, MapBarsResponse
from app.services.bar_photo_links import cover_thumbnail_url
from app.services.nearby_bars import active_bars_with_menu_time

MAX_SPAN_DEGREES = 0.2
# Coordinates arrive as floats, whose differences are not exact: 37.49 - 37.29 is
# 0.20000000000000284. A width of 0.2 degrees must still pass, so allow far less than a meter
# (1e-9 degrees is about 0.1 mm).
SPAN_TOLERANCE_DEGREES = 1e-9


def validate_area(south: float, west: float, north: float, east: float) -> None:
    """Checks FastAPI's Query constraints cannot express, in the spec's order (3.13.5)."""
    if south > north:
        raise validation_failed("north", "BOUNDS_INVERTED", "북쪽 경계는 남쪽 경계보다 남쪽에 있을 수 없습니다.")
    if west > east:
        raise validation_failed("east", "BOUNDS_INVERTED", "동쪽 경계는 서쪽 경계보다 서쪽에 있을 수 없습니다.")
    too_large = "지도 영역이 너무 넓습니다. 지도를 확대해 주세요."
    if north - south > MAX_SPAN_DEGREES + SPAN_TOLERANCE_DEGREES:
        raise validation_failed("north", "BOUNDS_TOO_LARGE", too_large)
    if east - west > MAX_SPAN_DEGREES + SPAN_TOLERANCE_DEGREES:
        raise validation_failed("east", "BOUNDS_TOO_LARGE", too_large)


def find_map_bars(
    session: Session, south: float, west: float, north: float, east: float, *, base_url: str
) -> MapBarsResponse:
    validate_area(south, west, north, east)
    query = (
        active_bars_with_menu_time()
        .where(Bar.latitude.between(south, north), Bar.longitude.between(west, east))
        .order_by(Bar.id)
    )
    return MapBarsResponse(items=map_bar_items(session, query, base_url))


def find_all_bars(session: Session, *, base_url: str) -> AllBarsResponse:
    """Every active bar, by name, then id (spec 3.19). It takes no location: the app computes
    distance, radius and map area on the device."""
    query = active_bars_with_menu_time().order_by(Bar.name, Bar.id)
    return AllBarsResponse(items=map_bar_items(session, query, base_url))


def map_bar_items(session: Session, query: Select, base_url: str) -> list[MapBarItem]:
    """The items of a query from `active_bars_with_menu_time`, in its order."""
    return [
        MapBarItem(
            barId=bar_id,
            name=name,
            address=address,
            latitude=float(latitude),
            longitude=float(longitude),
            coverThumbnailUrl=cover_thumbnail_url(cover_id, base_url),
            menuUpdatedAt=published_at,
        )
        for bar_id, name, address, latitude, longitude, published_at, cover_id in session.execute(query)
    ]
