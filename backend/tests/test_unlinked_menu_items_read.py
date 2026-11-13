"""Menu items without a product as the read APIs see them (API spec 3.9, 3.10.2, 3.14.8, 3.14.9 and 3.17).

An unlinked whisky and a non-whisky menu are on the bar's menu right away, with no product, brand or
category, but customer search and popular whiskies only see items linked to a product.
"""

from datetime import date

import pytest

from app.models import MenuItemKind, ProductSearchCount, SearchSource
from app.services.popular_products import popular_products
from tests.factories import make_bar, make_brand, make_product, publish_menu

TODAY = date(2026, 11, 13)


@pytest.fixture
def glenfiddich(db_session):
    return make_product(
        db_session, make_brand(db_session, "Glenfiddich", aliases=("글렌피딕",)), "Glenfiddich 12", aliases=("글렌피딕 12년",)
    )


@pytest.fixture
def menu(db_session, glenfiddich):
    """A bar selling Glenfiddich 12 (linked), an unlinked whisky and a highball (other)."""
    bar = make_bar(db_session, "Seorosang")
    board = publish_menu(
        db_session,
        bar,
        [
            (glenfiddich, "글렌피딕 12년", [("잔", 30, 17000)]),
            (MenuItemKind.WHISKY, "글렌알라키 10 CS 배치 11", [(None, 30, 26000)]),
            (MenuItemKind.OTHER, "하이볼", [(None, None, 12000)]),
        ],
    )
    db_session.refresh(board)
    return bar, board


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


def test_the_menu_shows_unlinked_items_without_product_fields(client, menu, glenfiddich):
    bar, _ = menu

    items = client.get(f"/api/bars/{bar.id}/menu").json()["items"]

    assert [
        (i["displayName"], i["productId"], i["productName"], i["brandId"], i["brandName"], i["category"], i["kind"])
        for i in items
    ] == [
        ("글렌피딕 12년", str(glenfiddich.id), "Glenfiddich 12", str(glenfiddich.brand_id), "Glenfiddich", "whisky", "whisky"),
        ("글렌알라키 10 CS 배치 11", None, None, None, None, None, "whisky"),
        ("하이볼", None, None, None, None, None, "other"),
    ]
    assert [i["options"][0]["priceKrw"] for i in items] == [17000, 26000, 12000]
    assert items[2]["options"][0]["pourMl"] is None


@pytest.mark.parametrize("query", ["글렌알라키", "하이볼", "글렌피딕"])
def test_search_finds_only_linked_items(client, menu, glenfiddich, query):
    bar, _ = menu

    body = client.get("/api/search/bars", params={"query": query}).json()

    found = [(item["barId"], item["productId"]) for item in body["items"]]
    assert found == ([(str(bar.id), str(glenfiddich.id))] if query == "글렌피딕" else [])


def test_popular_whiskies_count_only_linked_items(db_session, menu, glenfiddich):
    db_session.add(
        ProductSearchCount(search_date=TODAY, product_id=glenfiddich.id, source=SearchSource.INPUT, search_count=5)
    )
    db_session.flush()

    items = popular_products(db_session, TODAY, 10).items

    assert [(item.productId, item.barCount) for item in items] == [(glenfiddich.id, 1)]


def test_an_unlinked_item_can_be_marked_sold_out(client, menu, operator):
    bar, board = menu
    unlinked = board.entries[1].bar_menu_item_id

    response = client.put(
        f"/api/bars/{bar.id}/menu/items/{unlinked}/sold-out", json={"soldOut": True}, headers=operator
    )

    assert response.status_code == 200, response.text
    assert [(i["displayName"], i["soldOut"]) for i in response.json()["items"]] == [
        ("글렌피딕 12년", False),
        ("글렌알라키 10 CS 배치 11", True),
        ("하이볼", False),
    ]
    # Customers do not get it while it is sold out (spec 3.14.8).
    assert [i["displayName"] for i in client.get(f"/api/bars/{bar.id}/menu").json()["items"]] == [
        "글렌피딕 12년",
        "하이볼",
    ]
