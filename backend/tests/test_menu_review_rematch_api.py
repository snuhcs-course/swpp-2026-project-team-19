"""Rematching a line whose name the reviewer corrected (API spec 8.11), through the review API.

The sample menu: 글렌피딕 12년 (exact, Glenfiddich 12), Glenfiddich 12 read with age 15 (ambiguous,
Glenfiddich 12), Unknown Distillery 25 (unmatched), for a bar selling Glenfiddich 12 and 15.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import (
    BarMenuItem,
    CheckReason,
    ExtractedItem,
    MatchMethod,
    MenuChangeType,
    MenuItemCheck,
    MenuItemKind,
    ProductAlias,
    ReviewStatus,
)
from tests.factories import make_product
from tests.review_support import make_glenfiddich, options_of, upload_sample_review, valid_body


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


@pytest.fixture
def sample(client, db_session, image_storage, operator, glenfiddich):
    return upload_sample_review(client, db_session, operator, glenfiddich)


def apply(client, sample, body, operator) -> dict:
    response = client.post(f"/api/menu-imports/{sample.menu_import.id}/review-and-apply", json=body, headers=operator)
    assert response.status_code == 200, response.text
    return response.json()


def menu(client, sample, headers=None) -> list[tuple]:
    """The menu as customers see it, or as a manager with `headers` (sold-out items too)."""
    items = client.get(f"/api/bars/{sample.bar.id}/menu", headers=headers or {}).json()["items"]
    return [(i["displayName"], i["productId"], [o["priceKrw"] for o in i["options"]]) for i in items]


def checks(db_session, sample) -> dict:
    """Open and closed checks of the bar: {bar menu item id: [(reason, source line)]}."""
    db_session.expire_all()
    rows = db_session.scalars(select(MenuItemCheck).where(MenuItemCheck.bar_id == sample.bar.id))
    return {c.bar_menu_item_id: [(r.reason, r.source_extracted_item_id) for r in c.reasons] for c in rows}


def renamed(sample, glenfiddich, name, product=12, **fields):
    """The sample body with the exact 12 line's name corrected to `name`, still sent as `product`."""
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][1] = {
        **body["itemDecisions"][1],
        "productId": str(glenfiddich[product].id),
        "correctedProductName": name,
        **fields,
    }
    return body


def item_of(db_session, sample, product):
    return db_session.scalar(
        select(BarMenuItem).where(BarMenuItem.bar_id == sample.bar.id, BarMenuItem.product_id == product.id)
    )


def test_a_name_naming_another_product_links_that_product_and_is_checked(
    client, db_session, sample, operator, glenfiddich
):
    exact = sample.items[1]
    body = renamed(sample, glenfiddich, "글렌피딕 15년", aliasesToAdd=[{"aliasText": "글렌피딕 15년 잔"}])

    apply(client, sample, body, operator)

    # The line now names the 15, already on the board: it joins the 15, and the 12 it was compared with
    # leaves, since the owner changed one card (spec 8.11).
    assert [(name, product, prices) for name, product, prices in menu(client, sample)][0] == (
        "글렌피딕 15년",
        str(glenfiddich[15].id),
        [9000, 17000],
    )
    assert [name for name, *_ in menu(client, sample)] == ["글렌피딕 15년", "Unknown Distillery 25"]
    fifteen = item_of(db_session, sample, glenfiddich[15])
    assert checks(db_session, sample)[fifteen.id] == [(CheckReason.RELINKED_BY_NAME, exact.id)]
    db_session.expire_all()
    line = db_session.get(ExtractedItem, exact.id)
    assert (line.selected_product_id, line.selected_match_method, line.match_confidence, line.review_status) == (
        glenfiddich[15].id,
        MatchMethod.MANUAL,
        None,
        ReviewStatus.CORRECTED,
    )
    # The alias was for the product sent; an operator adds the spelling when checking (spec 3.18.3).
    aliases = db_session.scalars(select(ProductAlias.alias_text).where(ProductAlias.product_id == glenfiddich[12].id))
    assert "글렌피딕 15년 잔" not in set(aliases)


