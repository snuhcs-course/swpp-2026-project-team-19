"""Manual menu edits (API spec 3.14.1 to 3.14.7): add, edit, delete and reset, published at once."""

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core.errors import ApiError
from app.core.security import Principal
from app.models import (
    BarMenuItem,
    BarStatus,
    ImportMode,
    ImportStatus,
    MenuBoard,
    MenuImport,
    Product,
    User,
    UserType,
)
from app.schemas.menu_edit import MenuItemAddRequest
from app.services import menu_edit, serializable
from tests.factories import make_bar, make_owner, make_product, make_user, publish_menu
from tests.review_support import make_glenfiddich
from tests.sql_support import recorded_statements

NOW = datetime.now(timezone.utc)
STARTS, ENDS = NOW - timedelta(days=1), NOW + timedelta(days=14)
OWNER_SUBJECT = "owner-subject"
OPERATOR_SUBJECT = "operator-subject"


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


DISCOUNT = {"discountedPriceKrw": 14000, "startsAt": utc(STARTS), "endsAt": utc(ENDS)}


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


# A failed edit rolls the session back, which in tests also drops rows that were only flushed, so
# the setup is committed first (the test's outer transaction still undoes it afterwards).


@pytest.fixture
def bar(db_session, glenfiddich):
    """A bar selling the 12 (glass with a running discount, bottle) and the 15, at menu version 4."""
    bar = make_bar(db_session, "Seorosang")
    publish_menu(
        db_session,
        bar,
        [
            (glenfiddich[12], "글렌피딕 12년", [("잔", 30, 17000, (14000, STARTS, ENDS)), ("병", None, 160000)]),
            (glenfiddich[15], "글렌피딕 15년", [("잔", 30, 21000)]),
        ],
        published_at=NOW - timedelta(days=3),
        version=4,
    )
    db_session.commit()
    return bar


def option(price=18000, label="잔", pour=30, discount=None) -> dict:
    return {"optionLabel": label, "pourMl": pour, "priceKrw": price, "discount": discount}


def adding(product, menu_version) -> dict:
    return {"menuVersion": menu_version, "productId": str(product.id), "options": [option()]}


def editing(menu_version, options=None, *, name="글렌피딕 12년") -> dict:
    return {"menuVersion": menu_version, "displayName": name, "options": [option()] if options is None else options}


