# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-18). Reviewed by Haeul Yang.
"""GET /api/search/nearby-bars: every active bar within a radius (API spec, section 3.12)."""

import math
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.models import BarStatus
from app.services.search import EARTH_RADIUS_METERS, distance_meters
from tests.factories import make_bar, make_brand, make_product, publish_menu
from tests.test_search_api import ANY_AUTHORIZATION

URL = "/api/search/nearby-bars"
ORIGIN_LAT, ORIGIN_LNG = 37.478, 126.951
ORIGIN = {"lat": ORIGIN_LAT, "lng": ORIGIN_LNG}


def north(meters: float) -> str:
    """The latitude `meters` due north of the origin, with the 6 decimals bars are stored with."""
    return f"{ORIGIN_LAT + math.degrees(meters / EARTH_RADIUS_METERS):.6f}"


def bar_north(db_session, name: str, meters: float, **kwargs):
    return make_bar(db_session, name, latitude=north(meters), longitude=f"{ORIGIN_LNG:.6f}", **kwargs)


def nearby(client, headers=None, **params) -> list[dict]:
    response = client.get(URL, params={**ORIGIN, **params}, headers=headers)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"items"}
    return response.json()["items"]


def names(items) -> list[str]:
    return [item["name"] for item in items]


def test_returns_every_active_bar_in_the_radius_with_its_fields(client, db_session):
    seoul = timezone(timedelta(hours=9))
    published = datetime(2026, 10, 4, 18, 15, 30, 123456, tzinfo=seoul)
    with_menu = bar_north(db_session, "Seorosang", 120)
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    publish_menu(db_session, with_menu, [(product, "글렌피딕 12년", [("잔", 30, 17000)])], published_at=published)
    without_menu = make_bar(db_session, "Malt House", latitude="37.479874", longitude="126.954512")
    bar_north(db_session, "Too Far", 800)

    items = nearby(client)

    assert items == [
        {
            "barId": str(with_menu.id),
            "name": "Seorosang",
            "address": "Seorosang address",
            "latitude": float(with_menu.latitude),
            "longitude": ORIGIN_LNG,
            "distanceMeters": 120,
            "menuUpdatedAt": "2026-10-04T09:15:30.123456Z",
        },
        {
            "barId": str(without_menu.id),
            "name": "Malt House",
            "address": "Malt House address",
            "latitude": 37.479874,
            "longitude": 126.954512,
            "distanceMeters": distance_meters(ORIGIN_LAT, ORIGIN_LNG, 37.479874, 126.954512),
            "menuUpdatedAt": None,
        },
    ]


def test_nearest_first_and_ties_by_bar_id(client, db_session):
    same_place = [bar_north(db_session, f"Same {i}", 200) for i in range(3)]
    bar_north(db_session, "Nearest", 100)
    bar_north(db_session, "Farthest", 300)

    items = nearby(client)

    tied = sorted(str(bar.id) for bar in same_place)
    assert [item["barId"] for item in items[1:4]] == tied
    assert names(items)[0] == "Nearest" and names(items)[4] == "Farthest"
    assert [item["distanceMeters"] for item in items] == [100, 200, 200, 200, 300]


def test_inactive_bars_are_left_out(client, db_session):
    bar_north(db_session, "Open", 100)
    bar_north(db_session, "Closed", 100, status=BarStatus.INACTIVE)

    assert names(nearby(client)) == ["Open"]


def test_bars_without_published_items_are_included(client, db_session):
    never_published = bar_north(db_session, "Never Published", 100)
    all_taken_down = bar_north(db_session, "All Taken Down", 200)
    published = datetime(2026, 10, 4, 9, 15, tzinfo=timezone.utc)
    board = publish_menu(db_session, all_taken_down, [], published_at=published)

    items = nearby(client)

    assert [(item["barId"], item["menuUpdatedAt"]) for item in items] == [
        (str(never_published.id), None),
        (str(all_taken_down.id), "2026-10-04T09:15:00Z"),
    ]
    assert board.entries == []


def test_a_bar_exactly_at_the_radius_is_included(client, db_session):
    bar = make_bar(db_session, "Edge", latitude="37.480123", longitude="126.954321")
    distance = distance_meters(ORIGIN_LAT, ORIGIN_LNG, float(bar.latitude), float(bar.longitude))

    assert names(nearby(client, radiusMeters=distance)) == ["Edge"]
    assert nearby(client, radiusMeters=distance - 1) == []


def test_the_rounded_distance_decides(client, db_session):
    # Due north the haversine distance is the arc of the latitude difference.
    in_by_rounding = make_bar(db_session, "500.2 m", latitude="37.482498")
    out_by_rounding = make_bar(db_session, "500.7 m", latitude="37.482503")
    for bar, low, high in [(in_by_rounding, 500, 500.5), (out_by_rounding, 500.5, 501)]:
        assert low < EARTH_RADIUS_METERS * math.radians(float(bar.latitude) - ORIGIN_LAT) < high

    items = nearby(client, radiusMeters=500)

    assert [(item["name"], item["distanceMeters"]) for item in items] == [("500.2 m", 500)]


def test_the_default_radius_is_500_meters(client, db_session):
    bar_north(db_session, "450 m", 450)
    bar_north(db_session, "550 m", 550)

    assert names(nearby(client)) == ["450 m"]
    assert names(nearby(client, radiusMeters=600)) == ["450 m", "550 m"]


