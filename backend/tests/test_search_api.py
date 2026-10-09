# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9). Reviewed by Haeul Yang.
from datetime import datetime, timedelta, timezone

import pytest

from app.models import BarMenuItem, BarStatus
from app.services.search import distance_meters
from tests.factories import make_bar, make_brand, make_product, publish_menu

T0 = datetime(2026, 10, 4, 9, 15, tzinfo=timezone.utc)
ORIGIN = {"lat": 37.478, "lng": 126.951}


@pytest.fixture
def glenfiddich(db_session):
    brand = make_brand(db_session, "Glenfiddich", aliases=("글렌피딕",))
    return {
        age: make_product(db_session, brand, f"Glenfiddich {age}", aliases=(f"글렌피딕 {age}년",), age_years=age)
        for age in (12, 15, 18)
    }


def search(client, **params):
    response = client.get("/api/search/bars", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_exact_alias_search_returns_bar_rows(client, db_session, glenfiddich):
    bar = make_bar(db_session, "Seorosang", latitude="37.477648", longitude="126.963763")
    publish_menu(
        db_session,
        bar,
        [(glenfiddich[12], "글렌피딕 12Y", [("잔", None, 12000), ("병", None, 200000)])],
        published_at=T0,
    )

    body = search(client, query="  글렌피딕 12년 ")

    assert (body["query"], body["matchType"], body["truncated"]) == ("글렌피딕 12년", "alias_exact", False)
    assert body["matchedProducts"] == [
        {
            "productId": str(glenfiddich[12].id),
            "displayName": "Glenfiddich 12",
            "brandName": "Glenfiddich",
            "ageYears": 12,
            "editionName": None,
            "resultCount": 1,
        }
    ]
    assert body["items"] == [
        {
            "barId": str(bar.id),
            "barName": "Seorosang",
            "address": "Seorosang address",
            "latitude": 37.477648,
            "longitude": 126.963763,
            "distanceMeters": None,
            "productId": str(glenfiddich[12].id),
            "productDisplayName": "Glenfiddich 12",
            "menuDisplayName": "글렌피딕 12Y",
            "options": [
                {"optionLabel": "잔", "pourMl": None, "priceKrw": 12000, "sortOrder": 1},
                {"optionLabel": "병", "pourMl": None, "priceKrw": 200000, "sortOrder": 2},
            ],
            "menuUpdatedAt": "2026-10-04T09:15:00Z",
        }
    ]


def test_brand_search_merges_products_and_counts_rows(client, db_session, glenfiddich):
    first = make_bar(db_session, "A Bar")
    second = make_bar(db_session, "B Bar")
    publish_menu(db_session, first, [(glenfiddich[12], "12", [(None, 30, 1)]), (glenfiddich[18], "18", [(None, 30, 1)])])
    publish_menu(db_session, second, [(glenfiddich[12], "12", [(None, 30, 1)])])

    body = search(client, query="글렌피딕")

    assert body["matchType"] == "brand"
    assert [(p["displayName"], p["resultCount"]) for p in body["matchedProducts"]] == [
        ("Glenfiddich 12", 2),
        ("Glenfiddich 15", 0),
        ("Glenfiddich 18", 1),
    ]
    assert len(body["items"]) == 3


def test_unknown_product_has_no_matched_products(client, db_session, glenfiddich):
    body = search(client, query="없는위스키")

    assert (body["matchType"], body["matchedProducts"], body["items"]) == ("none", [], [])


def test_known_product_without_bars_has_matched_products_but_no_items(client, db_session, glenfiddich):
    body = search(client, query="글렌피딕 15년")

    assert [p["resultCount"] for p in body["matchedProducts"]] == [0]
    assert body["items"] == []


def test_inactive_bars_and_items_off_the_current_board_are_excluded(client, db_session, glenfiddich):
    inactive = make_bar(db_session, "Closed Bar", status=BarStatus.INACTIVE)
    publish_menu(db_session, inactive, [(glenfiddich[12], "12", [(None, 30, 1)])])
    dropped = make_bar(db_session, "Dropped Bar")
    db_session.add(BarMenuItem(bar_id=dropped.id, product_id=glenfiddich[12].id))  # sold before, not on the board
    db_session.flush()

    body = search(client, query="Glenfiddich 12")

    assert body["items"] == []
    assert body["matchedProducts"][0]["resultCount"] == 0


def test_without_location_newest_menu_comes_first_then_bar_name(client, db_session, glenfiddich):
    for name, age_days in [("Old Bar", 3), ("Bar B", 1), ("Bar A", 1)]:
        bar = make_bar(db_session, name)
        publish_menu(db_session, bar, [(glenfiddich[12], "12", [(None, 30, 1)])], published_at=T0 - timedelta(days=age_days))

    body = search(client, query="Glenfiddich 12")

    assert [i["barName"] for i in body["items"]] == ["Bar A", "Bar B", "Old Bar"]


def test_with_location_nearest_bar_comes_first(client, db_session, glenfiddich):
    # 0.01 degrees of latitude is about 1.1 km.
    far = make_bar(db_session, "Far Bar", latitude="37.498000", longitude="126.951000")
    near = make_bar(db_session, "Near Bar", latitude="37.488000", longitude="126.951000")
    publish_menu(db_session, far, [(glenfiddich[12], "12", [(None, 30, 1)])], published_at=T0 + timedelta(days=1))
    publish_menu(db_session, near, [(glenfiddich[12], "12", [(None, 30, 1)])], published_at=T0)

    items = search(client, query="Glenfiddich 12", **ORIGIN)["items"]

    assert [(i["barName"], i["distanceMeters"]) for i in items] == [("Near Bar", 1112), ("Far Bar", 2224)]


def test_limit_truncates_but_result_count_covers_all_rows(client, db_session, glenfiddich):
    for n in range(3):
        publish_menu(db_session, make_bar(db_session, f"Bar {n}"), [(glenfiddich[12], "12", [(None, 30, 1)])])

    body = search(client, query="Glenfiddich 12", limit=2)

    assert (len(body["items"]), body["truncated"]) == (2, True)
    assert body["matchedProducts"][0]["resultCount"] == 3


def test_query_of_exactly_100_characters_after_trimming_is_accepted(client, db_session):
    assert search(client, query=f"  {'가' * 100}  ")["matchType"] == "none"


@pytest.mark.parametrize(
    ("params", "path", "code"),
    [
        ({}, "query", "MISSING"),
        ({"query": "   "}, "query", "BLANK"),
        ({"query": "가" * 101}, "query", "STRING_TOO_LONG"),
        ({"query": "!!!"}, "query", "NOT_SEARCHABLE"),
        ({"query": "x", "lat": 37.5}, "lng", "LAT_LNG_REQUIRED_TOGETHER"),
        ({"query": "x", "lng": 127.0}, "lat", "LAT_LNG_REQUIRED_TOGETHER"),
        ({"query": "x", "lat": 91, "lng": 0}, "lat", "LESS_THAN_EQUAL"),
        ({"query": "x", "lat": 0, "lng": -181}, "lng", "GREATER_THAN_EQUAL"),
        ({"query": "x", "limit": 0}, "limit", "GREATER_THAN_EQUAL"),
        ({"query": "x", "limit": 101}, "limit", "LESS_THAN_EQUAL"),
    ],
)
def test_invalid_input_returns_validation_failed(client, params, path, code):
    response = client.get("/api/search/bars", params=params)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert [(e["path"], e["code"]) for e in error["fieldErrors"]] == [(path, code)]


def test_distance_meters():
    assert distance_meters(37.478, 126.951, 37.478, 126.951) == 0
    # Seoul City Hall to Gangnam Station is about 8.8 km.
    assert 8_700 < distance_meters(37.5663, 126.9779, 37.4979, 127.0276) < 8_900
