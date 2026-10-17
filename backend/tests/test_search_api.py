# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9); Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-15, PR #26; 2026-10-17). Reviewed by Haeul Yang.
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import BarMenuItem, BarStatus, MenuBoardEntry
from app.services.search import distance_meters
from tests.auth_support import connection_error, new_signing_key
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

    assert (body["matchType"], body["matchedProducts"], body["items"], body["truncated"]) == ("none", [], [], False)


def test_known_product_without_bars_has_matched_products_but_no_items(client, db_session, glenfiddich):
    body = search(client, query="글렌피딕 15년")

    assert body["matchType"] == "alias_exact"
    assert [(p["displayName"], p["resultCount"]) for p in body["matchedProducts"]] == [("Glenfiddich 15", 0)]
    assert (body["items"], body["truncated"]) == ([], False)


def test_known_brand_without_bars_lists_its_products_but_no_items(client, db_session, glenfiddich):
    body = search(client, query="Glenfiddich")

    assert body["matchType"] == "brand"
    assert [(p["displayName"], p["resultCount"]) for p in body["matchedProducts"]] == [
        ("Glenfiddich 12", 0),
        ("Glenfiddich 15", 0),
        ("Glenfiddich 18", 0),
    ]
    assert (body["items"], body["truncated"]) == ([], False)


def test_inactive_bars_and_items_off_the_current_board_are_excluded(client, db_session, glenfiddich):
    inactive = make_bar(db_session, "Closed Bar", status=BarStatus.INACTIVE)
    publish_menu(db_session, inactive, [(glenfiddich[12], "12", [(None, 30, 1)])])
    dropped = make_bar(db_session, "Dropped Bar")
    db_session.add(BarMenuItem(bar_id=dropped.id, product_id=glenfiddich[12].id))  # sold before, not on the board
    db_session.flush()

    body = search(client, query="Glenfiddich 12")

    assert body["items"] == []
    assert body["matchedProducts"][0]["resultCount"] == 0


@pytest.fixture
def yoichi(db_session):
    # "요이치" is the brand alias and also the alias of the flagship Single Malt, as in the service catalog.
    brand = make_brand(db_session, "Yoichi", aliases=("요이치",))
    return {
        "single malt": make_product(db_session, brand, "Yoichi Single Malt", aliases=("요이치",)),
        "10": make_product(db_session, brand, "Yoichi 10", aliases=("요이치 10년",), age_years=10),
    }


def test_brand_search_lists_the_exact_product_first(client, db_session, yoichi):
    # The 10 is sold nearer, but the customer typed the Single Malt's name.
    near = make_bar(db_session, "Near Bar", latitude="37.488000", longitude="126.951000")
    far = make_bar(db_session, "Far Bar", latitude="37.498000", longitude="126.951000")
    farther = make_bar(db_session, "Farther Bar", latitude="37.508000", longitude="126.951000")
    publish_menu(db_session, near, [(yoichi["10"], "요이치 10", [(None, 30, 1)])])
    publish_menu(db_session, far, [(yoichi["single malt"], "요이치", [(None, 30, 1)])])
    publish_menu(db_session, farther, [(yoichi["single malt"], "요이치", [(None, 30, 1)])])

    body = search(client, query="요이치", **ORIGIN)

    assert body["matchType"] == "brand"
    assert [p["displayName"] for p in body["matchedProducts"]] == ["Yoichi Single Malt", "Yoichi 10"]
    # Exact product rows first, each group nearest first.
    assert [(i["barName"], i["productDisplayName"]) for i in body["items"]] == [
        ("Far Bar", "Yoichi Single Malt"),
        ("Farther Bar", "Yoichi Single Malt"),
        ("Near Bar", "Yoichi 10"),
    ]


def test_brand_search_without_location_keeps_newest_menu_first_within_each_group(client, db_session, yoichi):
    for name, product, age_days in [
        ("Old Malt Bar", "single malt", 3),
        ("New Malt Bar", "single malt", 1),
        ("Newest Ten Bar", "10", 0),
    ]:
        bar = make_bar(db_session, name)
        published_at = T0 - timedelta(days=age_days)
        publish_menu(db_session, bar, [(yoichi[product], "요이치", [(None, 30, 1)])], published_at=published_at)

    items = search(client, query="요이치")["items"]

    assert [i["barName"] for i in items] == ["New Malt Bar", "Old Malt Bar", "Newest Ten Bar"]


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


# ---- result card fields: bar identity, prices, pour sizes, menu update date (API spec, section 3.10.3) ----


def test_options_carry_label_pour_size_and_price_as_written(client, db_session, glenfiddich):
    bar = make_bar(db_session)
    publish_menu(
        db_session,
        bar,
        [(glenfiddich[12], "글렌피딕 12년", [("잔", 30, 17000), (None, 15, 9000), ("병", None, 160000)])],
    )

    (item,) = search(client, query="Glenfiddich 12")["items"]

    # Every option of the entry, with nulls kept as null rather than left out or emptied.
    assert item["options"] == [
        {"optionLabel": "잔", "pourMl": 30, "priceKrw": 17000, "sortOrder": 1},
        {"optionLabel": None, "pourMl": 15, "priceKrw": 9000, "sortOrder": 2},
        {"optionLabel": "병", "pourMl": None, "priceKrw": 160000, "sortOrder": 3},
    ]


def test_options_follow_sort_order_not_insert_order(client, db_session, glenfiddich):
    bar = make_bar(db_session)
    publish_menu(db_session, bar, [(glenfiddich[12], "12", [("병", None, 160000), ("잔", 30, 17000)])])
    entry = db_session.scalars(select(MenuBoardEntry)).one()
    entry.options[0].sort_order = 3  # the bottle, inserted first, now comes last
    db_session.flush()
    # A real request reads the options from the database; drop the list this test session already holds.
    db_session.expire(entry, ["options"])

    (item,) = search(client, query="Glenfiddich 12")["items"]

    assert [(o["optionLabel"], o["sortOrder"]) for o in item["options"]] == [("잔", 2), ("병", 3)]