def test_a_name_naming_no_product_publishes_an_unlinked_whisky_in_the_same_place(
    client, db_session, sample, operator, glenfiddich
):
    exact = sample.items[1]
    twelve = sample.board.entries[0].bar_menu_item
    twelve.sold_out_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
    db_session.commit()

    result = apply(client, sample, renamed(sample, glenfiddich, "글렌피딕 미스터리 캐스크"), operator)

    assert result["result"]["unlinkedWhisky"] == 1
    # In the 12's place, sold out like it (a manager sees sold-out items).
    assert [(name, product) for name, product, _ in menu(client, sample, operator)][0] == ("글렌피딕 미스터리 캐스크", None)
    db_session.expire_all()
    unlinked = db_session.scalar(
        select(BarMenuItem).where(BarMenuItem.bar_id == sample.bar.id, BarMenuItem.product_id.is_(None))
    )
    assert (unlinked.kind, unlinked.name_key, unlinked.sold_out_at is not None) == (
        MenuItemKind.WHISKY,
        "글렌피딕미스터리캐스크",
        True,
    )
    # The 12's item stays the 12's and goes back on sale off the board.
    assert db_session.get(BarMenuItem, twelve.id).sold_out_at is None
    assert checks(db_session, sample)[unlinked.id] == [(CheckReason.UNLINKED_BY_NAME, exact.id)]
    line = db_session.get(ExtractedItem, exact.id)
    assert (line.selected_product_id, line.selected_match_method) == (None, None)


def test_a_name_naming_the_product_sent_keeps_it_and_its_aliases(client, db_session, sample, operator, glenfiddich):
    body = renamed(sample, glenfiddich, "Glenfiddich 12", aliasesToAdd=[{"aliasText": "글렌피딕 12 잔"}])

    apply(client, sample, body, operator)

    assert menu(client, sample)[0][:2] == ("Glenfiddich 12", str(glenfiddich[12].id))
    assert checks(db_session, sample) == {}
    aliases = db_session.scalars(select(ProductAlias.alias_text).where(ProductAlias.product_id == glenfiddich[12].id))
    assert "글렌피딕 12 잔" in set(aliases)


def test_spacing_or_symbols_alone_are_not_a_corrected_name(client, db_session, sample, operator, glenfiddich):
    # "글렌피딕12년" normalizes like the line's "글렌피딕 12년", so the line is not matched again.
    apply(client, sample, renamed(sample, glenfiddich, "글렌피딕12년", product=15), operator)

    assert menu(client, sample)[0][:2] == ("글렌피딕12년", str(glenfiddich[15].id))
    assert CheckReason.RELINKED_BY_NAME not in {r for reasons in checks(db_session, sample).values() for r, _ in reasons}


def test_an_inactive_product_is_never_confirmed(client, db_session, sample, operator, glenfiddich):
    apply(client, sample, renamed(sample, glenfiddich, "Glenfiddich 21"), operator)

    assert menu(client, sample)[0][:2] == ("Glenfiddich 21", None)


def test_a_line_published_without_a_product_is_linked_when_its_name_names_one(
    client, db_session, sample, operator, glenfiddich
):
    unknown = sample.items[3]
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][3] = {
        "action": "publish_without_product",
        "extractedItemId": str(unknown.id),
        "finalLineType": "product",
        "kind": "whisky",
        "correctedProductName": "글렌피딕 15년",
        "options": options_of(unknown),
    }

    apply(client, sample, body, operator)

    fifteen = item_of(db_session, sample, glenfiddich[15])
    assert ("글렌피딕 15년", str(glenfiddich[15].id), [45000]) in menu(client, sample)
    assert checks(db_session, sample)[fifteen.id] == [(CheckReason.RELINKED_BY_NAME, unknown.id)]