def menu_of(client, bar, headers) -> dict:
    response = client.get(f"/api/bars/{bar.id}/menu", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def add(client, bar_id, body, headers):
    return client.post(f"/api/bars/{bar_id}/menu/items", json=body, headers=headers)


def edit(client, bar_id, item_id, body, headers):
    return client.put(f"/api/bars/{bar_id}/menu/items/{item_id}", json=body, headers=headers)


def delete(client, bar_id, item_id, menu_version, headers):
    params = {} if menu_version is None else {"menuVersion": menu_version}
    return client.delete(f"/api/bars/{bar_id}/menu/items/{item_id}", params=params, headers=headers)


def reset(client, bar_id, body, headers):
    return client.post(f"/api/bars/{bar_id}/menu/reset", json=body, headers=headers)


def error(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def field_errors(response) -> list[tuple[str, str]]:
    assert error(response) == (422, "VALIDATION_FAILED"), response.text
    return [(e["path"], e["code"]) for e in response.json()["error"]["fieldErrors"]]


def item_of(menu, product) -> dict:
    return next(item for item in menu["items"] if item["productId"] == str(product.id))


def unchanged(item: dict) -> dict:
    """An item as another item's edit must leave it."""
    return {key: item[key] for key in ("menuBoardEntryId", "barMenuItemId", "displayName", "sortOrder", "options")}


def owner_of(db_session, supabase, bar) -> dict:
    reviewer = make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)
    make_owner(db_session, make_user(db_session, OWNER_SUBJECT), bar, reviewer)
    db_session.commit()
    return {"Authorization": f"Bearer {supabase.token(sub=OWNER_SUBJECT)}"}


def add_import(db_session, bar, status=ImportStatus.READY_FOR_REVIEW) -> MenuImport:
    menu_import = MenuImport(
        idempotency_key=str(uuid4()),
        request_fingerprint="0" * 64,
        bar_id=bar.id,
        mode=ImportMode.PARTIAL_UPDATE,
        status=status,
    )
    db_session.add(menu_import)
    db_session.commit()
    return menu_import


# ---- add ----


def make_glenfiddich_18(db_session, glenfiddich) -> Product:
    return make_product(db_session, glenfiddich["brand"], "Glenfiddich 18", age_years=18)


def test_adding_puts_the_item_at_the_end_and_publishes_it(client, db_session, operator, bar, glenfiddich):
    eighteen = make_glenfiddich_18(db_session, glenfiddich)
    before = menu_of(client, bar, operator)

    response = add(
        client,
        bar.id,
        {"menuVersion": 4, "productId": str(eighteen.id), "displayName": " 글렌피딕 18년 ", "options": [option(32000)]},
        operator,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body == menu_of(client, bar, operator)
    assert body["menuVersion"] == 5
    assert body["publishedAt"] > before["publishedAt"]
    added = item_of(body, eighteen)
    assert (added["displayName"], added["sortOrder"], added["productName"]) == ("글렌피딕 18년", 3, "Glenfiddich 18")
    assert [(o["optionLabel"], o["pourMl"], o["priceKrw"], o["discount"]) for o in added["options"]] == [
        ("잔", 30, 32000, None)
    ]
    # The other items keep their ids, order, options and the 12's discount.
    assert [unchanged(i) for i in body["items"][:2]] == [unchanged(i) for i in before["items"]]
    # Published at once: customers find it.
    found = client.get("/api/search/bars", params={"query": "Glenfiddich 18"}).json()["items"]
    assert [(i["barId"], i["menuDisplayName"]) for i in found] == [(str(bar.id), "글렌피딕 18년")]


def test_without_a_display_name_the_item_takes_the_products_name(client, db_session, operator, bar, glenfiddich):
    eighteen = make_glenfiddich_18(db_session, glenfiddich)

    body = add(client, bar.id, adding(eighteen, 4), operator).json()

    assert item_of(body, eighteen)["displayName"] == "Glenfiddich 18"


def test_the_first_add_creates_the_menu_at_version_one(client, db_session, operator, glenfiddich):
    bar = make_bar(db_session, "Empty")

    response = add(client, bar.id, adding(glenfiddich[12], None), operator)

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["menuVersion"], [i["sortOrder"] for i in body["items"]]) == (1, [1])
    board = db_session.get(MenuBoard, body["menuBoardId"])
    assert board.last_import_id is None
    assert utc(board.published_at) == body["publishedAt"]


def test_a_product_sold_before_gets_its_bar_menu_item_back(client, operator, bar, glenfiddich):
    fifteen = item_of(menu_of(client, bar, operator), glenfiddich[15])
    assert delete(client, bar.id, fifteen["barMenuItemId"], 4, operator).status_code == 200

    body = add(client, bar.id, adding(glenfiddich[15], 5), operator).json()

    again = item_of(body, glenfiddich[15])
    assert again["barMenuItemId"] == fifteen["barMenuItemId"]
    assert again["menuBoardEntryId"] != fifteen["menuBoardEntryId"]


def test_a_product_already_on_the_menu_is_a_conflict(client, operator, bar, glenfiddich):
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])

    response = add(client, bar.id, adding(glenfiddich[12], 4), operator)

    assert error(response) == (409, "MENU_ITEM_EXISTS")
    assert response.json()["error"]["details"] == {"barMenuItemId": twelve["barMenuItemId"]}
    assert menu_of(client, bar, operator)["menuVersion"] == 4