def test_each_row_carries_its_own_bar_and_menu(client, db_session, glenfiddich):
    seorosang = make_bar(db_session, "Seorosang", latitude="37.477648", longitude="126.963763")
    malt = make_bar(db_session, "Malt House", latitude="37.484102", longitude="126.929815")
    publish_menu(db_session, seorosang, [(glenfiddich[12], "글렌피딕 12Y", [("잔", 30, 17000)])], published_at=T0)
    publish_menu(
        db_session,
        malt,
        [(glenfiddich[12], "Glenfiddich 12 Years", [(None, 15, 9000)])],
        published_at=T0 - timedelta(days=2),
    )

    items = {item["barId"]: item for item in search(client, query="Glenfiddich 12", **ORIGIN)["items"]}

    def card(item):
        return {key: item[key] for key in ("barName", "address", "latitude", "longitude", "menuDisplayName")} | {
            "prices": [o["priceKrw"] for o in item["options"]],
            "menuUpdatedAt": item["menuUpdatedAt"],
        }

    assert card(items[str(seorosang.id)]) == {
        "barName": "Seorosang",
        "address": "Seorosang address",
        "latitude": 37.477648,
        "longitude": 126.963763,
        "menuDisplayName": "글렌피딕 12Y",
        "prices": [17000],
        "menuUpdatedAt": "2026-10-04T09:15:00Z",
    }
    assert card(items[str(malt.id)]) == {
        "barName": "Malt House",
        "address": "Malt House address",
        "latitude": 37.484102,
        "longitude": 126.929815,
        "menuDisplayName": "Glenfiddich 12 Years",
        "prices": [9000],
        "menuUpdatedAt": "2026-10-02T09:15:00Z",
    }
    assert {item["productDisplayName"] for item in items.values()} == {"Glenfiddich 12"}
    assert all(isinstance(item["distanceMeters"], int) for item in items.values())


def test_menu_updated_at_is_sent_in_utc(client, db_session, glenfiddich):
    seoul = timezone(timedelta(hours=9))
    published = datetime(2026, 10, 4, 18, 15, 30, 123456, tzinfo=seoul)
    publish_menu(db_session, make_bar(db_session), [(glenfiddich[12], "12", [(None, 30, 1)])], published_at=published)

    (item,) = search(client, query="Glenfiddich 12")["items"]

    assert item["menuUpdatedAt"] == "2026-10-04T09:15:30.123456Z"


def test_menu_updated_at_follows_the_latest_publish(client, db_session, glenfiddich):
    board = publish_menu(db_session, make_bar(db_session), [(glenfiddich[12], "12", [(None, 30, 1)])], published_at=T0)
    board.published_at = T0 + timedelta(days=7)  # the board is republished in place
    db_session.flush()

    (item,) = search(client, query="Glenfiddich 12")["items"]

    assert item["menuUpdatedAt"] == "2026-10-11T09:15:00Z"


# ---- guest search and tokens (API spec, sections 3.1.5 and 3.10) ----


def expired_supabase_token(supabase, token_for, monkeypatch):
    now = int(time.time())
    return f"Bearer {supabase.token(iat=now - 3600, exp=now - 60)}"


def supabase_token_signed_by_another_key(supabase, token_for, monkeypatch):
    return f"Bearer {supabase.token(key=new_signing_key(supabase.key.kid))}"


def malformed_token(supabase, token_for, monkeypatch):
    return "Bearer not-a-jwt"


def temporary_token_after_temporary_login_is_off(supabase, token_for, monkeypatch):
    token = token_for("customer")
    monkeypatch.setenv("TEMP_AUTH_ENABLED", "false")
    return f"Bearer {token}"


def supabase_token_without_supabase_url(supabase, token_for, monkeypatch):
    token = supabase.token()
    monkeypatch.delenv("SUPABASE_URL")
    return f"Bearer {token}"


def supabase_token_while_signing_keys_are_out_of_reach(supabase, token_for, monkeypatch):
    supabase.jwks.error = connection_error()
    return f"Bearer {supabase.token()}"


def valid_supabase_token(supabase, token_for, monkeypatch):
    return f"Bearer {supabase.token()}"


def another_scheme(supabase, token_for, monkeypatch):
    return "Basic dXNlcjpwYXNz"


@pytest.mark.parametrize(
    "authorization",
    [
        expired_supabase_token,
        supabase_token_signed_by_another_key,
        malformed_token,
        temporary_token_after_temporary_login_is_off,
        supabase_token_without_supabase_url,
        supabase_token_while_signing_keys_are_out_of_reach,
        valid_supabase_token,
        another_scheme,
    ],
    ids=lambda case: case.__name__,
)
def test_guest_search_ignores_any_token(
    client, db_session, glenfiddich, supabase, token_for, monkeypatch, authorization
):
    bar = make_bar(db_session, "Seorosang")
    publish_menu(db_session, bar, [(glenfiddich[12], "글렌피딕 12Y", [("잔", None, 12000)])], published_at=T0)
    as_guest = client.get("/api/search/bars", params={"query": "글렌피딕"})

    header = authorization(supabase, token_for, monkeypatch)
    with_token = client.get("/api/search/bars", params={"query": "글렌피딕"}, headers={"Authorization": header})

    assert as_guest.status_code == with_token.status_code == 200
    assert with_token.json() == as_guest.json()
    assert with_token.json()["items"]
    # The header is not even read: no signing keys were looked up.
    assert supabase.jwks.fetches == 0