def test_a_line_read_as_other_is_matched_when_published_as_a_whisky(
    client, db_session, sample, operator, glenfiddich
):
    """The AI did not match a line it read as other, so it is matched now even with its name unchanged."""
    unknown = sample.items[3]
    product = make_product(db_session, glenfiddich["brand"], "Unknown Distillery 25", age_years=25)
    db_session.execute(
        ExtractedItem.__table__.update().where(ExtractedItem.id == unknown.id).values(extracted_kind=MenuItemKind.OTHER)
    )
    db_session.commit()
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][3] = {
        "action": "publish_without_product",
        "extractedItemId": str(unknown.id),
        "finalLineType": "product",
        "kind": "whisky",
        "options": options_of(unknown),
    }

    apply(client, sample, body, operator)

    assert ("Unknown Distillery 25", str(product.id), [45000]) in menu(client, sample)


def test_lines_rematching_joins_keep_the_price_of_the_line_not_renamed(
    client, db_session, sample, operator, glenfiddich
):
    """The 15yo line, sent as the 15 but renamed to the 12, joins the exact 12 line: its 30 ml price differs,
    which the owner could not see, so it is not refused (spec 8.12)."""
    _, exact, conflict, *_ = sample.items
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][2] = {
        "action": "select_existing_product",
        "extractedItemId": str(conflict.id),
        "finalLineType": "product",
        "productId": str(glenfiddich[15].id),
        "correctedProductName": "글렌피딕 12년",
        "options": options_of(conflict),
    }

    apply(client, sample, body, operator)

    assert menu(client, sample)[0] == ("글렌피딕 12년", str(glenfiddich[12].id), [9000, 17000])
    twelve = item_of(db_session, sample, glenfiddich[12])
    assert checks(db_session, sample)[twelve.id] == [
        (CheckReason.RELINKED_BY_NAME, conflict.id),
        (CheckReason.PRICE_CONFLICT, conflict.id),
    ]
    check = db_session.scalar(select(MenuItemCheck).where(MenuItemCheck.bar_menu_item_id == twelve.id))
    assert [(o["priceKrw"], o["extractedItemId"]) for o in check.discarded_options] == [(21000, str(conflict.id))]


def test_an_ignored_change_keeps_the_item_it_compared(client, db_session, sample, operator, glenfiddich):
    """With the 12's update ignored, the renamed line does not take the 12's place: it is published on its own."""
    body = renamed(sample, glenfiddich, "글렌피딕 미스터리 캐스크")
    for decision in body["changeDecisions"]:
        if decision["changeId"] == str(sample.changes[MenuChangeType.UPDATE].id):
            decision["decision"] = "ignore"

    apply(client, sample, body, operator)

    published = menu(client, sample)
    assert [name for name, *_ in published] == ["글렌피딕 미스터리 캐스크", "Unknown Distillery 25", "글렌피딕 12년"]
    assert (published[0][1], published[2][1]) == (None, str(glenfiddich[12].id))


@pytest.mark.parametrize("sold_before", [False, True])
def test_a_name_naming_a_product_off_the_board_moves_the_line_to_its_item(
    client, db_session, sample, operator, glenfiddich, sold_before
):
    """The 12's item keeps the 12; the line goes to an item of the 18 (the one the bar sold before, if any)
    in the 12's place, sold out like it."""
    eighteen = make_product(db_session, glenfiddich["brand"], "Glenfiddich 18", aliases=("글렌피딕 18년",), age_years=18)
    old = BarMenuItem(bar_id=sample.bar.id, product_id=eighteen.id) if sold_before else None
    if old is not None:
        db_session.add(old)
    twelve = sample.board.entries[0].bar_menu_item
    twelve.sold_out_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
    db_session.commit()

    apply(client, sample, renamed(sample, glenfiddich, "글렌피딕 18년"), operator)

    assert menu(client, sample, operator)[0][:2] == ("글렌피딕 18년", str(eighteen.id))
    db_session.expire_all()
    moved = item_of(db_session, sample, eighteen)
    assert moved.sold_out_at is not None
    if old is not None:
        assert moved.id == old.id
    assert (db_session.get(BarMenuItem, twelve.id).product_id, db_session.get(BarMenuItem, twelve.id).sold_out_at) == (
        glenfiddich[12].id,
        None,
    )
    assert checks(db_session, sample)[moved.id] == [(CheckReason.RELINKED_BY_NAME, sample.items[1].id)]