def test_the_largest_radius_is_3000_meters(client, db_session):
    bar_north(db_session, "2990 m", 2990)
    bar_north(db_session, "3010 m", 3010)

    assert names(nearby(client, radiusMeters=3000)) == ["2990 m"]


@pytest.mark.parametrize(
    ("origin", "bar"),
    [
        ((0.0, 179.9995), ("0.000000", "-179.999500")),  # across the antimeridian
        ((89.9995, 0.0), ("89.999500", "180.000000")),  # across the North Pole
    ],
    ids=["antimeridian", "north pole"],
)
def test_bars_across_the_antimeridian_or_a_pole_are_found(client, db_session, origin, bar):
    make_bar(db_session, "Other Side", latitude=bar[0], longitude=bar[1])
    lat, lng = origin

    items = nearby(client, lat=lat, lng=lng)

    assert names(items) == ["Other Side"]
    assert items[0]["distanceMeters"] == distance_meters(lat, lng, float(bar[0]), float(bar[1])) == 111


def test_no_bar_nearby_is_an_empty_list(client, db_session):
    assert nearby(client) == []

    bar_north(db_session, "Far Away", 5000)

    assert nearby(client, radiusMeters=3000) == []


@pytest.mark.parametrize(("lat", "lng"), [(90, 180), (-90, -180)])
def test_the_extreme_coordinates_are_accepted(client, db_session, lat, lng):
    bar_north(db_session, "Seorosang", 100)

    assert nearby(client, lat=lat, lng=lng) == []


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, [("lat", "MISSING"), ("lng", "MISSING")]),
        ({"lat": ORIGIN_LAT}, [("lng", "MISSING")]),
        ({"lng": ORIGIN_LNG}, [("lat", "MISSING")]),
        ({**ORIGIN, "lat": 90.1}, [("lat", "LESS_THAN_EQUAL")]),
        ({**ORIGIN, "lat": -90.1}, [("lat", "GREATER_THAN_EQUAL")]),
        ({**ORIGIN, "lng": 180.1}, [("lng", "LESS_THAN_EQUAL")]),
        ({**ORIGIN, "lng": -180.1}, [("lng", "GREATER_THAN_EQUAL")]),
        ({**ORIGIN, "lat": "nan"}, [("lat", "LESS_THAN_EQUAL")]),
        ({**ORIGIN, "lng": "inf"}, [("lng", "LESS_THAN_EQUAL")]),
        ({**ORIGIN, "lat": "-inf"}, [("lat", "GREATER_THAN_EQUAL")]),
        ({**ORIGIN, "lat": "north"}, [("lat", "FLOAT_PARSING")]),
        ({**ORIGIN, "radiusMeters": 0}, [("radiusMeters", "GREATER_THAN_EQUAL")]),
        ({**ORIGIN, "radiusMeters": 3001}, [("radiusMeters", "LESS_THAN_EQUAL")]),
        ({**ORIGIN, "radiusMeters": "1.5"}, [("radiusMeters", "INT_PARSING")]),
        ({**ORIGIN, "radiusMeters": "far"}, [("radiusMeters", "INT_PARSING")]),
        (
            {"lat": 91, "radiusMeters": 0},
            [("lat", "LESS_THAN_EQUAL"), ("lng", "MISSING"), ("radiusMeters", "GREATER_THAN_EQUAL")],
        ),
    ],
)
def test_invalid_parameters_are_validation_errors(client, params, expected):
    response = client.get(URL, params=params)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert sorted((field["path"], field["code"]) for field in error["fieldErrors"]) == sorted(expected)


# ---- public: the Authorization header is not read (API spec, sections 3.1.5 and 3.12) ----


@pytest.mark.parametrize("authorization", ANY_AUTHORIZATION, ids=lambda case: case.__name__)
def test_any_authorization_header_gives_the_guest_result(
    client, db_session, supabase, token_for, monkeypatch, authorization
):
    bar_north(db_session, "Seorosang", 100)
    as_guest = nearby(client)

    header = authorization(supabase, token_for, monkeypatch)

    assert nearby(client, headers={"Authorization": header}) == as_guest != []


def test_an_operator_does_not_see_inactive_bars_either(client, db_session, token_for):
    bar_north(db_session, "Open", 100)
    bar_north(db_session, "Closed", 100, status=BarStatus.INACTIVE)

    items = nearby(client, headers={"Authorization": f"Bearer {token_for('operator')}"})

    assert names(items) == ["Open"]


# ---- one read-only query, whatever the number of bars ----


def statements_of_a_request(client, db_session) -> list[str]:
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    connection = db_session.connection()
    event.listen(connection, "before_cursor_execute", record)
    try:
        nearby(client, radiusMeters=3000)
    finally:
        event.remove(connection, "before_cursor_execute", record)
    return statements


def test_one_select_whatever_the_number_of_bars(client, db_session):
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    bar = bar_north(db_session, "Bar 0", 100)
    publish_menu(db_session, bar, [(product, "12", [(None, 30, 1)])])
    with_one_bar = statements_of_a_request(client, db_session)

    for i in range(1, 10):
        bar = bar_north(db_session, f"Bar {i}", 100 + i * 50)
        if i % 2:
            publish_menu(db_session, bar, [(product, "12", [(None, 30, 1)])])
    with_ten_bars = statements_of_a_request(client, db_session)

    assert len(with_one_bar) == len(with_ten_bars) == 1
    # Nothing is written: the location is not stored.
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in with_one_bar + with_ten_bars)