def test_missing_and_inactive_products_and_brands_are_rejected(client, operator, bar, glenfiddich):
    def add_with(**fields):
        return add(client, bar.id, {"menuVersion": 4, "options": [option()], **fields}, operator)

    assert field_errors(add_with(productId=str(uuid4()))) == [("productId", "PRODUCT_NOT_FOUND")]
    assert field_errors(add_with(productId=str(glenfiddich[21].id))) == [("productId", "PRODUCT_INACTIVE")]
    missing_brand = {"brand": {"type": "existing", "brandId": str(uuid4())}, "product": {"displayName": "New 10"}}
    assert field_errors(add_with(newProduct=missing_brand)) == [("newProduct.brand.brandId", "BRAND_NOT_FOUND")]


def test_a_new_product_is_created_searchable_and_records_its_creator(client, db_session, supabase, bar):
    """Only an operator may create a catalog product (spec 2.2, 3.14.3)."""
    make_user(db_session, OPERATOR_SUBJECT, user_type=UserType.OPERATOR)
    db_session.commit()
    operator = {"Authorization": f"Bearer {supabase.token(sub=OPERATOR_SUBJECT)}"}
    new_product = {
        "brand": {"type": "new", "canonicalName": "Deanston"},
        "product": {"displayName": "Deanston Virgin Oak", "editionName": "Virgin Oak", "abv": 46.3},
        "aliases": [{"aliasText": "딘스톤 버진 오크", "languageCode": "ko"}],
    }

    response = add(
        client,
        bar.id,
        {"menuVersion": 4, "newProduct": new_product, "displayName": "딘스톤 버진 오크", "options": [option(pour=None)]},
        operator,
    )

    assert response.status_code == 201, response.text
    product = db_session.scalar(select(Product).where(Product.display_name == "Deanston Virgin Oak"))
    operator_id = db_session.scalar(select(User.id).where(User.auth_subject == OPERATOR_SUBJECT))
    assert (product.created_by_user_id, product.brand.created_by_user_id) == (operator_id, operator_id)
    assert product.created_from_extracted_item_id is None
    assert item_of(response.json(), product)["brandName"] == "Deanston"
    found = client.get("/api/search/bars", params={"query": "딘스톤 버진 오크"}).json()
    assert [i["productId"] for i in found["items"]] == [str(product.id)]


def test_a_new_product_that_exists_is_a_conflict_and_nothing_is_created(client, db_session, operator, bar, glenfiddich):
    count = db_session.scalar(select(func.count()).select_from(Product))
    new_product = {
        "brand": {"type": "new", "canonicalName": "Kavalan"},
        "product": {"displayName": "Kavalan Classic"},
        # Matches the active 12, so the brand created above is rolled back with the request.
        "aliases": [{"aliasText": "글렌피딕 12년"}],
    }

    response = add(client, bar.id, {"menuVersion": 4, "newProduct": new_product, "options": [option()]}, operator)

    assert error(response) == (409, "DUPLICATE_PRODUCT_FOUND")
    details = response.json()["error"]["details"]
    assert set(details) == {"existingProduct"}
    assert (details["existingProduct"]["productId"], details["existingProduct"]["isActive"]) == (
        str(glenfiddich[12].id),
        True,
    )
    assert db_session.scalar(select(func.count()).select_from(Product)) == count
    assert menu_of(client, bar, operator)["menuVersion"] == 4


NEW_X = {"brand": {"type": "new", "canonicalName": "X"}, "product": {"displayName": "X"}}


@pytest.mark.parametrize("fields", [{}, {"productId": "both", "newProduct": NEW_X}], ids=["neither", "both"])
def test_exactly_one_of_product_id_and_new_product(client, operator, bar, glenfiddich, fields):
    fields = {**fields, "productId": str(glenfiddich[15].id)} if "productId" in fields else fields

    response = add(client, bar.id, {"menuVersion": 4, "options": [option()], **fields}, operator)

    assert field_errors(response) == [("productId", "EXACTLY_ONE_REQUIRED")]


