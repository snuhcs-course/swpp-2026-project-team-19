from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import BarMenuItem, BarStatus, MenuBoard, MenuBoardEntry, MenuEntryOption, User, UserType
from app.services.bar_menu import discount_response
from tests.auth_support import connection_error
from tests.factories import make_bar, make_brand, make_owner, make_product, make_user, publish_menu
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
    assert (body["menuBoardId"], body["menuVersion"]) == (str(board.id), 1)
    assert body["publishedAt"] == "2026-10-04T09:15:00Z"
    assert [(i["displayName"], i["productId"], i["sortOrder"]) for i in body["items"]] == [
        ("글렌드로낙 12Y", str(twelve.id), 1),
        ("글렌드로낙 15Y", str(fifteen.id), 2),
    ]
    assert [(i["productName"], i["brandId"], i["brandName"], i["category"]) for i in body["items"]] == [
        ("GlenDronach 12", str(brand.id), "GlenDronach", "whisky"),
        ("GlenDronach 15", str(brand.id), "GlenDronach", "whisky"),
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


# ---- sold-out items: only operators and the bar's owner see them (spec 3.9, 3.14.8) ----


def menu_with_a_sold_out_item(db_session, *, all_sold_out=False):
    """A bar selling Ardbeg 10, 5 (sold out) and Uigeadail, in that order."""
    brand = make_brand(db_session, "Ardbeg")
    products = [make_product(db_session, brand, name) for name in ("Ardbeg 10", "Ardbeg 5", "Ardbeg Uigeadail")]
    bar = make_bar(db_session)
    publish_menu(db_session, bar, [(p, p.display_name, [(None, 30, 12000)]) for p in products])
    for product in products if all_sold_out else products[1:2]:
        item = db_session.scalar(select(BarMenuItem).where(BarMenuItem.product_id == product.id))
        item.sold_out_at = datetime(2026, 11, 3, 1, tzinfo=timezone.utc)
    db_session.flush()
    return bar


def lines(body) -> list[tuple[str, int, bool]]:
    return [(item["displayName"], item["sortOrder"], item["soldOut"]) for item in body["items"]]


def test_guests_and_customers_do_not_get_sold_out_items(client, db_session, token_for):
    bar = menu_with_a_sold_out_item(db_session)
    customer = {"Authorization": f"Bearer {token_for('customer')}"}

    for headers in ({}, customer):
        body = client.get(f"/api/bars/{bar.id}/menu", headers=headers).json()
        assert lines(body) == [("Ardbeg 10", 1, False), ("Ardbeg Uigeadail", 3, False)]


def test_an_operator_gets_sold_out_items_in_place(client, db_session, token_for):
    bar = menu_with_a_sold_out_item(db_session)
    operator = {"Authorization": f"Bearer {token_for('operator')}"}

    body = client.get(f"/api/bars/{bar.id}/menu", headers=operator).json()

    assert lines(body) == [("Ardbeg 10", 1, False), ("Ardbeg 5", 2, True), ("Ardbeg Uigeadail", 3, False)]


def test_only_the_bars_own_owner_gets_sold_out_items(client, db_session, supabase):
    bar = menu_with_a_sold_out_item(db_session)
    reviewer = make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)
    make_owner(db_session, make_user(db_session, "owner-subject"), bar, reviewer)
    make_owner(db_session, make_user(db_session, "other-subject"), make_bar(db_session, "Other"), reviewer)

    def seen_by(subject):
        headers = {"Authorization": f"Bearer {supabase.token(sub=subject)}"}
        return [name for name, _, _ in lines(client.get(f"/api/bars/{bar.id}/menu", headers=headers).json())]

    assert seen_by("owner-subject") == ["Ardbeg 10", "Ardbeg 5", "Ardbeg Uigeadail"]
    assert seen_by("other-subject") == ["Ardbeg 10", "Ardbeg Uigeadail"]


def test_a_menu_sold_out_for_a_customer_keeps_the_board(client, db_session):
    bar = menu_with_a_sold_out_item(db_session, all_sold_out=True)

    body = client.get(f"/api/bars/{bar.id}/menu").json()

    assert body["items"] == []
    assert None not in (body["menuBoardId"], body["menuVersion"], body["publishedAt"])


def test_an_operator_with_an_uncheckable_token_does_not_get_sold_out_items(client, db_session, supabase):
    bar = menu_with_a_sold_out_item(db_session)
    db_session.add(User(auth_subject="operator-subject", user_type=UserType.OPERATOR))
    db_session.flush()
    supabase.jwks.error = connection_error()

    body = client.get(
        f"/api/bars/{bar.id}/menu", headers={"Authorization": f"Bearer {supabase.token(sub='operator-subject')}"}
    ).json()

    assert [name for name, _, _ in lines(body)] == ["Ardbeg 10", "Ardbeg Uigeadail"]


def permission_queries(statements) -> list[str]:
    return [sql for sql in statements if "bar_owners" in sql or "FROM users" in sql]


