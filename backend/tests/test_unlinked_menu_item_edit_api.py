"""Manual adds and edits of menu items without a product, and the operator-only catalog (API spec 2.2,
3.14.1, 3.14.3 to 3.14.6 and 3.18.1).

An owner adds a whisky the catalog does not have, or a non-whisky menu, straight to the bar's menu with
`kind`; neither touches the shared catalog. An unlinked whisky opens an operator check.
"""

import pytest
from sqlalchemy import func, select

from app.models import (
    BarMenuItem,
    Brand,
    CheckReason,
    CheckStatus,
    MenuItemCheck,
    MenuItemKind,
    Product,
    ProductAlias,
)
from tests.test_menu_edit_api import (  # noqa: F401  (fixtures)
    add,
    bar,
    delete,
    edit,
    error,
    field_errors,
    glenfiddich,
    operator,
    option,
    owner_of,
    reset,
)


@pytest.fixture
def owner(db_session, supabase, bar):  # noqa: F811
    return owner_of(db_session, supabase, bar)


def unlinked(kind: str, name: str, menu_version: int = 4, options=None) -> dict:
    return {"menuVersion": menu_version, "kind": kind, "displayName": name, "options": options or [option()]}


def catalog_size(db_session) -> tuple[int, int, int]:
    return tuple(db_session.scalar(select(func.count()).select_from(t)) for t in (Brand, Product, ProductAlias))


def checks_of(db_session, item_id) -> list[tuple[CheckStatus, list[CheckReason]]]:
    db_session.expire_all()
    checks = db_session.scalars(select(MenuItemCheck).where(MenuItemCheck.bar_menu_item_id == item_id))
    return [(c.status, [r.reason for r in c.reasons]) for c in checks]


def last_item(response) -> dict:
    """The item added without a product is the last one (spec 3.14.3)."""
    return response.json()["items"][-1]


# ---- adding without a product ----


def test_an_owner_adds_a_beer_to_the_menu_only(client, db_session, owner, bar):  # noqa: F811
    before = catalog_size(db_session)

    response = add(client, bar.id, unlinked("other", "맥주 1", options=[option(8000, label=None, pour=None)]), owner)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["menuVersion"] == 5
    item = last_item(response)
    assert (item["displayName"], item["kind"], item["productId"], item["category"], item["sortOrder"]) == (
        "맥주 1",
        "other",
        None,
        None,
        3,
    )
    assert item["options"][0]["pourMl"] is None
    assert catalog_size(db_session) == before
    # A non-whisky menu waits for no one.
    assert checks_of(db_session, item["barMenuItemId"]) == []
    assert client.get("/api/search/bars", params={"query": "맥주 1"}).json()["items"] == []


def test_an_unlinked_whisky_opens_an_operator_check(client, db_session, owner, bar):  # noqa: F811
    before = catalog_size(db_session)

    response = add(client, bar.id, unlinked("whisky", "글렌알라키 10 CS"), owner)

    assert response.status_code == 201, response.text
    item = last_item(response)
    assert (item["kind"], item["productId"]) == ("whisky", None)
    assert catalog_size(db_session) == before
    assert checks_of(db_session, item["barMenuItemId"]) == [(CheckStatus.OPEN, [CheckReason.UNLINKED])]
    check = db_session.scalar(select(MenuItemCheck).where(MenuItemCheck.bar_menu_item_id == item["barMenuItemId"]))
    assert (check.bar_id, check.display_name, check.reasons[0].source_extracted_item_id) == (
        bar.id,
        "글렌알라키 10 CS",
        None,
    )


def test_the_same_name_key_on_the_board_is_the_same_item(client, owner, bar):  # noqa: F811
    first = add(client, bar.id, unlinked("other", "하이볼"), owner)

    # Normalization ignores spacing and case, and the kind does not matter.
    response = add(client, bar.id, unlinked("whisky", " 하 이 볼 ", menu_version=5), owner)

    assert error(response) == (409, "MENU_ITEM_EXISTS")
    assert response.json()["error"]["details"] == {"barMenuItemId": last_item(first)["barMenuItemId"]}


def test_an_unlinked_item_that_left_the_board_is_not_reused(client, db_session, owner, bar):  # noqa: F811
    first = last_item(add(client, bar.id, unlinked("whisky", "글렌알라키 10 CS"), owner))
    assert delete(client, bar.id, first["barMenuItemId"], 5, owner).status_code == 200

    again = add(client, bar.id, unlinked("whisky", "글렌알라키 10 CS", menu_version=6), owner)

    assert again.status_code == 201, again.text
    second = last_item(again)
    assert second["barMenuItemId"] != first["barMenuItemId"]
    # The first item's check closed when it left the board; the new item has its own.
    assert checks_of(db_session, first["barMenuItemId"]) == [(CheckStatus.DISMISSED, [CheckReason.UNLINKED])]
    assert checks_of(db_session, second["barMenuItemId"]) == [(CheckStatus.OPEN, [CheckReason.UNLINKED])]


def test_an_unlinked_item_needs_a_name_that_normalizes(client, owner, bar):  # noqa: F811
    missing = add(client, bar.id, {"menuVersion": 4, "kind": "other", "options": [option()]}, owner)
    blank = add(client, bar.id, unlinked("other", "!!"), owner)

    assert field_errors(missing) == [("displayName", "MISSING")]
    assert field_errors(blank) == [("displayName", "NOT_NORMALIZABLE")]