def test_new_names_must_normalize_to_something(client, operator, bar):
    new_product = {
        "brand": {"type": "new", "canonicalName": "!!!", "aliases": [{"aliasText": "~"}]},
        "product": {"displayName": "***"},
        "aliases": [{"aliasText": "..."}],
    }

    response = add(client, bar.id, {"menuVersion": 4, "newProduct": new_product, "options": [option()]}, operator)

    assert field_errors(response) == [
        ("newProduct.brand.canonicalName", "NOT_NORMALIZABLE"),
        ("newProduct.brand.aliases[0].aliasText", "NOT_NORMALIZABLE"),
        ("newProduct.product.displayName", "NOT_NORMALIZABLE"),
        ("newProduct.aliases[0].aliasText", "NOT_NORMALIZABLE"),
    ]


# ---- options and discounts ----


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        pytest.param([], [("options", "TOO_SHORT")], id="no option"),
        pytest.param([option(1000 + n, pour=n + 1) for n in range(4)], [("options", "TOO_LONG")], id="four options"),
        pytest.param([option(), option(20000)], [("options", "DUPLICATE_OPTION_VALUES")], id="same label and pour"),
        pytest.param([option(0)], [("options[0].priceKrw", "GREATER_THAN_EQUAL")], id="zero price"),
        pytest.param([option(100_000_000)], [("options[0].priceKrw", "LESS_THAN_EQUAL")], id="price too high"),
        pytest.param([option(pour=0)], [("options[0].pourMl", "GREATER_THAN_EQUAL")], id="zero pour"),
        pytest.param([option(label="  ")], [("options[0].optionLabel", "STRING_TOO_SHORT")], id="blank label"),
        pytest.param(
            [{**option(), "soldOut": True}], [("options[0].soldOut", "EXTRA_FORBIDDEN")], id="unknown field"
        ),
        pytest.param(
            [option(14000, discount=DISCOUNT)],
            [("options[0].discount.discountedPriceKrw", "DISCOUNT_NOT_LOWER")],
            id="discount equal to the price",
        ),
        pytest.param(
            [option(discount={**DISCOUNT, "endsAt": utc(STARTS)})],
            [("options[0].discount.endsAt", "END_BEFORE_START"), ("options[0].discount.endsAt", "DISCOUNT_ENDED")],
            id="ends when it starts",
        ),
        pytest.param(
            [option(discount={**DISCOUNT, "startsAt": utc(NOW - timedelta(days=9)), "endsAt": utc(NOW)})],
            [("options[0].discount.endsAt", "DISCOUNT_ENDED")],
            id="already ended",
        ),
        pytest.param(
            [option(discount={**DISCOUNT, "startsAt": "2026-11-01T09:00:00"})],
            [("options[0].discount.startsAt", "TIMEZONE_AWARE")],
            id="time without a zone",
        ),
    ],
)
def test_option_rules(client, operator, bar, glenfiddich, options, expected):
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])

    response = edit(client, bar.id, twelve["barMenuItemId"], editing(4, options), operator)

    assert field_errors(response) == expected


def test_every_problem_comes_in_one_response(client, operator, bar, glenfiddich):
    options = [option(14000, discount=DISCOUNT), option(14000, discount=DISCOUNT)]

    response = add(client, bar.id, {"menuVersion": 4, "options": options}, operator)

    assert field_errors(response) == [
        ("productId", "EXACTLY_ONE_REQUIRED"),
        ("options", "DUPLICATE_OPTION_VALUES"),
        ("options[0].discount.discountedPriceKrw", "DISCOUNT_NOT_LOWER"),
        ("options[1].discount.discountedPriceKrw", "DISCOUNT_NOT_LOWER"),
    ]


def test_a_discount_that_has_not_started_is_stored_and_sent(client, operator, bar, glenfiddich):
    later = {"discountedPriceKrw": 15000, "startsAt": utc(NOW + timedelta(days=2)), "endsAt": utc(ENDS)}
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])

    body = edit(client, bar.id, twelve["barMenuItemId"], editing(4, [option(discount=later)]), operator).json()

    assert item_of(body, glenfiddich[12])["options"][0]["discount"] == later


# ---- edit ----


