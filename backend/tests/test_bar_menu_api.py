from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models import BarMenuItem, BarStatus, MenuBoard, MenuBoardEntry, MenuEntryOption
from tests.factories import make_bar, make_brand, make_product, publish_menu

def test_returns_bar_and_menu_in_display_order(client, db_session):
    bar = make_bar(db_session, "Seorosang", latitude="37.477648", longitude="126.963763")
    brand = make_brand(db_session, "GlenDronach")
    twelve = make_product(db_session, brand, "GlenDronach 12", age_years=12)
    fifteen = make_product(db_session, brand, "GlenDronach 15", age_years=15)
    board = publish_menu(
        db_session,
        bar,
        [
            (twelve, "글렌드로낙 12Y", [("잔", None, 13000), ("병", None, 260000)]),
            (fifteen, "글렌드로낙 15Y", [(None, 30, 26000)]),
        ],
        published_at=datetime(2026, 10, 4, 18, 15, tzinfo=timezone(timedelta(hours=9))),
    )

    response = client.get(f"/api/bars/{bar.id}/menu")

    assert response.status_code == 200
    body = response.json()
    assert body["barId"] == str(bar.id)
    assert (body["name"], body["latitude"], body["longitude"]) == ("Seorosang", 37.477648, 126.963763)
    assert body["menuBoardId"] == str(board.id)
    assert body["publishedAt"] == "2026-10-04T09:15:00Z"
    assert [(i["displayName"], i["productId"], i["sortOrder"]) for i in body["items"]] == [
        ("글렌드로낙 12Y", str(twelve.id), 1),
        ("글렌드로낙 15Y", str(fifteen.id), 2),
    ]
    assert [(o["optionLabel"], o["pourMl"], o["priceKrw"]) for o in body["items"][0]["options"]] == [
        ("잔", None, 13000),
        ("병", None, 260000),
    ]
    entry = db_session.get(MenuBoardEntry, body["items"][0]["menuBoardEntryId"])
    assert body["items"][0]["barMenuItemId"] == str(entry.bar_menu_item_id)
    assert db_session.get(MenuEntryOption, body["items"][1]["options"][0]["menuEntryOptionId"]).pour_ml == 30


def test_items_and_options_follow_sort_order_not_insert_order(client, db_session):
    bar = make_bar(db_session)
    brand = make_brand(db_session, "Ardbeg")
    ten = make_product(db_session, brand, "Ardbeg 10")
    uigeadail = make_product(db_session, brand, "Ardbeg Uigeadail")
    board = MenuBoard(bar_id=bar.id, published_at=datetime.now(timezone.utc))
    db_session.add(board)
    db_session.flush()
    # Inserted in reverse: the entry and option written first have the larger sort_order.
    for product, name, sort_order in [(ten, "Ardbeg 10", 2), (uigeadail, "Uigeadail", 1)]:
        item = BarMenuItem(bar_id=bar.id, product_id=product.id)
        db_session.add(item)
        db_session.flush()
        entry = MenuBoardEntry(menu_board_id=board.id, bar_menu_item_id=item.id, display_name=name, sort_order=sort_order)
        db_session.add(entry)
        db_session.flush()
        for label, option_order in [("second", 2), ("first", 1)]:
            db_session.add(
                MenuEntryOption(menu_board_entry_id=entry.id, option_label=label, price_krw=1000, sort_order=option_order)
            )
    db_session.flush()

    items = client.get(f"/api/bars/{bar.id}/menu").json()["items"]

    assert [i["displayName"] for i in items] == ["Uigeadail", "Ardbeg 10"]
    assert [o["optionLabel"] for o in items[1]["options"]] == ["first", "second"]


def test_bar_without_menu_board_returns_empty_menu(client, db_session):
    bar = make_bar(db_session, "Whisky Bokchun")

    response = client.get(f"/api/bars/{bar.id}/menu")

    assert response.status_code == 200
    body = response.json()
    assert (body["menuBoardId"], body["publishedAt"], body["items"]) == (None, None, [])
    assert body["name"] == "Whisky Bokchun"


@pytest.mark.parametrize("bar_id", [str(uuid4()), "not-a-uuid"])
def test_unknown_bar_returns_bar_not_found(client, bar_id):
    response = client.get(f"/api/bars/{bar_id}/menu")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BAR_NOT_FOUND"
    assert response.json()["error"]["details"] == {"barId": bar_id}


def test_inactive_bar_is_hidden_from_anonymous_and_customer(client, db_session, token_for):
    bar = make_bar(db_session, status=BarStatus.INACTIVE)
    customer = token_for("customer")

    anonymous = client.get(f"/api/bars/{bar.id}/menu")
    as_customer = client.get(f"/api/bars/{bar.id}/menu", headers={"Authorization": f"Bearer {customer}"})

    assert anonymous.status_code == as_customer.status_code == 404
    assert anonymous.json()["error"]["code"] == "BAR_NOT_FOUND"


def test_inactive_bar_is_visible_to_operator(client, db_session, token_for):
    bar = make_bar(db_session, status=BarStatus.INACTIVE)
    operator = token_for("operator")

    response = client.get(f"/api/bars/{bar.id}/menu", headers={"Authorization": f"Bearer {operator}"})

    assert response.status_code == 200
    assert response.json()["barId"] == str(bar.id)


def test_invalid_token_is_rejected_even_on_public_route(client, db_session, token_for):
    bar = make_bar(db_session)
    token_for("customer")  # enables temporary auth

    response = client.get(f"/api/bars/{bar.id}/menu", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
