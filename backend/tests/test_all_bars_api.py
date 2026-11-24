"""GET /api/search/all-bars: every active bar, for the app to place on the device (API spec, section 3.19)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import BarStatus
from tests.factories import make_bar, make_bar_photo, make_brand, make_product, publish_menu
from tests.sql_support import recorded_statements
from tests.test_map_bars_api import ITEM_FIELDS
from tests.test_search_api import ANY_AUTHORIZATION

URL = "/api/search/all-bars"


def all_bars(client, headers=None, params=None) -> list[dict]:
    response = client.get(URL, headers=headers, params=params)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"items"}
    assert "cache-control" not in response.headers
    return response.json()["items"]


def names(items) -> list[str]:
    return [item["name"] for item in items]


def test_returns_every_active_bar_with_its_fields(client, db_session):
    published = datetime(2026, 10, 4, 18, 15, 30, 123456, tzinfo=timezone(timedelta(hours=9)))
    with_menu = make_bar(db_session, "Seorosang", latitude="37.477648", longitude="126.963763")
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    publish_menu(db_session, with_menu, [(product, "글렌피딕 12년", [("잔", 30, 17000)])], published_at=published)
    # Far from the first: there is no area or radius.
    without_menu = make_bar(db_session, "Busan Malt", latitude="35.100000", longitude="129.040000")

    assert all_bars(client) == [
        {
            "barId": str(without_menu.id),
            "name": "Busan Malt",
            "address": "Busan Malt address",
            "latitude": 35.1,
            "longitude": 129.04,
            "coverThumbnailUrl": None,
            "menuUpdatedAt": None,
        },
        {
            "barId": str(with_menu.id),
            "name": "Seorosang",
            "address": "Seorosang address",
            "latitude": 37.477648,
            "longitude": 126.963763,
            "coverThumbnailUrl": None,
            "menuUpdatedAt": "2026-10-04T09:15:30.123456Z",
        },
    ]


def test_the_items_are_those_of_map_bars(client, db_session):
    """The same bar has the same item in both APIs (spec 3.19: the 3.13.3 item)."""
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    with_menu = make_bar(db_session, "With Menu", latitude="37.477648", longitude="126.963763")
    publish_menu(db_session, with_menu, [(product, "12", [(None, 30, 1)])])
    empty_menu = make_bar(db_session, "Empty Menu", latitude="37.479874", longitude="126.954512")
    publish_menu(db_session, empty_menu, [])
    with_photo = make_bar(db_session, "With Photo", latitude="37.481000", longitude="126.952000")
    make_bar_photo(db_session, with_photo, 1)
    make_bar(db_session, "No Menu", latitude="37.470000", longitude="126.940000")
    area = {"south": 37.4, "west": 126.9, "north": 37.6, "east": 127.0}

    from_map = client.get("/api/search/map-bars", params=area).json()["items"]
    from_all = all_bars(client)

    assert len(from_all) == 4
    assert {item["barId"]: item for item in from_all} == {item["barId"]: item for item in from_map}
    assert [set(item) for item in from_all] == [ITEM_FIELDS] * 4


def test_inactive_bars_are_left_out_even_for_an_operator(client, db_session, token_for):
    make_bar(db_session, "Open")
    make_bar(db_session, "Closed", status=BarStatus.INACTIVE)
    operator = {"Authorization": f"Bearer {token_for('operator')}"}

    assert names(all_bars(client)) == names(all_bars(client, headers=operator)) == ["Open"]


def test_sorted_by_name_then_bar_id(client, db_session):
    twins = [make_bar(db_session, "Same Name", latitude=f"37.48{i}000") for i in range(3)]
    make_bar(db_session, "Zeta", latitude="37.470000")
    make_bar(db_session, "Alpha", latitude="37.490000")

    items = all_bars(client)

    assert names(items) == ["Alpha", "Same Name", "Same Name", "Same Name", "Zeta"]
    assert [item["barId"] for item in items[1:4]] == sorted(str(bar.id) for bar in twins)


def test_no_active_bar_is_an_empty_list(client, db_session):
    assert all_bars(client) == []

    make_bar(db_session, "Closed", status=BarStatus.INACTIVE)

    assert all_bars(client) == []


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 37.478, "lng": 126.951},
        {"south": 37.47, "west": 126.94, "north": 37.49, "east": 126.97},
        {"limit": 1, "radiusMeters": "x", "unknown": "1"},
    ],
)
def test_query_parameters_are_ignored(client, db_session, params):
    make_bar(db_session, "Near", latitude="37.478000", longitude="126.951000")
    make_bar(db_session, "Far", latitude="35.100000", longitude="129.040000")

    assert all_bars(client, params=params) == all_bars(client) != []


# ---- public: the Authorization header is not read (spec 3.1.5, 3.19) ----


@pytest.mark.parametrize("authorization", ANY_AUTHORIZATION, ids=lambda case: case.__name__)
def test_any_authorization_header_gives_the_guest_result(
    client, db_session, supabase, token_for, monkeypatch, authorization
):
    make_bar(db_session, "Seorosang")
    as_guest = all_bars(client)

    header = authorization(supabase, token_for, monkeypatch)

    assert all_bars(client, headers={"Authorization": header}) == as_guest != []
    assert supabase.jwks.fetches == 0


def test_one_select_whatever_the_number_of_bars(client, db_session):
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    bar = make_bar(db_session, "Bar 0")
    publish_menu(db_session, bar, [(product, "12", [(None, 30, 1)])])
    with recorded_statements(db_session) as with_one_bar:
        all_bars(client)
    for i in range(1, 10):
        bar = make_bar(db_session, f"Bar {i}", latitude=f"37.48{i}000")
        make_bar_photo(db_session, bar, 1)
        if i % 2:
            publish_menu(db_session, bar, [(product, "12", [(None, 30, 1)])])
    with recorded_statements(db_session) as with_ten_bars:
        assert len(all_bars(client)) == 10

    assert len(with_one_bar) == len(with_ten_bars) == 1
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in with_one_bar + with_ten_bars)