def test_editing_replaces_the_name_and_options_in_place(client, operator, bar, glenfiddich):
    before = menu_of(client, bar, operator)
    twelve = item_of(before, glenfiddich[12])
    options = [option(17000, discount=twelve["options"][0]["discount"]), option(30000, label="더블", pour=60)]

    response = edit(client, bar.id, twelve["barMenuItemId"], editing(4, options, name="글렌피딕 12Y"), operator)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["menuVersion"] == 5
    edited = item_of(body, glenfiddich[12])
    assert (edited["barMenuItemId"], edited["sortOrder"], edited["displayName"]) == (
        twelve["barMenuItemId"],
        1,
        "글렌피딕 12Y",
    )
    # The glass's discount was sent back, so it stays; the bottle was left out, so it is gone.
    assert [(o["optionLabel"], o["priceKrw"], o["discount"]) for o in edited["options"]] == [
        ("잔", 17000, twelve["options"][0]["discount"]),
        ("더블", 30000, None),
    ]
    assert unchanged(item_of(body, glenfiddich[15])) == unchanged(item_of(before, glenfiddich[15]))


def test_leaving_the_discount_out_removes_it(client, operator, bar, glenfiddich):
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])

    body = edit(client, bar.id, twelve["barMenuItemId"], editing(4, [option(17000)]), operator).json()

    assert item_of(body, glenfiddich[12])["options"][0]["discount"] is None


def test_an_item_with_more_options_than_allowed_can_be_trimmed(client, db_session, operator, glenfiddich):
    bar = make_bar(db_session, "Many options")
    many = [(None, pour, 1000 * pour) for pour in (15, 30, 45, 60)]
    publish_menu(db_session, bar, [(glenfiddich[12], "글렌피딕 12년", many)])
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])
    assert len(twelve["options"]) == 4

    response = edit(client, bar.id, twelve["barMenuItemId"], editing(1), operator)

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("item_id", ["deleted", str(uuid4()), "not-a-uuid"])
def test_editing_an_item_not_on_the_menu_is_not_found(client, operator, bar, glenfiddich, item_id):
    if item_id == "deleted":
        item_id = item_of(menu_of(client, bar, operator), glenfiddich[15])["barMenuItemId"]
        delete(client, bar.id, item_id, 4, operator)
    version = menu_of(client, bar, operator)["menuVersion"]

    response = edit(client, bar.id, item_id, editing(version), operator)

    assert error(response) == (404, "MENU_ITEM_NOT_FOUND")
    assert response.json()["error"]["details"] == {"barMenuItemId": item_id}


def test_an_edit_needs_a_display_name_and_a_version(client, operator, bar, glenfiddich):
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])

    response = edit(client, bar.id, twelve["barMenuItemId"], {"options": [option()]}, operator)

    assert field_errors(response) == [("menuVersion", "MISSING"), ("displayName", "MISSING")]


# ---- delete ----


def test_deleting_takes_one_item_off_and_keeps_the_others_in_place(client, db_session, operator, bar, glenfiddich):
    before = menu_of(client, bar, operator)
    twelve = item_of(before, glenfiddich[12])

    response = delete(client, bar.id, twelve["barMenuItemId"], 4, operator)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["menuVersion"] == 5
    # The 15 keeps its sortOrder 2, so the order has a gap.
    assert [unchanged(i) for i in body["items"]] == [unchanged(item_of(before, glenfiddich[15]))]
    # The bar menu item stays for a later add of the same product.
    assert db_session.get(BarMenuItem, twelve["barMenuItemId"]) is not None


def test_deleting_the_last_item_keeps_an_empty_menu(client, operator, glenfiddich, db_session):
    bar = make_bar(db_session, "One item")
    publish_menu(db_session, bar, [(glenfiddich[12], "글렌피딕 12년", [(None, 30, 17000)])])
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])

    body = delete(client, bar.id, twelve["barMenuItemId"], 1, operator).json()

    assert (body["menuBoardId"] is not None, body["menuVersion"], body["items"]) == (True, 2, [])


