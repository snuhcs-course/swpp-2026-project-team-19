"""Active bars within a radius of the customer (API spec, section 3.12).

One query reads the bars inside a latitude/longitude box around the circle, and the haversine
distance then keeps those inside the circle. The box only narrows what the database returns, so it
may be larger than needed but never smaller: near a pole or across the antimeridian it drops the
longitude limit instead of splitting the range. There are few bars, so no spatial index is used.
"""

import math
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Bar, BarStatus, MenuBoard
from app.schemas.search import NearbyBarItem, NearbyBarsResponse
from app.services.search import EARTH_RADIUS_METERS, distance_meters

DEFAULT_RADIUS_METERS = 500
MAX_RADIUS_METERS = 3000
# A bar is in when its distance rounded to whole meters is within the radius, so it can be up to
# 0.5 m outside; the box is drawn 1 m wider so that such a bar is not cut off before the check.
BOX_MARGIN_METERS = 1


@dataclass(frozen=True)
class BoundingBox:
    min_lat: float
    max_lat: float
    # None when the box would contain a pole or cross the antimeridian: no longitude limit then.
    min_lng: float | None
    max_lng: float | None


def bounding_box(lat: float, lng: float, radius_meters: float) -> BoundingBox:
    """A box containing every point within radius_meters (plus the margin) of lat/lng."""
    angle = (radius_meters + BOX_MARGIN_METERS) / EARTH_RADIUS_METERS
    min_lat = max(lat - math.degrees(angle), -90.0)
    max_lat = min(lat + math.degrees(angle), 90.0)
    # The widest longitude difference on a circle of this angular radius (it lies slightly
    # poleward of lat). When sin(angle) >= cos(lat) the circle contains a pole.
    ratio = math.sin(angle) / math.cos(math.radians(lat)) if abs(lat) < 90 else math.inf
    if ratio >= 1:
        return BoundingBox(min_lat, max_lat, None, None)
    d_lng = math.degrees(math.asin(ratio))
    if lng - d_lng < -180 or lng + d_lng > 180:
        return BoundingBox(min_lat, max_lat, None, None)
    return BoundingBox(min_lat, max_lat, lng - d_lng, lng + d_lng)


def active_bars_with_menu_time() -> Select:
    """(id, name, address, latitude, longitude, published_at or None) of every active bar; callers
    add the area. Also used by the map-area query (spec 3.13)."""
    return (
        select(Bar.id, Bar.name, Bar.address, Bar.latitude, Bar.longitude, MenuBoard.published_at)
        .outerjoin(MenuBoard, MenuBoard.bar_id == Bar.id)  # at most one board per bar
        .where(Bar.status == BarStatus.ACTIVE)
    )


def find_nearby_bars(
    session: Session, lat: float, lng: float, radius_meters: int = DEFAULT_RADIUS_METERS
) -> NearbyBarsResponse:
    box = bounding_box(lat, lng, radius_meters)
    query = active_bars_with_menu_time().where(Bar.latitude.between(box.min_lat, box.max_lat))
    if box.min_lng is not None:
        query = query.where(Bar.longitude.between(box.min_lng, box.max_lng))

    items = []
    for bar_id, name, address, bar_lat, bar_lng, published_at in session.execute(query):
        distance = distance_meters(lat, lng, float(bar_lat), float(bar_lng))
        if distance <= radius_meters:
            items.append(
                NearbyBarItem(
                    barId=bar_id,
                    name=name,
                    address=address,
                    latitude=float(bar_lat),
                    longitude=float(bar_lng),
                    distanceMeters=distance,
                    menuUpdatedAt=published_at,
                )
            )
    items.sort(key=lambda item: (item.distanceMeters, str(item.barId)))
    return NearbyBarsResponse(items=items)