@pytest.mark.parametrize(
    "fields",
    [{"productId": "x"}, {"newProduct": "x"}],
    ids=["with-productId", "with-newProduct"],
)
def test_kind_is_one_of_three_ways_to_add(client, owner, bar, glenfiddich, fields):  # noqa: F811
    values = {"productId": str(glenfiddich[15].id)} if "productId" in fields else {"newProduct": {
        "brand": {"type": "new", "canonicalName": "Kavalan"}, "product": {"displayName": "Kavalan Classic"}
    }}

    response = add(client, bar.id, {**unlinked("whisky", "카발란"), **values}, owner)

    assert field_errors(response) == [("productId", "EXACTLY_ONE_REQUIRED")]


def test_an_unknown_kind_is_rejected(client, owner, bar):  # noqa: F811
    response = add(client, bar.id, unlinked("beer", "맥주 1"), owner)

    assert [code for _, code in field_errors(response)] == ["ENUM"]


# ---- the catalog is the operators' ----


NEW_PRODUCT = {"brand": {"type": "new", "canonicalName": "Kavalan"}, "product": {"displayName": "Kavalan Classic"}}


def test_an_owner_cannot_create_a_catalog_product(client, db_session, owner, bar):  # noqa: F811
    before = catalog_size(db_session)

    response = add(client, bar.id, {"menuVersion": 4, "newProduct": NEW_PRODUCT, "options": [option()]}, owner)

    assert field_errors(response) == [("newProduct", "OPERATOR_ONLY")]
    assert catalog_size(db_session) == before


def test_a_new_catalog_product_is_a_whisky(client, operator, bar):  # noqa: F811
    product = {**NEW_PRODUCT, "product": {"displayName": "Kavalan Classic", "category": "gin"}}

    response = add(client, bar.id, {"menuVersion": 4, "newProduct": product, "options": [option()]}, operator)

    assert field_errors(response) == [("newProduct.product.category", "LITERAL_ERROR")]


def test_an_owner_is_refused_the_catalog_only_after_the_bar_checks(client, owner, bar):  # noqa: F811
    """OPERATOR_ONLY is a business rule, checked after the menu version (spec 3.14.1)."""
    response = add(client, bar.id, {"menuVersion": 3, "newProduct": NEW_PRODUCT, "options": [option()]}, owner)

    assert error(response) == (409, "MENU_OUTDATED")


# ---- editing, deleting and resetting ----


def test_renaming_an_unlinked_item_moves_its_name_key_and_check(client, db_session, owner, bar):  # noqa: F811
    item = last_item(add(client, bar.id, unlinked("whisky", "글렌알라키 10"), owner))

    response = edit(
        client, bar.id, item["barMenuItemId"], {"menuVersion": 5, "displayName": "글렌알라키 10 CS", "options": [option()]}, owner
    )

    assert response.status_code == 200, response.text
    db_session.expire_all()
    row = db_session.get(BarMenuItem, item["barMenuItemId"])
    assert (row.name_key, row.kind, row.product_id) == ("글렌알라키10cs", MenuItemKind.WHISKY, None)
    check = db_session.scalar(select(MenuItemCheck).where(MenuItemCheck.bar_menu_item_id == row.id))
    assert check.display_name == "글렌알라키 10 CS"


def test_renaming_to_another_unlinked_items_name_is_a_conflict(client, owner, bar):  # noqa: F811
    first = last_item(add(client, bar.id, unlinked("other", "하이볼"), owner))
    second = last_item(add(client, bar.id, unlinked("other", "진토닉", menu_version=5), owner))

    response = edit(client, bar.id, second["barMenuItemId"], {"menuVersion": 6, "displayName": "하이볼", "options": [option()]}, owner)
    keep_name = edit(client, bar.id, first["barMenuItemId"], {"menuVersion": 6, "displayName": "하이 볼", "options": [option()]}, owner)

    assert error(response) == (409, "MENU_ITEM_EXISTS")
    assert response.json()["error"]["details"] == {"barMenuItemId": first["barMenuItemId"]}
    # The item's own key is no conflict.
    assert keep_name.status_code == 200, keep_name.text


def test_renaming_an_unlinked_item_to_nothing_is_rejected(client, owner, bar):  # noqa: F811
    item = last_item(add(client, bar.id, unlinked("other", "하이볼"), owner))

    response = edit(client, bar.id, item["barMenuItemId"], {"menuVersion": 5, "displayName": "!!", "options": [option()]}, owner)

    assert field_errors(response) == [("displayName", "NOT_NORMALIZABLE")]


def test_an_edit_cannot_change_the_kind(client, owner, bar):  # noqa: F811
    item = last_item(add(client, bar.id, unlinked("other", "하이볼"), owner))
    body = {"menuVersion": 5, "displayName": "하이볼", "kind": "whisky", "options": [option()]}

    response = edit(client, bar.id, item["barMenuItemId"], body, owner)

    assert field_errors(response) == [("kind", "EXTRA_FORBIDDEN")]


def test_a_reset_dismisses_the_open_checks(client, db_session, owner, bar):  # noqa: F811
    item = last_item(add(client, bar.id, unlinked("whisky", "글렌알라키 10 CS"), owner))

    assert reset(client, bar.id, {"menuVersion": 5}, owner).status_code == 200

    assert checks_of(db_session, item["barMenuItemId"]) == [(CheckStatus.DISMISSED, [CheckReason.UNLINKED])]


def test_a_linked_item_with_the_same_name_is_no_conflict(client, db_session, owner, bar, glenfiddich):  # noqa: F811
    """Name keys only tell unlinked items apart; a product's item is known by its product."""
    response = add(client, bar.id, unlinked("whisky", "글렌피딕 12년"), owner)

    assert response.status_code == 201, response.text