def test_the_callers_permission_is_read_only_when_a_sold_out_item_is_there(client, db_session, supabase):
    plain = make_bar(db_session, "Plain")
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    publish_menu(db_session, plain, [(product, "Glenfiddich 12", [(None, 30, 17000)])])
    with_sold_out = menu_with_a_sold_out_item(db_session)
    customer = {"Authorization": f"Bearer {supabase.token(sub='customer-subject')}"}

    with recorded_statements(db_session) as for_plain:
        assert client.get(f"/api/bars/{plain.id}/menu", headers=customer).status_code == 200
    with recorded_statements(db_session) as for_guest:
        assert client.get(f"/api/bars/{with_sold_out.id}/menu").status_code == 200
    with recorded_statements(db_session) as for_customer:
        assert client.get(f"/api/bars/{with_sold_out.id}/menu", headers=customer).status_code == 200

    assert permission_queries(for_plain) == permission_queries(for_guest) == []
    assert permission_queries(for_customer) != []


def test_an_inactive_bar_with_sold_out_items_asks_for_the_permission_once(client, db_session, supabase):
    bar = menu_with_a_sold_out_item(db_session)
    bar.status = BarStatus.INACTIVE
    make_user(db_session, "operator-subject", user_type=UserType.OPERATOR)
    operator = {"Authorization": f"Bearer {supabase.token(sub='operator-subject')}"}

    with recorded_statements(db_session) as statements:
        body = client.get(f"/api/bars/{bar.id}/menu", headers=operator).json()

    assert [sold_out for _, _, sold_out in lines(body)] == [False, True, False]
    assert len(permission_queries(statements)) == 1


# ---- every field is always present; a missing value is null (spec 3.9, 3.9.1) ----

BAR_FIELDS = {
    "barId",
    "name",
    "address",
    "latitude",
    "longitude",
    "phone",
    "menuBoardId",
    "menuVersion",
    "publishedAt",
    "items",
}
ITEM_FIELDS = {
    "menuBoardEntryId",
    "barMenuItemId",
    "productId",
    "productName",
    "brandId",
    "brandName",
    "category",
    "displayName",
    "sortOrder",
    "soldOut",
    "options",
}
OPTION_FIELDS = {"menuEntryOptionId", "optionLabel", "pourMl", "priceKrw", "discount", "sortOrder"}
DISCOUNT_FIELDS = {"discountedPriceKrw", "startsAt", "endsAt"}


def test_a_bar_with_nothing_optional_still_sends_every_field(client, db_session):
    bar = make_bar(db_session)
    bar.phone = None
    db_session.flush()

    body = client.get(f"/api/bars/{bar.id}/menu").json()

    assert set(body) == BAR_FIELDS
    assert (body["phone"], body["menuBoardId"], body["menuVersion"], body["publishedAt"], body["items"]) == (
        None,
        None,
        None,
        None,
        [],
    )


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
    assert item["options"][0]["discount"] is None


def test_a_discount_sends_every_field(client, db_session):
    bar = make_bar(db_session)
    product = make_product(db_session, make_brand(db_session, "Ardbeg"), "Ardbeg 10")
    publish_menu(db_session, bar, [(product, "Ardbeg 10", [("잔", 30, 13000, (11000, PAST, FUTURE))])])

    [option] = client.get(f"/api/bars/{bar.id}/menu").json()["items"][0]["options"]

    assert set(option) == OPTION_FIELDS
    assert set(option["discount"]) == DISCOUNT_FIELDS


# ---- menu version and discounts ----

NOW = datetime.now(timezone.utc)
PAST = NOW - timedelta(days=30)
FUTURE = NOW + timedelta(days=30)


def test_menu_version_is_the_boards_version(client, db_session):
    bar = make_bar(db_session)
    publish_menu(db_session, bar, [], version=4)

    assert client.get(f"/api/bars/{bar.id}/menu").json()["menuVersion"] == 4


def test_running_and_upcoming_discounts_are_sent_but_ended_ones_are_not(client, db_session):
    bar = make_bar(db_session)
    product = make_product(db_session, make_brand(db_session, "Ardbeg"), "Ardbeg 10")
    options = [
        ("잔", 30, 13000, (11000, PAST, FUTURE)),
        ("더블", 60, 25000, (20000, FUTURE, FUTURE + timedelta(days=1))),
        ("병", None, 260000, (200000, PAST - timedelta(days=1), PAST)),
        ("하프", None, 140000),
    ]
    publish_menu(db_session, bar, [(product, "Ardbeg 10", options)])

    body = client.get(f"/api/bars/{bar.id}/menu").json()

    discounts = [option["discount"] for option in body["items"][0]["options"]]
    assert discounts[2:] == [None, None]
    assert [d["discountedPriceKrw"] for d in discounts[:2]] == [11000, 20000]
    assert discounts[0]["startsAt"] == PAST.isoformat().replace("+00:00", "Z")
    assert discounts[1]["endsAt"] == (FUTURE + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    # The list price stays the list price while the discount runs.
    assert body["items"][0]["options"][0]["priceKrw"] == 13000


def test_a_discount_ends_at_its_end_time():
    option = MenuEntryOption(discount_price_krw=11000, discount_starts_at=PAST, discount_ends_at=FUTURE)

    assert discount_response(option, FUTURE - timedelta(microseconds=1)) is not None
    assert discount_response(option, FUTURE) is None
    assert discount_response(MenuEntryOption(), NOW) is None


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