def test_deleting_needs_the_menu_version(client, operator, bar, glenfiddich):
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])

    assert field_errors(delete(client, bar.id, twelve["barMenuItemId"], None, operator)) == [("menuVersion", "MISSING")]


@pytest.mark.parametrize("item_id", [str(uuid4()), "not-a-uuid"])
def test_deleting_an_item_not_on_the_menu_is_not_found(client, operator, bar, item_id):
    response = delete(client, bar.id, item_id, 4, operator)

    assert error(response) == (404, "MENU_ITEM_NOT_FOUND")


# ---- reset ----


def test_reset_empties_the_menu_and_keeps_the_board(client, db_session, operator, bar):
    before = menu_of(client, bar, operator)

    response = reset(client, bar.id, {"menuVersion": 4}, operator)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["menuBoardId"], body["menuVersion"], body["items"]) == (before["menuBoardId"], 5, [])
    assert body["publishedAt"] > before["publishedAt"]
    assert client.get("/api/search/bars", params={"query": "글렌피딕"}).json()["items"] == []


def test_reset_without_a_menu_changes_nothing(client, db_session, operator):
    bar = make_bar(db_session, "Empty")

    response = reset(client, bar.id, {"menuVersion": None}, operator)

    assert response.status_code == 200, response.text
    assert (response.json()["menuBoardId"], response.json()["menuVersion"]) == (None, None)
    assert db_session.scalar(select(MenuBoard).where(MenuBoard.bar_id == bar.id)) is None


def test_reset_needs_the_menu_version_field(client, operator, bar):
    assert field_errors(reset(client, bar.id, {}, operator)) == [("menuVersion", "MISSING")]


# ---- sold-out (spec 3.14.8): kept while on the board, cleared when the item leaves ----


def mark_sold_out(db_session, item_id) -> BarMenuItem:
    item = db_session.get(BarMenuItem, item_id)
    item.sold_out_at = NOW
    db_session.commit()
    return item


def sold_out_at(db_session, item_id):
    db_session.expire_all()
    return db_session.get(BarMenuItem, item_id).sold_out_at


def test_editing_a_sold_out_item_keeps_it_sold_out(client, db_session, operator, bar, glenfiddich):
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])["barMenuItemId"]
    mark_sold_out(db_session, twelve)

    body = edit(client, bar.id, twelve, editing(4, [option(19000)]), operator).json()

    assert item_of(body, glenfiddich[12])["soldOut"] is True
    assert sold_out_at(db_session, twelve) is not None


def test_deleting_puts_the_item_back_on_sale_for_a_later_add(client, db_session, operator, bar, glenfiddich):
    fifteen = item_of(menu_of(client, bar, operator), glenfiddich[15])["barMenuItemId"]
    mark_sold_out(db_session, fifteen)

    assert delete(client, bar.id, fifteen, 4, operator).status_code == 200
    assert sold_out_at(db_session, fifteen) is None
    body = add(client, bar.id, adding(glenfiddich[15], 5), operator).json()
    assert (item_of(body, glenfiddich[15])["barMenuItemId"], item_of(body, glenfiddich[15])["soldOut"]) == (
        fifteen,
        False,
    )


def test_deleting_leaves_other_sold_out_items_alone(client, db_session, operator, bar, glenfiddich):
    menu = menu_of(client, bar, operator)
    twelve, fifteen = (item_of(menu, glenfiddich[age])["barMenuItemId"] for age in (12, 15))
    mark_sold_out(db_session, twelve)

    delete(client, bar.id, fifteen, 4, operator)

    assert sold_out_at(db_session, twelve) is not None


def test_reset_puts_every_item_back_on_sale(client, db_session, operator, bar, glenfiddich):
    menu = menu_of(client, bar, operator)
    items = [item_of(menu, glenfiddich[age])["barMenuItemId"] for age in (12, 15)]
    for item_id in items:
        mark_sold_out(db_session, item_id)

    assert reset(client, bar.id, {"menuVersion": 4}, operator).status_code == 200
    assert [sold_out_at(db_session, item_id) for item_id in items] == [None, None]