def test_an_unlinked_item_is_linked_in_place_when_its_renamed_line_names_a_product(
    client, db_session, sample, operator, glenfiddich
):
    """The bar's unlinked Unknown Distillery 25, uploaded again with the name corrected to a catalog product:
    the item is linked (spec 3.14.1), its unlinked reason goes, and relinked_by_name is added."""
    unknown = sample.items[3]
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][3] = {
        "action": "publish_without_product",
        "extractedItemId": str(unknown.id),
        "finalLineType": "product",
        "kind": "whisky",
        "options": options_of(unknown),
    }
    apply(client, sample, body, operator)
    db_session.expire_all()
    unlinked = db_session.scalar(
        select(BarMenuItem).where(BarMenuItem.bar_id == sample.bar.id, BarMenuItem.product_id.is_(None))
    )
    thirty = make_product(db_session, glenfiddich["brand"], "Unknown Distillery 30", age_years=30)
    db_session.commit()
    again = upload_again(client, db_session, sample, operator)
    items = again["items"]
    body = {
        "reviewVersion": 1,
        "itemDecisions": [
            {"action": "reject", "extractedItemId": str(item.id), "finalLineType": "product"}
            if item.extracted_line_type.value == "product"
            else {
                "action": "confirm_non_product",
                "extractedItemId": str(item.id),
                "finalLineType": item.extracted_line_type.value,
            }
            for item in items
        ],
        # Only the unknown line is published; the changes of the rejected lines are ignored.
        "changeDecisions": [
            {"changeId": str(c.id), "decision": "apply" if c.extracted_item_id in (None, items[3].id) else "ignore"}
            for c in again["changes"]
        ],
    }
    body["itemDecisions"][3] = {
        "action": "publish_without_product",
        "extractedItemId": str(items[3].id),
        "finalLineType": "product",
        "kind": "whisky",
        "correctedProductName": "Unknown Distillery 30",
        "options": options_of(items[3]),
    }
    response = client.post(f"/api/menu-imports/{again['import'].id}/review-and-apply", json=body, headers=operator)
    assert response.status_code == 200, response.text

    db_session.expire_all()
    linked = db_session.get(BarMenuItem, unlinked.id)
    assert (linked.product_id, linked.name_key) == (thirty.id, None)
    # The unlinked check closes with its reason kept (spec 3.18.1), and an operator checks the new link.
    found = db_session.scalars(
        select(MenuItemCheck).where(MenuItemCheck.bar_menu_item_id == linked.id).order_by(MenuItemCheck.created_at)
    )
    assert sorted((c.status.value, [r.reason for r in c.reasons]) for c in found) == [
        ("dismissed", [CheckReason.UNLINKED]),
        ("open", [CheckReason.RELINKED_BY_NAME]),
    ]


def upload_again(client, db_session, sample, operator) -> dict:
    from uuid import uuid4

    from app.models import MenuImport
    from app.services.menu_review_validation import load_items, pending_changes
    from tests.review_support import JPEG

    response = client.post(
        f"/api/bars/{sample.bar.id}/menu-imports",
        headers={**operator, "Idempotency-Key": str(uuid4())},
        data={"mode": "partial_update"},
        files=[("images", ("sample.jpg", JPEG, "image/jpeg"))],
    )
    assert response.status_code == 202, response.text
    db_session.expire_all()
    menu_import = db_session.get(MenuImport, response.json()["menuImportId"])
    return {"import": menu_import, "items": load_items(db_session, menu_import), "changes": pending_changes(db_session, menu_import)}
