"""The popular whiskies on the customer home screen (API spec 3.17)."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import BarMenuItem, BarStatus, ProductSearchCount, SearchSource
from app.services.popular_products import popular_products
from app.services.request_limits import kst_date
from tests.factories import make_bar, make_brand, make_product, publish_menu
from tests.sql_support import recorded_statements

TODAY = date(2026, 11, 3)
ITEM_FIELDS = {"productId", "displayName", "brandName", "ageYears", "editionName", "barCount"}


def popular(client, **params) -> list[dict]:
    response = client.get("/api/search/popular-products", params=params)
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "public, max-age=600"
    assert set(response.json()) == {"items"}
    return response.json()["items"]


def ranked(db_session, today: date = TODAY, limit: int = 10) -> list[str]:
    return [item.displayName for item in popular_products(db_session, today, limit).items]


def sell(db_session, product, bars: int, *, prefix: str | None = None) -> list:
    """`bars` new active bars, each selling only `product`."""
    made = []
    for i in range(bars):
        bar = make_bar(db_session, f"{prefix or product.display_name} bar {i}")
        publish_menu(db_session, bar, [(product, product.display_name, [(None, 30, 10000)])])
        made.append(bar)
    return made


def searched(db_session, product, count: int, *, day: date = TODAY, source=SearchSource.INPUT) -> None:
    db_session.add(ProductSearchCount(search_date=day, product_id=product.id, source=source, search_count=count))
    db_session.flush()


@pytest.fixture
def brand(db_session):
    return make_brand(db_session, "Brand")


def product(db_session, brand, name: str, **kwargs):
    return make_product(db_session, brand, name, **kwargs)


def test_nothing_sold_anywhere_is_an_empty_list(client, db_session, brand):
    searched(db_session, product(db_session, brand, "Unsold"), 50, day=kst_date(datetime.now(timezone.utc)))

    assert popular(client) == []


def test_every_field_is_sent(client, db_session):
    glenfiddich = make_brand(db_session, "Glenfiddich")
    twelve = make_product(db_session, glenfiddich, "Glenfiddich 12", age_years=12)
    special = make_product(db_session, glenfiddich, "Glenfiddich Fire & Cane", edition_name="Fire & Cane")
    sell(db_session, twelve, 2)
    sell(db_session, special, 1)

    assert popular(client) == [
        {
            "productId": str(twelve.id),
            "displayName": "Glenfiddich 12",
            "brandName": "Glenfiddich",
            "ageYears": 12,
            "editionName": None,
            "barCount": 2,
        },
        {
            "productId": str(special.id),
            "displayName": "Glenfiddich Fire & Cane",
            "brandName": "Glenfiddich",
            "ageYears": None,
            "editionName": "Fire & Cane",
            "barCount": 1,
        },
    ]


def test_without_searches_products_are_ordered_by_bar_count_then_name(db_session, brand):
    for name, bars in (("B", 1), ("A", 1), ("C", 3), ("D", 2)):
        sell(db_session, product(db_session, brand, name), bars)

    assert ranked(db_session) == ["C", "D", "A", "B"]


def test_products_searched_at_least_3_times_come_first_by_searches(db_session, brand):
    sold_widely = product(db_session, brand, "Sold widely")
    twice = product(db_session, brand, "Twice")
    three = product(db_session, brand, "Three times")
    ten = product(db_session, brand, "Ten times")
    sell(db_session, sold_widely, 5)
    for item in (twice, three, ten):
        sell(db_session, item, 1)
    searched(db_session, twice, 2)
    searched(db_session, three, 3)
    searched(db_session, ten, 10)

    # Twice is not popular yet, so it falls back behind Sold widely by barCount.
    assert ranked(db_session) == ["Ten times", "Three times", "Sold widely", "Twice"]


def test_popular_ties_go_by_bar_count_then_name_then_id(db_session, brand):
    items = {name: product(db_session, brand, name) for name in ("B", "A", "C")}
    for name, bars in (("B", 1), ("A", 1), ("C", 2)):
        sell(db_session, items[name], bars)
    for item in items.values():
        searched(db_session, item, 4)
    twin_a = product(db_session, brand, "Twin")
    twin_b = product(db_session, brand, "Twin")
    for twin in (twin_a, twin_b):
        sell(db_session, twin, 1)
        searched(db_session, twin, 4)

    result = popular_products(db_session, TODAY).items

    assert [item.displayName for item in result] == ["C", "A", "B", "Twin", "Twin"]
    assert [item.productId for item in result[3:]] == sorted([twin_a.id, twin_b.id])


def test_searches_of_every_source_in_the_last_30_days_add_up(db_session, brand):
    every_source = product(db_session, brand, "Every source")
    old = product(db_session, brand, "Old")
    window_edge = product(db_session, brand, "Window edge")
    widely = product(db_session, brand, "Widely")
    for item in (every_source, old, window_edge):
        sell(db_session, item, 1)
    sell(db_session, widely, 2)
    for source in SearchSource:
        searched(db_session, every_source, 1, source=source)
    searched(db_session, old, 2, day=TODAY - timedelta(days=29))
    searched(db_session, old, 9, day=TODAY - timedelta(days=30))  # outside the 30 days
    searched(db_session, window_edge, 3, day=TODAY - timedelta(days=29))
    searched(db_session, window_edge, 9, day=TODAY + timedelta(days=1))  # not a date of the window either

    assert ranked(db_session) == ["Every source", "Window edge", "Widely", "Old"]


def test_bar_count_is_the_number_of_bars_a_product_id_search_shows(client, db_session, brand):
    item = product(db_session, brand, "Whisky")
    on_sale, closed, sold_out = sell(db_session, item, 3)
    closed.status = BarStatus.INACTIVE
    db_session.scalar(select(BarMenuItem).where(BarMenuItem.bar_id == sold_out.id)).sold_out_at = datetime.now(
        timezone.utc
    )
    dropped = make_bar(db_session, "Dropped")
    db_session.add(BarMenuItem(bar_id=dropped.id, product_id=item.id))  # sold before, not on the board
    # Another product on the same board does not add a bar.
    other = product(db_session, brand, "Other")
    publish_menu(db_session, make_bar(db_session, "Mixed"), [(item, "1", [(None, 30, 1)]), (other, "2", [(None, 30, 1)])])
    db_session.flush()

    [card, _other] = popular(client)
    search = client.get("/api/search/bars", params={"productId": card["productId"], "source": "popular"}).json()

    assert card["barCount"] == 2
    assert len(search["items"]) == search["matchedProducts"][0]["resultCount"] == card["barCount"]


def test_inactive_products_are_left_out(client, db_session, brand):
    retired = product(db_session, brand, "Retired", is_active=False)
    sell(db_session, retired, 3)
    searched(db_session, retired, 50, day=kst_date(datetime.now(timezone.utc)))

    assert popular(client) == []


def test_limit_defaults_to_10_and_cuts_the_list(client, db_session, brand):
    for i in range(12):
        sell(db_session, product(db_session, brand, f"P{i:02}"), 1)

    assert [item["displayName"] for item in popular(client)] == [f"P{i:02}" for i in range(10)]
    assert len(popular(client, limit=20)) == 12
    assert [item["displayName"] for item in popular(client, limit=1)] == ["P00"]


@pytest.mark.parametrize(
    ("limit", "code"), [(0, "GREATER_THAN_EQUAL"), (21, "LESS_THAN_EQUAL"), ("x", "INT_PARSING"), (1.5, "INT_PARSING")]
)
def test_invalid_limit_returns_validation_failed(client, limit, code):
    response = client.get("/api/search/popular-products", params={"limit": limit})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert [(e["path"], e["code"]) for e in error["fieldErrors"]] == [("limit", code)]
    assert "Cache-Control" not in response.headers


def test_the_authorization_header_is_not_read(client, db_session, brand, supabase):
    sell(db_session, product(db_session, brand, "Whisky"), 1)

    as_guest = popular(client)
    response = client.get("/api/search/popular-products", headers={"Authorization": "Bearer not-a-token"})

    assert (response.status_code, response.json()["items"]) == (200, as_guest)
    assert supabase.jwks.fetches == 0


def test_the_ranking_uses_todays_seoul_date(client, db_session, brand, monkeypatch):
    # 15:30 UTC on 2 November is 00:30 on 3 November in Seoul, so 4 October is the 31st day back.
    class LateEvening(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 2, 15, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr("app.api.routes.search.datetime", LateEvening)
    inside, outside = product(db_session, brand, "Inside"), product(db_session, brand, "Outside")
    sell(db_session, inside, 1)
    sell(db_session, outside, 2)
    searched(db_session, inside, 3, day=date(2026, 10, 5))
    searched(db_session, outside, 3, day=date(2026, 10, 4))

    assert [item["displayName"] for item in popular(client)] == ["Inside", "Outside"]


def test_the_number_of_queries_does_not_grow_with_the_products(client, db_session, brand):
    sell(db_session, product(db_session, brand, "First"), 1)
    db_session.expire_all()
    with recorded_statements(db_session) as with_one:
        popular(client)

    for i in range(10):
        item = product(db_session, make_brand(db_session, f"Brand {i}"), f"Product {i}")
        sell(db_session, item, 2)
        searched(db_session, item, 5)
    db_session.expire_all()
    with recorded_statements(db_session) as with_many:
        assert len(popular(client)) == 10

    assert len(with_one) == len(with_many)
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in with_many)
