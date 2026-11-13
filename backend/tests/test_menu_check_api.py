"""The operator's menu item check list and resolving a check (API spec 3.18.2, 3.18.3, 3.14.1)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import (
    BarMenuItem,
    BarStatus,
    CheckReason,
    ImportMode,
    ImportStatus,
    MenuBoard,
    MenuImport,
    MenuItemCheck,
    MenuItemKind,
    Product,
    ProductAlias,
    User,
    UserType,
)
from app.services.menu_checks import raise_check
from tests.factories import make_bar, make_product, make_user, publish_menu
from tests.review_support import make_glenfiddich

PUBLISHED = datetime(2026, 11, 10, 9, tzinfo=timezone.utc)
OPERATOR_SUBJECT = "check-operator"


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


@pytest.fixture
def bar(db_session, glenfiddich):
    """A bar selling Glenfiddich 12 (glass 17,000, bottle 160,000) at menu version 1."""
    bar = make_bar(db_session, "Seorosang")
    publish_menu(
        db_session, bar, [(glenfiddich[12], "글렌피딕 12년", [("잔", 30, 17000), ("병", None, 160000)])], published_at=PUBLISHED
    )
    db_session.commit()
    return bar


def add_unlinked(client, bar, operator, name="글렌알라키 10 CS", kind="whisky", options=None) -> dict:
    menu = client.get(f"/api/bars/{bar.id}/menu").json()
    body = {
        "menuVersion": menu["menuVersion"],
        "kind": kind,
        "displayName": name,
        "options": options or [{"optionLabel": "잔", "pourMl": 30, "priceKrw": 26000}],
    }
    response = client.post(f"/api/bars/{bar.id}/menu/items", json=body, headers=operator)
    assert response.status_code == 201, response.text
    return response.json()["items"][-1]


def checks(client, operator, **params) -> dict:
    response = client.get("/api/menu-item-checks", params=params, headers=operator)
    assert response.status_code == 200, response.text
    return response.json()


def resolve(client, check_id, body, headers):
    return client.post(f"/api/menu-item-checks/{check_id}/resolve", json=body, headers=headers)


def error(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def field_errors(response) -> list[tuple[str, str]]:
    assert error(response) == (422, "VALIDATION_FAILED"), response.text
    return [(e["path"], e["code"]) for e in response.json()["error"]["fieldErrors"]]


def menu(client, bar, headers=None) -> dict:
    return client.get(f"/api/bars/{bar.id}/menu", headers=headers or {}).json()


@pytest.fixture
def unlinked(client, bar, operator) -> tuple[dict, dict]:
    """(the unlinked whisky's menu item, its open check)."""
    item = add_unlinked(client, bar, operator)
    [check] = checks(client, operator)["items"]
    return item, check


# ---- the list ----


def test_the_list_shows_an_open_check_with_its_item(client, bar, operator, unlinked):
    item, check = unlinked

    assert check["status"] == "open"
    assert [(r["reason"], r["source"]) for r in check["reasons"]] == [("unlinked", None)]
    assert (check["resolvedAt"], check["resolution"], check["resolvedProductId"], check["discardedOptions"]) == (
        None,
        None,
        None,
        [],
    )
    assert check["bar"] == {"barId": str(bar.id), "name": "Seorosang", "status": "active"}
    assert check["item"] == {
        "barMenuItemId": item["barMenuItemId"],
        "kind": "whisky",
        "displayName": "글렌알라키 10 CS",
        "onBoard": True,
        "soldOut": False,
        "product": None,
        "options": [{"optionLabel": "잔", "pourMl": 30, "priceKrw": 26000}],
    }


def test_a_review_reason_carries_its_line(client, db_session, image_storage, operator, glenfiddich):
    from tests.review_support import upload_sample_review, valid_body

    sample = upload_sample_review(client, db_session, operator, glenfiddich)
    body = valid_body(sample, glenfiddich)
    unknown = body["itemDecisions"][3]
    body["itemDecisions"][3] = {
        "action": "publish_without_product",
        "extractedItemId": unknown["extractedItemId"],
        "finalLineType": "product",
        "kind": "whisky",
        "options": unknown["options"],
    }
    assert client.post(f"/api/menu-imports/{sample.menu_import.id}/review-and-apply", json=body, headers=operator).status_code == 200

    [check] = checks(client, operator)["items"]

    source = check["reasons"][0]["source"]
    assert (source["menuImportId"], source["extractedItemId"], source["rawText"]) == (
        str(sample.menu_import.id),
        unknown["extractedItemId"],
        sample.items[3].raw_text,
    )
    assert (source["extractedProductName"], source["sourceBox"], source["imageUrlExpiresAt"]) == (
        "Unknown Distillery 25",
        None,
        None,
    )
    assert source["imageUrl"].startswith("http")


def test_filters_order_and_pages(client, db_session, bar, operator):
    first, second = add_unlinked(client, bar, operator, "A"), add_unlinked(client, bar, operator, "B")
    other_bar = make_bar(db_session, "Other")
    publish_menu(db_session, other_bar, [])
    db_session.commit()
    add_unlinked(client, other_bar, operator, "C")

    page = checks(client, operator, limit=1, barId=str(bar.id))
    rest = checks(client, operator, limit=1, barId=str(bar.id), cursor=page["nextCursor"])

    # Two pages of one check each, together the bar's checks; open checks come oldest first, and the
    # test's single transaction gives them the same created_at, so the id breaks the tie.
    paged = [c["item"]["barMenuItemId"] for c in page["items"] + rest["items"]]
    assert sorted(paged) == sorted([first["barMenuItemId"], second["barMenuItemId"]])
    assert [c["checkId"] for c in page["items"] + rest["items"]] == sorted(c["checkId"] for c in page["items"] + rest["items"])
    assert rest["nextCursor"] is None
    assert len(checks(client, operator)["items"]) == 3
    stale = client.get("/api/menu-item-checks", params={"cursor": page["nextCursor"]}, headers=operator)
    assert field_errors(stale) == [("cursor", "INVALID_CURSOR")]


def test_closed_checks_come_newest_first_and_keep_the_name(client, db_session, bar, operator):
    first, second = add_unlinked(client, bar, operator, "A"), add_unlinked(client, bar, operator, "B")
    for item in (first, second):
        version = menu(client, bar)["menuVersion"]
        url = f"/api/bars/{bar.id}/menu/items/{item['barMenuItemId']}"
        assert client.delete(url, params={"menuVersion": version}, headers=operator).status_code == 200

    dismissed = checks(client, operator, status="dismissed")["items"]

    assert [(c["item"]["displayName"], c["item"]["onBoard"], c["item"]["options"]) for c in dismissed] == [
        ("B", False, []),
        ("A", False, []),
    ]
    assert all(c["resolvedAt"] is not None for c in dismissed)
    page = checks(client, operator, status="dismissed", limit=1)
    assert [c["item"]["displayName"] for c in checks(client, operator, status="dismissed", limit=1, cursor=page["nextCursor"])["items"]] == ["A"]


@pytest.mark.parametrize("params", [{"status": "closed"}, {"barId": "x"}, {"limit": 0}, {"limit": 201}])
def test_bad_list_filters(client, operator, params):
    assert error(client.get("/api/menu-item-checks", params=params, headers=operator)) == (422, "VALIDATION_FAILED")


# ---- linking ----


def test_linking_an_unlinked_whisky_makes_it_searchable(client, db_session, supabase, bar, glenfiddich, unlinked):
    item, check = unlinked
    make_user(db_session, OPERATOR_SUBJECT, user_type=UserType.OPERATOR)
    db_session.commit()
    signed_in = {"Authorization": f"Bearer {supabase.token(sub=OPERATOR_SUBJECT)}"}
    product = make_product(db_session, glenfiddich["brand"], "GlenAllachie 10 CS")
    db_session.commit()
    before = menu(client, bar)

    response = resolve(
        client,
        check["checkId"],
        {"resolution": "link_existing", "productId": str(product.id), "aliasesToAdd": [{"aliasText": "글렌알라키 10 CS"}]},
        signed_in,
    )

    assert response.status_code == 200, response.text
    resolved = response.json()
    assert (resolved["status"], resolved["resolution"], resolved["resolvedProductId"]) == (
        "resolved",
        "link_existing",
        str(product.id),
    )
    assert resolved["item"]["product"]["productId"] == str(product.id)
    after = menu(client, bar)
    # The same item, now linked; the version moves, the publish time does not (spec 3.18.3).
    assert after["items"][-1]["barMenuItemId"] == item["barMenuItemId"]
    assert (after["menuVersion"], after["publishedAt"]) == (before["menuVersion"] + 1, before["publishedAt"])
    db_session.expire_all()
    row = db_session.get(MenuItemCheck, check["checkId"])
    assert row.resolved_by_user_id == db_session.scalar(select(User.id).where(User.auth_subject == OPERATOR_SUBJECT))
    found = client.get("/api/search/bars", params={"query": "글렌알라키 10 CS"}).json()["items"]
    assert [(i["barId"], i["productId"]) for i in found] == [(str(bar.id), str(product.id))]
    assert db_session.scalar(select(ProductAlias).where(ProductAlias.alias_text == "글렌알라키 10 CS")) is not None


def test_linking_to_a_product_sold_before_moves_the_line_to_its_item(client, db_session, bar, operator, glenfiddich, unlinked):
    item, check = unlinked
    old = BarMenuItem(bar_id=bar.id, product_id=glenfiddich[15].id)
    db_session.add(old)
    db_session.commit()

    response = resolve(client, check["checkId"], {"resolution": "link_existing", "productId": str(glenfiddich[15].id)}, operator)

    assert response.status_code == 200, response.text
    # The check stays on the item it was resolved on, which has left the board.
    assert (response.json()["item"]["barMenuItemId"], response.json()["item"]["onBoard"]) == (item["barMenuItemId"], False)
    lines = menu(client, bar)["items"]
    assert [(i["barMenuItemId"], i["displayName"], i["productId"]) for i in lines][-1] == (
        str(old.id),
        "글렌알라키 10 CS",
        str(glenfiddich[15].id),
    )


def test_linking_to_a_product_on_the_board_merges_the_lines(client, db_session, bar, operator, glenfiddich):
    # Same glass with another price (dropped), and a half bottle the board does not have (added).
    item = add_unlinked(
        client,
        bar,
        operator,
        "글렌피딕 십이년",
        options=[{"optionLabel": "잔", "pourMl": 30, "priceKrw": 18000}, {"optionLabel": "하프", "pourMl": 350, "priceKrw": 90000}],
    )
    [check] = checks(client, operator)["items"]

    response = resolve(client, check["checkId"], {"resolution": "link_existing", "productId": str(glenfiddich[12].id)}, operator)

    assert response.status_code == 200, response.text
    [line] = menu(client, bar)["items"]
    assert (line["displayName"], [(o["optionLabel"], o["priceKrw"]) for o in line["options"]]) == (
        "글렌피딕 12년",
        [("잔", 17000), ("병", 160000), ("하프", 90000)],
    )
    [conflict] = checks(client, operator)["items"]
    assert conflict["item"]["barMenuItemId"] == line["barMenuItemId"]
    assert [r["reason"] for r in conflict["reasons"]] == ["price_conflict"]
    assert conflict["discardedOptions"] == [
        {"optionLabel": "잔", "pourMl": 30, "priceKrw": 18000, "displayName": "글렌피딕 십이년", "extractedItemId": None}
    ]
    assert item["barMenuItemId"] != line["barMenuItemId"]


def test_create_and_link_makes_a_whisky_product(client, db_session, bar, operator, glenfiddich, unlinked):
    _, check = unlinked
    body = {
        "resolution": "create_and_link",
        "brand": {"type": "existing", "brandId": str(glenfiddich["brand"].id)},
        "product": {"displayName": "GlenAllachie 10 Cask Strength", "ageYears": 10},
    }

    response = resolve(client, check["checkId"], body, operator)

    assert response.status_code == 200, response.text
    product = db_session.scalar(select(Product).where(Product.display_name == "GlenAllachie 10 Cask Strength"))
    assert response.json()["resolvedProductId"] == str(product.id)
    assert menu(client, bar)["items"][-1]["productId"] == str(product.id)


def test_create_and_link_of_an_existing_product_is_a_conflict(client, bar, operator, glenfiddich, unlinked):
    _, check = unlinked
    body = {
        "resolution": "create_and_link",
        "brand": {"type": "existing", "brandId": str(glenfiddich["brand"].id)},
        "product": {"displayName": "Glenfiddich 12"},
    }

    response = resolve(client, check["checkId"], body, operator)

    assert error(response) == (409, "DUPLICATE_PRODUCT_FOUND")
    assert "extractedItemId" not in response.json()["error"]["details"]
    assert checks(client, operator)["items"][0]["status"] == "open"


# ---- keep and mark_as_other ----


def test_keep_confirms_a_linked_item_without_a_new_version(client, db_session, bar, operator, glenfiddich):
    item = db_session.scalar(select(BarMenuItem).where(BarMenuItem.bar_id == bar.id))
    entry_name = menu(client, bar)["items"][0]["displayName"]
    raise_check(db_session, item, entry_name, CheckReason.ATTRIBUTE_CONFLICT)
    db_session.commit()
    [check] = checks(client, operator)["items"]
    version = menu(client, bar)["menuVersion"]

    response = resolve(client, check["checkId"], {"resolution": "keep"}, operator)

    assert response.status_code == 200, response.text
    assert (response.json()["resolution"], response.json()["resolvedProductId"]) == ("keep", str(glenfiddich[12].id))
    assert menu(client, bar)["menuVersion"] == version


def test_mark_as_other_makes_a_non_whisky_menu(client, db_session, bar, operator, unlinked):
    item, check = unlinked
    version = menu(client, bar)["menuVersion"]

    response = resolve(client, check["checkId"], {"resolution": "mark_as_other"}, operator)

    assert response.status_code == 200, response.text
    assert (response.json()["item"]["kind"], response.json()["resolvedProductId"]) == ("other", None)
    assert menu(client, bar)["items"][-1]["kind"] == "other"
    assert menu(client, bar)["menuVersion"] == version + 1


def test_a_resolution_must_fit_the_item(client, db_session, bar, operator, unlinked):
    _, check = unlinked
    linked = db_session.scalar(select(BarMenuItem).where(BarMenuItem.bar_id == bar.id, BarMenuItem.product_id.is_not(None)))
    raise_check(db_session, linked, "글렌피딕 12년", CheckReason.ATTRIBUTE_CONFLICT)
    db_session.commit()
    linked_check = next(c for c in checks(client, operator)["items"] if c["item"]["product"])

    assert field_errors(resolve(client, check["checkId"], {"resolution": "keep"}, operator)) == [
        ("resolution", "RESOLUTION_NOT_ALLOWED")
    ]
    assert field_errors(resolve(client, linked_check["checkId"], {"resolution": "mark_as_other"}, operator)) == [
        ("resolution", "RESOLUTION_NOT_ALLOWED")
    ]


# ---- errors ----


def test_an_unknown_check_is_not_found(client, operator):
    for check_id in (str(uuid4()), "not-a-uuid"):
        response = resolve(client, check_id, {"resolution": "keep"}, operator)
        assert error(response) == (404, "MENU_ITEM_CHECK_NOT_FOUND")
        assert response.json()["error"]["details"] == {"checkId": check_id}


def test_a_closed_check_cannot_be_resolved_again(client, bar, operator, unlinked):
    _, check = unlinked
    assert resolve(client, check["checkId"], {"resolution": "mark_as_other"}, operator).status_code == 200

    again = resolve(client, check["checkId"], {"resolution": "mark_as_other"}, operator)

    assert error(again) == (409, "INVALID_CHECK_STATE")
    assert again.json()["error"]["details"] == {"checkId": check["checkId"], "status": "resolved"}


def test_nothing_is_resolved_while_an_import_is_unfinished(client, db_session, bar, operator, unlinked):
    _, check = unlinked
    db_session.add(
        MenuImport(
            idempotency_key=str(uuid4()),
            request_fingerprint="0" * 64,
            bar_id=bar.id,
            mode=ImportMode.FULL_REPLACE,
            status=ImportStatus.READY_FOR_REVIEW,
        )
    )
    db_session.commit()

    response = resolve(client, check["checkId"], {"resolution": "mark_as_other"}, operator)

    assert error(response) == (409, "ACTIVE_IMPORT_EXISTS")
    assert checks(client, operator)["items"][0]["status"] == "open"


def test_an_inactive_bar_is_not_found(client, db_session, bar, operator, unlinked):
    _, check = unlinked
    bar.status = BarStatus.INACTIVE
    db_session.commit()

    assert error(resolve(client, check["checkId"], {"resolution": "mark_as_other"}, operator)) == (404, "BAR_NOT_FOUND")


def test_product_and_brand_errors(client, db_session, bar, operator, glenfiddich, unlinked):
    _, check = unlinked

    def link(product_id):
        return resolve(client, check["checkId"], {"resolution": "link_existing", "productId": str(product_id)}, operator)

    assert field_errors(link(uuid4())) == [("productId", "PRODUCT_NOT_FOUND")]
    assert field_errors(link(glenfiddich[21].id)) == [("productId", "PRODUCT_INACTIVE")]
    missing_brand = {
        "resolution": "create_and_link",
        "brand": {"type": "existing", "brandId": str(uuid4())},
        "product": {"displayName": "X 10"},
    }
    assert field_errors(resolve(client, check["checkId"], missing_brand, operator)) == [("brand.brandId", "BRAND_NOT_FOUND")]


def test_request_rules_come_first(client, operator):
    gin = {
        "resolution": "create_and_link",
        "brand": {"type": "new", "canonicalName": "!!"},
        "product": {"displayName": "X", "category": "gin"},
    }
    blank_alias = {"resolution": "link_existing", "productId": str(uuid4()), "aliasesToAdd": [{"aliasText": "!!"}]}

    assert field_errors(resolve(client, uuid4(), gin, operator)) == [("product.category", "LITERAL_ERROR")]
    assert field_errors(resolve(client, uuid4(), blank_alias, operator)) == [("aliasesToAdd[0].aliasText", "NOT_NORMALIZABLE")]
    assert field_errors(resolve(client, uuid4(), {"resolution": "approve"}, operator)) == [("", "UNION_TAG_INVALID")]


# ---- more of the relink rule (spec 3.14.1) ----


def linked_check(client, db_session, bar, operator) -> dict:
    """An attribute_conflict check on the board's Glenfiddich 12."""
    item = db_session.scalar(select(BarMenuItem).where(BarMenuItem.bar_id == bar.id))
    raise_check(db_session, item, "글렌피딕 12년", CheckReason.ATTRIBUTE_CONFLICT)
    db_session.commit()
    [check] = checks(client, operator)["items"]
    return check


def test_linking_to_the_current_product_changes_nothing_but_closes_the_check(client, db_session, bar, operator, glenfiddich):
    check = linked_check(client, db_session, bar, operator)
    version = menu(client, bar)["menuVersion"]

    response = resolve(client, check["checkId"], {"resolution": "link_existing", "productId": str(glenfiddich[12].id)}, operator)

    assert (response.status_code, response.json()["status"]) == (200, "resolved")
    assert menu(client, bar)["menuVersion"] == version


def test_relinking_a_linked_line_moves_it_to_the_other_products_new_item(client, db_session, bar, operator, glenfiddich):
    check = linked_check(client, db_session, bar, operator)
    before = menu(client, bar)["items"][0]

    response = resolve(client, check["checkId"], {"resolution": "link_existing", "productId": str(glenfiddich[15].id)}, operator)

    assert response.status_code == 200, response.text
    [line] = menu(client, bar)["items"]
    assert (line["productId"], line["displayName"], line["options"]) == (
        str(glenfiddich[15].id),
        "글렌피딕 12년",
        before["options"],
    )
    assert line["barMenuItemId"] != before["barMenuItemId"]
    # The 12's item stays for a later add of the same product.
    assert db_session.get(BarMenuItem, before["barMenuItemId"]).product_id == glenfiddich[12].id


def test_merging_review_options_keeps_their_lines_in_discarded_options(client, db_session, image_storage, operator, glenfiddich):
    from tests.review_support import upload_sample_review, valid_body

    sample = upload_sample_review(client, db_session, operator, glenfiddich)
    body = valid_body(sample, glenfiddich)
    unknown = body["itemDecisions"][3]
    source = unknown["options"][0]["extractedOptionId"]
    body["itemDecisions"][3] = {
        "action": "publish_without_product",
        "extractedItemId": unknown["extractedItemId"],
        "finalLineType": "product",
        "kind": "whisky",
        # The same 30 ml price as the 12 (kept once), and a 15 ml price that differs (dropped).
        "options": [{"extractedOptionId": source, "pourMl": 15, "priceKrw": 8000}, {"pourMl": 30, "priceKrw": 17000}],
    }
    assert client.post(f"/api/menu-imports/{sample.menu_import.id}/review-and-apply", json=body, headers=operator).status_code == 200
    [check] = checks(client, operator)["items"]

    response = resolve(client, check["checkId"], {"resolution": "link_existing", "productId": str(glenfiddich[12].id)}, operator)

    assert response.status_code == 200, response.text
    [line] = menu(client, sample.bar)["items"]
    assert [(o["pourMl"], o["priceKrw"]) for o in line["options"]] == [(15, 9000), (30, 17000)]
    [conflict] = checks(client, operator)["items"]
    assert conflict["discardedOptions"] == [
        {
            "optionLabel": None,
            "pourMl": 15,
            "priceKrw": 8000,
            "displayName": "Unknown Distillery 25",
            "extractedItemId": unknown["extractedItemId"],
        }
    ]


def test_create_and_link_with_a_new_brand(client, db_session, bar, operator, unlinked):
    _, check = unlinked
    body = {
        "resolution": "create_and_link",
        "brand": {"type": "new", "canonicalName": "GlenAllachie", "aliases": [{"aliasText": "글렌알라키"}]},
        "product": {"displayName": "GlenAllachie 10 CS"},
    }

    response = resolve(client, check["checkId"], body, operator)

    assert response.status_code == 200, response.text
    assert response.json()["item"]["product"]["brandName"] == "GlenAllachie"
    blank = {**body, "brand": {"type": "new", "canonicalName": "X", "aliases": [{"aliasText": "!!"}]}}
    assert field_errors(resolve(client, uuid4(), blank, operator)) == [("brand.aliases[0].aliasText", "NOT_NORMALIZABLE")]


def test_an_open_check_of_an_item_off_the_board_cannot_be_resolved(client, db_session, bar, operator, glenfiddich):
    off_board = BarMenuItem(bar_id=bar.id, product_id=glenfiddich[15].id)
    db_session.add(off_board)
    db_session.flush()
    raise_check(db_session, off_board, "글렌피딕 15년", CheckReason.ATTRIBUTE_CONFLICT)
    db_session.commit()
    [check] = checks(client, operator)["items"]

    assert error(resolve(client, check["checkId"], {"resolution": "keep"}, operator)) == (409, "INVALID_CHECK_STATE")