# ---- menu version ----


@pytest.mark.parametrize(
    ("bar_name", "submitted", "current"),
    [("with menu", 3, 4), ("with menu", None, 4), ("without menu", 1, None)],
    ids=["older version", "null for a menu", "a version without a menu"],
)
def test_a_different_menu_version_changes_nothing(client, db_session, operator, bar, bar_name, submitted, current):
    target = bar if bar_name == "with menu" else make_bar(db_session, "Empty")
    db_session.commit()

    response = reset(client, target.id, {"menuVersion": submitted}, operator)

    assert error(response) == (409, "MENU_OUTDATED")
    assert response.json()["error"]["details"] == {"submittedMenuVersion": submitted, "currentMenuVersion": current}
    assert menu_of(client, target, operator)["menuVersion"] == current


def test_a_retried_edit_that_succeeded_is_outdated(client, operator, bar, glenfiddich):
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])
    body = {"menuVersion": 4, "displayName": "12", "options": [option()]}
    assert edit(client, bar.id, twelve["barMenuItemId"], body, operator).status_code == 200

    assert error(edit(client, bar.id, twelve["barMenuItemId"], body, operator)) == (409, "MENU_OUTDATED")


def test_a_review_publish_and_an_edit_share_the_version(client, operator, bar, glenfiddich):
    """An edit made on a menu older than a review publish is outdated (spec 8.7 raises it too)."""
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])
    edit(client, bar.id, twelve["barMenuItemId"], editing(4), operator)

    assert error(reset(client, bar.id, {"menuVersion": 4}, operator)) == (409, "MENU_OUTDATED")
    assert reset(client, bar.id, {"menuVersion": 5}, operator).json()["menuVersion"] == 6


# ---- order of checks ----


@pytest.mark.parametrize("status", [ImportStatus.UPLOADED, ImportStatus.PROCESSING, ImportStatus.READY_FOR_REVIEW])
def test_an_unfinished_import_blocks_every_edit_before_the_version(
    client, db_session, operator, bar, glenfiddich, status
):
    menu_import = add_import(db_session, bar, status)
    twelve = item_of(menu_of(client, bar, operator), glenfiddich[12])["barMenuItemId"]
    # An outdated version too: the import is reported first.
    responses = [
        add(client, bar.id, {"menuVersion": 1, "productId": str(glenfiddich[15].id), "options": [option()]}, operator),
        edit(client, bar.id, twelve, {"menuVersion": 1, "displayName": "12", "options": [option()]}, operator),
        delete(client, bar.id, twelve, 1, operator),
        reset(client, bar.id, {"menuVersion": 1}, operator),
    ]

    for response in responses:
        assert error(response) == (409, "ACTIVE_IMPORT_EXISTS")
        assert response.json()["error"]["details"] == {"menuImportId": str(menu_import.id), "status": status.value}


@pytest.mark.parametrize("status", [ImportStatus.APPLIED, ImportStatus.FAILED, ImportStatus.CANCELED])
def test_a_finished_import_does_not_block(client, db_session, operator, bar, status):
    add_import(db_session, bar, status)

    assert reset(client, bar.id, {"menuVersion": 4}, operator).status_code == 200


def test_the_request_is_checked_before_the_bar(client, operator):
    response = reset(client, uuid4(), {"menuVersion": "four"}, operator)

    assert field_errors(response) == [("menuVersion", "INT_PARSING")]


def test_rules_of_the_request_alone_come_before_the_bar(client, operator):
    response = add(client, uuid4(), {"menuVersion": 1, "options": [option()]}, operator)

    assert field_errors(response) == [("productId", "EXACTLY_ONE_REQUIRED")]


@pytest.mark.parametrize("bar_id", [str(uuid4()), "not-a-uuid"])
def test_a_missing_bar_is_not_found(client, operator, bar_id):
    response = reset(client, bar_id, {"menuVersion": None}, operator)

    assert error(response) == (404, "BAR_NOT_FOUND")
    assert response.json()["error"]["details"] == {"barId": bar_id}


