"""GET /api/search/map-bars: every active bar inside the map area (API spec, section 3.13)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import BarStatus
from tests.factories import make_bar, make_brand, make_product, publish_menu
from tests.sql_support import recorded_statements
from tests.test_search_api import ANY_AUTHORIZATION

URL = "/api/search/map-bars"
AREA = {"south": 37.47, "west": 126.94, "north": 37.49, "east": 126.97}
ITEM_FIELDS = {"barId", "name", "address", "latitude", "longitude", "menuUpdatedAt"}


def map_bars(client, headers=None, **area) -> list[dict]:
    response = client.get(URL, params={**AREA, **area}, headers=headers)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"items"}
    return response.json()["items"]


def names(items) -> set[str]:
    return {item["name"] for item in items}


def field_errors(client, params) -> list[tuple[str, str]]:
    response = client.get(URL, params=params)
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    return sorted((field["path"], field["code"]) for field in error["fieldErrors"])


def test_returns_every_active_bar_inside_the_area_with_its_fields(client, db_session):
    published = datetime(2026, 10, 4, 18, 15, 30, 123456, tzinfo=timezone(timedelta(hours=9)))
    with_menu = make_bar(db_session, "Seorosang", latitude="37.477648", longitude="126.963763")
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    publish_menu(db_session, with_menu, [(product, "글렌피딕 12년", [("잔", 30, 17000)])], published_at=published)
    without_menu = make_bar(db_session, "Malt House", latitude="37.479874", longitude="126.954512")
    make_bar(db_session, "North of the area", latitude="37.495000", longitude="126.950000")
    make_bar(db_session, "East of the area", latitude="37.480000", longitude="126.975000")

    items = map_bars(client)

    expected = {
        str(with_menu.id): {
            "barId": str(with_menu.id),
            "name": "Seorosang",
            "address": "Seorosang address",
            "latitude": 37.477648,
            "longitude": 126.963763,
            "menuUpdatedAt": "2026-10-04T09:15:30.123456Z",
        },
        str(without_menu.id): {
            "barId": str(without_menu.id),
            "name": "Malt House",
            "address": "Malt House address",
            "latitude": 37.479874,
            "longitude": 126.954512,
            "menuUpdatedAt": None,
        },
    }
    assert items == [expected[bar_id] for bar_id in sorted(expected)]


def test_bars_on_the_edges_and_corners_are_included(client, db_session):
    on_edges = {
        "south edge": ("37.470000", "126.950000"),
        "north edge": ("37.490000", "126.950000"),
        "west edge": ("37.480000", "126.940000"),
        "east edge": ("37.480000", "126.970000"),
        "south-west corner": ("37.470000", "126.940000"),
        "north-east corner": ("37.490000", "126.970000"),
    }
    just_outside = {
        "below south": ("37.469999", "126.950000"),
        "above north": ("37.490001", "126.950000"),
        "west of west": ("37.480000", "126.939999"),
        "east of east": ("37.480000", "126.970001"),
    }
    for name, (latitude, longitude) in {**on_edges, **just_outside}.items():
        make_bar(db_session, name, latitude=latitude, longitude=longitude)

    assert names(map_bars(client)) == set(on_edges)


def test_an_area_of_one_point_finds_the_bar_on_it(client, db_session):
    make_bar(db_session, "Seorosang", latitude="37.477648", longitude="126.963763")

    items = map_bars(client, south=37.477648, north=37.477648, west=126.963763, east=126.963763)

    assert names(items) == {"Seorosang"}


def test_sorted_by_bar_id(client, db_session):
    bars = [make_bar(db_session, f"Bar {i}", latitude=f"37.48{i}000") for i in range(6)]

    items = map_bars(client)

    assert [item["barId"] for item in items] == sorted(str(bar.id) for bar in bars)


def test_inactive_bars_are_left_out_even_for_an_operator(client, db_session, token_for):
    make_bar(db_session, "Open")
    make_bar(db_session, "Closed", status=BarStatus.INACTIVE)
    operator = {"Authorization": f"Bearer {token_for('operator')}"}

    assert names(map_bars(client)) == names(map_bars(client, headers=operator)) == {"Open"}


def test_a_menu_with_no_items_still_has_its_time(client, db_session):
    bar = make_bar(db_session)
    publish_menu(db_session, bar, [], published_at=datetime(2026, 10, 4, 9, 15, tzinfo=timezone.utc))

    assert [item["menuUpdatedAt"] for item in map_bars(client)] == ["2026-10-04T09:15:00Z"]


def test_no_bar_in_the_area_is_an_empty_list(client, db_session):
    assert map_bars(client) == []

    make_bar(db_session, "Far Away", latitude="35.100000", longitude="129.040000")

    assert map_bars(client) == []


def test_every_item_has_exactly_the_spec_fields(client, db_session):
    make_bar(db_session)

    assert [set(item) for item in map_bars(client)] == [ITEM_FIELDS]


# ---- the area size limit (spec 3.13.2) ----


@pytest.mark.parametrize(
    "area",
    [
        # Exactly 0.2 degrees, although the float differences are a little over 0.2.
        {"south": 37.29, "north": 37.49, "west": 126.77, "east": 126.97},
        {"south": 33.3, "north": 33.5, "west": 126.4, "east": 126.6},
        {"south": -90, "north": -89.8, "west": 179.8, "east": 180},
    ],
)
def test_an_area_of_exactly_the_limit_is_accepted(client, area):
    assert map_bars(client, **area) == []


@pytest.mark.parametrize(
    ("area", "expected"),
    [
        ({"south": 37.29, "north": 37.490001}, [("north", "BOUNDS_TOO_LARGE")]),
        ({"west": 126.77, "east": 126.970001}, [("east", "BOUNDS_TOO_LARGE")]),
        # Both too large: north is checked first.
        ({"south": 37.0, "north": 38.0, "west": 126.0, "east": 128.0}, [("north", "BOUNDS_TOO_LARGE")]),
        ({"south": 37.49, "north": 37.47}, [("north", "BOUNDS_INVERTED")]),
        ({"west": 126.97, "east": 126.94}, [("east", "BOUNDS_INVERTED")]),
        # Inverted is checked before the size, and north before east.
        ({"south": 37.49, "north": 37.47, "west": 126.97, "east": 126.94}, [("north", "BOUNDS_INVERTED")]),
        ({"south": 37.0, "north": 38.0, "west": 126.97, "east": 126.94}, [("east", "BOUNDS_INVERTED")]),
        # Across the antimeridian.
        ({"west": 179.9, "east": -179.9}, [("east", "BOUNDS_INVERTED")]),
    ],
)
def test_an_inverted_or_too_large_area_is_rejected(client, area, expected):
    assert field_errors(client, {**AREA, **area}) == expected


# ---- parameter validation (spec 3.13.5) ----


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, [("east", "MISSING"), ("north", "MISSING"), ("south", "MISSING"), ("west", "MISSING")]),
        ({**AREA, "south": None}, [("south", "MISSING")]),
        ({**AREA, "north": 90.1}, [("north", "LESS_THAN_EQUAL")]),
        ({**AREA, "south": -90.1}, [("south", "GREATER_THAN_EQUAL")]),
        ({**AREA, "east": 180.1}, [("east", "LESS_THAN_EQUAL")]),
        ({**AREA, "west": -180.1}, [("west", "GREATER_THAN_EQUAL")]),
        ({**AREA, "north": "nan"}, [("north", "LESS_THAN_EQUAL")]),
        ({**AREA, "east": "inf"}, [("east", "LESS_THAN_EQUAL")]),
        ({**AREA, "west": "-inf"}, [("west", "GREATER_THAN_EQUAL")]),
        ({**AREA, "south": "north"}, [("south", "FLOAT_PARSING")]),
        # Parameter errors come first, all at once; the area checks run only after them.
        ({**AREA, "south": 91, "west": 127.5}, [("south", "LESS_THAN_EQUAL")]),
        (
            {"south": 91, "west": "x"},
            [("east", "MISSING"), ("north", "MISSING"), ("south", "LESS_THAN_EQUAL"), ("west", "FLOAT_PARSING")],
        ),
    ],
)
def test_invalid_parameters_are_validation_errors(client, params, expected):
    params = {key: value for key, value in params.items() if value is not None}

    assert field_errors(client, params) == expected


# ---- public: the Authorization header is not read (spec 3.1.5, 3.13) ----


@pytest.mark.parametrize("authorization", ANY_AUTHORIZATION, ids=lambda case: case.__name__)
def test_any_authorization_header_gives_the_guest_result(
    client, db_session, supabase, token_for, monkeypatch, authorization
):
    make_bar(db_session, "Seorosang")
    as_guest = map_bars(client)

    header = authorization(supabase, token_for, monkeypatch)

    assert map_bars(client, headers={"Authorization": header}) == as_guest != []


def test_one_select_whatever_the_number_of_bars(client, db_session):
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    bar = make_bar(db_session, "Bar 0")
    publish_menu(db_session, bar, [(product, "12", [(None, 30, 1)])])
    with recorded_statements(db_session) as with_one_bar:
        map_bars(client)
    for i in range(1, 10):
        bar = make_bar(db_session, f"Bar {i}", latitude=f"37.48{i}000")
        if i % 2:
            publish_menu(db_session, bar, [(product, "12", [(None, 30, 1)])])
    with recorded_statements(db_session) as with_ten_bars:
        assert len(map_bars(client)) == 10

    assert len(with_one_bar) == len(with_ten_bars) == 1
    # Nothing is written: the area is not stored.
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in with_one_bar + with_ten_bars)
