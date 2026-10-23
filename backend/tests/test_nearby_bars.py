"""The bounding box that narrows the nearby-bar query (API spec, section 3.12).

The box may be larger than the circle but must never cut off a point inside it, or a bar within
the radius would be missing from the response.
"""

import math

import pytest

from app.services.nearby_bars import BOX_MARGIN_METERS, bounding_box
from app.services.search import EARTH_RADIUS_METERS


def destination(lat: float, lng: float, meters: float, bearing_degrees: float) -> tuple[float, float]:
    """The point `meters` away from lat/lng along a great circle with the given initial bearing."""
    phi1, lambda1 = math.radians(lat), math.radians(lng)
    delta, theta = meters / EARTH_RADIUS_METERS, math.radians(bearing_degrees)
    phi2 = math.asin(math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta))
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1), math.cos(delta) - math.sin(phi1) * math.sin(phi2)
    )
    lng2 = (math.degrees(lambda2) + 540) % 360 - 180
    return math.degrees(phi2), lng2


def inside(box, lat: float, lng: float) -> bool:
    if not box.min_lat <= lat <= box.max_lat:
        return False
    return box.min_lng is None or box.min_lng <= lng <= box.max_lng


@pytest.mark.parametrize("lat", [0.0, 37.478, -33.9, 70.0, 85.0, -88.0])
@pytest.mark.parametrize("radius", [1, 500, 3000])
def test_every_point_of_the_circle_is_inside_the_box(lat, radius):
    box = bounding_box(lat, 126.951, radius)

    outside = [
        bearing
        for bearing in range(0, 360, 3)
        if not inside(box, *destination(lat, 126.951, radius, bearing))
    ]

    assert outside == []


def test_the_box_is_not_much_larger_than_the_circle():
    lat, lng = 37.478, 126.951
    box = bounding_box(lat, lng, 500)

    angle = math.degrees((500 + BOX_MARGIN_METERS) / EARTH_RADIUS_METERS)
    assert box.max_lat - lat == pytest.approx(angle)
    assert lat - box.min_lat == pytest.approx(angle)
    assert box.max_lng - lng == pytest.approx(angle / math.cos(math.radians(lat)), rel=1e-6)
    assert lng - box.min_lng == pytest.approx(angle / math.cos(math.radians(lat)), rel=1e-6)


@pytest.mark.parametrize(
    ("lat", "lng"),
    [
        (89.99, 0.0),  # 1.1 km from the North Pole: the circle contains it
        (90.0, 180.0),
        (-90.0, -180.0),
        (0.0, 179.999),  # the circle crosses the antimeridian
        (0.0, -179.999),
    ],
)
def test_no_longitude_limit_around_a_pole_or_across_the_antimeridian(lat, lng):
    box = bounding_box(lat, lng, 3000)

    assert (box.min_lng, box.max_lng) == (None, None)
    assert -90 <= box.min_lat <= lat <= box.max_lat <= 90
