from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models import BarMenuItem, BarStatus, MenuBoard, MenuBoardEntry, MenuEntryOption, User, UserType
from tests.auth_support import connection_error
from tests.factories import make_bar, make_brand, make_product, publish_menu
from tests.sql_support import recorded_statements

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


def test_board_with_every_item_removed_keeps_its_id_and_date(client, db_session):
    # Spec 3.9.1: the app tells "no menu yet" (null id) from "nothing on sale now" (id, no items).
    bar = make_bar(db_session)
    board = publish_menu(db_session, bar, [], published_at=datetime(2026, 10, 4, 9, 15, tzinfo=timezone.utc))

    body = client.get(f"/api/bars/{bar.id}/menu").json()

    assert (body["menuBoardId"], body["publishedAt"], body["items"]) == (str(board.id), "2026-10-04T09:15:00Z", [])


def test_missing_phone_is_null(client, db_session):
    bar = make_bar(db_session)
    bar.phone = None
    db_session.flush()

    body = client.get(f"/api/bars/{bar.id}/menu").json()

    assert body["phone"] is None
    assert {"name", "address", "latitude", "longitude"} <= body.keys()


@pytest.mark.parametrize("bar_id", [str(uuid4()), "not-a-uuid"])
def test_unknown_bar_returns_bar_not_found(client, bar_id):
    response = client.get(f"/api/bars/{bar_id}/menu")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BAR_NOT_FOUND"
    assert response.json()["error"]["details"] == {"barId": bar_id}


@pytest.mark.parametrize(
    "spelling",
    [
        str.upper,
        lambda bar_id: bar_id.replace("-", ""),
        lambda bar_id: f"{{{bar_id}}}",
        lambda bar_id: f"urn:uuid:{bar_id}",
    ],
    ids=["upper case", "no hyphens", "braces", "urn prefix"],
)
def test_other_spellings_of_the_uuid_find_the_bar(client, db_session, spelling):
    # Kept on purpose: any text Python reads as this UUID names the bar. The response always
    # gives the canonical form, which is what the app keeps.
    bar = make_bar(db_session)

    response = client.get(f"/api/bars/{spelling(str(bar.id))}/menu")

    assert response.status_code == 200
    assert response.json()["barId"] == str(bar.id)


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


# ---- a token the server cannot check counts as no token here (API spec, section 3.1.5) ----


def supabase_url_missing(supabase, token_for, monkeypatch):
    token = supabase.token()
    monkeypatch.delenv("SUPABASE_URL")
    return token


def signing_keys_out_of_reach(supabase, token_for, monkeypatch):
    supabase.jwks.error = connection_error()
    return supabase.token()


def temporary_login_misconfigured(supabase, token_for, monkeypatch):
    token = token_for("customer")
    monkeypatch.setenv("TEMP_AUTH_USER_TYPE", "admin")
    return token