def test_an_inactive_bar_is_not_found_for_a_manager_and_forbidden_for_others(
    client, db_session, operator, bar, token_for
):
    bar.status = BarStatus.INACTIVE
    db_session.commit()

    assert error(reset(client, bar.id, {"menuVersion": 4}, operator)) == (404, "BAR_NOT_FOUND")
    # A temporary token takes its role from the server setting, so the customer is issued last.
    customer = {"Authorization": f"Bearer {token_for('customer')}"}
    assert error(reset(client, bar.id, {"menuVersion": 4}, customer)) == (403, "FORBIDDEN")


def test_the_bars_owner_may_edit(client, db_session, supabase, bar):
    owner = owner_of(db_session, supabase, bar)

    assert reset(client, bar.id, {"menuVersion": 4}, owner).status_code == 200


# ---- the bar row lock and the transaction ----


def test_the_bar_row_is_locked_before_anything_is_checked(client, db_session, operator, bar):
    with recorded_statements(db_session) as statements:
        assert reset(client, bar.id, {"menuVersion": 4}, operator).status_code == 200

    lock = next(i for i, sql in enumerate(statements) if "FOR UPDATE" in sql)
    assert "FROM bars" in statements[lock]
    unfinished = next(i for i, sql in enumerate(statements) if "FROM menu_imports" in sql)
    stamp = next(i for i, sql in enumerate(statements) if "clock_timestamp()" in sql)
    assert lock < unfinished < stamp


def test_an_owner_revoked_before_the_lock_is_forbidden(db_session, bar, glenfiddich):
    """The route let the owner in; the transaction checks again once the bar row is locked."""
    reviewer = make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)
    ownership = make_owner(db_session, make_user(db_session, OWNER_SUBJECT), bar, reviewer)
    ownership.revoked_at, ownership.revoked_by_user_id = NOW, reviewer.id
    db_session.commit()
    owner = Principal(kind="supabase", subject=OWNER_SUBJECT, claims={})
    body = MenuItemAddRequest.model_validate({"menuVersion": 4, "productId": str(uuid4()), "options": [option()]})

    with pytest.raises(ApiError) as caught:
        menu_edit.add_menu_item(lambda: nullcontext(db_session), owner, bar.id, body, base_url="")

    assert (caught.value.status_code, caught.value.code) == (403, "FORBIDDEN")


class _SerializationFailure(Exception):
    sqlstate = "40001"


def test_a_write_conflict_is_retried(client, operator, bar, monkeypatch):
    real, calls = menu_edit._reset_once, []

    def flaky(*args):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("UPDATE ...", {}, _SerializationFailure())
        return real(*args)

    monkeypatch.setattr(menu_edit, "_reset_once", flaky)
    monkeypatch.setattr(serializable, "sleep", lambda seconds: None)

    assert reset(client, bar.id, {"menuVersion": 4}, operator).json()["menuVersion"] == 5
    assert len(calls) == 2


def test_repeated_conflicts_are_503_and_roll_everything_back(client, db_session, operator, bar, monkeypatch):
    count = db_session.scalar(select(func.count()).select_from(Product))
    real = menu_edit._publish

    def publish_then_conflict(session, board, *args, **kwargs):
        real(session, board, *args, **kwargs)
        raise OperationalError("UPDATE ...", {}, _SerializationFailure())

    monkeypatch.setattr(menu_edit, "_publish", publish_then_conflict)
    monkeypatch.setattr(serializable, "sleep", lambda seconds: None)
    new_product = {"brand": {"type": "new", "canonicalName": "Deanston"}, "product": {"displayName": "Deanston 12"}}

    response = add(client, bar.id, {"menuVersion": 4, "newProduct": new_product, "options": [option()]}, operator)

    assert error(response) == (503, "TEMPORARY_WRITE_CONFLICT")
    assert db_session.scalar(select(func.count()).select_from(Product)) == count
    assert menu_of(client, bar, operator)["menuVersion"] == 4