@pytest.mark.parametrize(
    "uncheckable",
    [supabase_url_missing, signing_keys_out_of_reach, temporary_login_misconfigured],
    ids=lambda case: case.__name__,
)
def test_uncheckable_token_reads_the_menu_as_a_guest(
    client, db_session, supabase, token_for, monkeypatch, uncheckable
):
    bar = make_bar(db_session)
    as_guest = client.get(f"/api/bars/{bar.id}/menu")

    token = uncheckable(supabase, token_for, monkeypatch)
    response = client.get(f"/api/bars/{bar.id}/menu", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == as_guest.json()


def test_operator_with_an_uncheckable_token_sees_only_what_a_guest_sees(client, db_session, supabase):
    bar = make_bar(db_session, status=BarStatus.INACTIVE)
    db_session.add(User(auth_subject="operator-subject", user_type=UserType.OPERATOR))
    db_session.flush()
    supabase.jwks.error = connection_error()

    response = client.get(
        f"/api/bars/{bar.id}/menu", headers={"Authorization": f"Bearer {supabase.token(sub='operator-subject')}"}
    )

    assert (response.status_code, response.json()["error"]["code"]) == (404, "BAR_NOT_FOUND")


def test_protected_routes_still_answer_503_when_tokens_cannot_be_checked(client, supabase):
    supabase.jwks.error = connection_error()

    response = client.get(
        "/api/catalog/brands", params={"query": "x"}, headers={"Authorization": f"Bearer {supabase.token()}"}
    )

    assert (response.status_code, response.json()["error"]["code"]) == (503, "SERVICE_UNAVAILABLE")


def test_after_a_401_the_same_request_without_a_token_succeeds(client, db_session, token_for):
    # Spec 3.1.5: when the session cannot be refreshed, the app retries a public route as a guest.
    bar = make_bar(db_session)
    token_for("customer")  # enables temporary auth

    rejected = client.get(f"/api/bars/{bar.id}/menu", headers={"Authorization": "Bearer not-a-jwt"})
    retried = client.get(f"/api/bars/{bar.id}/menu")

    assert rejected.status_code == 401
    assert retried.status_code == 200
    assert retried.json()["barId"] == str(bar.id)


# ---- every field is always present; a missing value is null (spec 3.9, 3.9.1) ----

BAR_FIELDS = {"barId", "name", "address", "latitude", "longitude", "phone", "menuBoardId", "publishedAt", "items"}
ITEM_FIELDS = {"menuBoardEntryId", "barMenuItemId", "productId", "displayName", "sortOrder", "options"}
OPTION_FIELDS = {"menuEntryOptionId", "optionLabel", "pourMl", "priceKrw", "sortOrder"}


def test_a_bar_with_nothing_optional_still_sends_every_field(client, db_session):
    bar = make_bar(db_session)
    bar.phone = None
    db_session.flush()

    body = client.get(f"/api/bars/{bar.id}/menu").json()

    assert set(body) == BAR_FIELDS
    assert (body["phone"], body["menuBoardId"], body["publishedAt"], body["items"]) == (None, None, None, [])


def test_menu_items_and_options_send_every_field(client, db_session):
    bar = make_bar(db_session)
    product = make_product(db_session, make_brand(db_session, "Ardbeg"), "Ardbeg 10")
    publish_menu(db_session, bar, [(product, "Ardbeg 10", [(None, None, 12000), ("잔", 30, 13000)])])

    body = client.get(f"/api/bars/{bar.id}/menu").json()

    assert set(body) == BAR_FIELDS
    [item] = body["items"]
    assert set(item) == ITEM_FIELDS
    assert [set(option) for option in item["options"]] == [OPTION_FIELDS, OPTION_FIELDS]
    assert (item["options"][0]["optionLabel"], item["options"][0]["pourMl"]) == (None, None)


# ---- the number of queries does not grow with the menu ----


def statements_for_menu(client, db_session, bar) -> list[str]:
    with recorded_statements(db_session) as statements:
        response = client.get(f"/api/bars/{bar.id}/menu")
    assert response.status_code == 200
    return statements


def test_the_number_of_queries_does_not_grow_with_the_menu(client, db_session):
    brand = make_brand(db_session, "Ardbeg")
    products = [make_product(db_session, brand, f"Ardbeg {i}") for i in range(20)]
    small = make_bar(db_session, "Small")
    publish_menu(db_session, small, [(products[0], "Ardbeg 0", [(None, 30, 10000)])])
    large = make_bar(db_session, "Large")
    options = [("잔", 30, 10000), ("병", None, 200000)]
    publish_menu(db_session, large, [(product, product.display_name, options) for product in products])
    db_session.expire_all()  # nothing comes from the session's cache

    with_one_item = statements_for_menu(client, db_session, small)
    db_session.expire_all()
    with_twenty_items = statements_for_menu(client, db_session, large)

    assert len(with_one_item) == len(with_twenty_items)
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in with_twenty_items)
