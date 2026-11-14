"""Review submissions that publish lines without a product (API spec 5.4, 8.7, 8.8, 8.10 and 3.18.1).

The sample photo's fourth line, "Unknown Distillery 25", matches nothing in the catalog. Published
without a product it goes on the bar's menu only; an unlinked whisky opens an operator check. A later
upload of the same menu finds the same item by its name key, and once the catalog has the product,
a line matched to it links that item instead of adding a second one.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import (
    BarMenuItem,
    CheckReason,
    CheckStatus,
    ExtractedItem,
    MenuChangeType,
    MenuImport,
    MenuItemCheck,
    MenuItemKind,
    ReviewStatus,
)
from app.schemas.menu_review import ReviewAndApplyRequest
from app.services.menu_review_validation import load_items, pending_changes, validate_review
from tests.factories import make_product
from tests.review_support import JPEG, make_glenfiddich, options_of, upload_sample_review, valid_body


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


@pytest.fixture
def sample(client, db_session, image_storage, operator, glenfiddich):
    return upload_sample_review(client, db_session, operator, glenfiddich)


def without_product(body, index, kind="whisky", **fields):
    decision = body["itemDecisions"][index]
    body["itemDecisions"][index] = {
        "action": "publish_without_product",
        "extractedItemId": decision["extractedItemId"],
        "finalLineType": "product",
        "kind": kind,
        "options": decision["options"],
        **fields,
    }
    return body


def apply(client, menu_import_id, body, headers) -> dict:
    response = client.post(f"/api/menu-imports/{menu_import_id}/review-and-apply", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def menu_items(client, bar) -> list[tuple]:
    items = client.get(f"/api/bars/{bar.id}/menu").json()["items"]
    return [(i["displayName"], i["productId"], i["kind"], [o["priceKrw"] for o in i["options"]]) for i in items]


def checks_of(db_session, item_id) -> list[tuple]:
    db_session.expire_all()
    checks = db_session.scalars(select(MenuItemCheck).where(MenuItemCheck.bar_menu_item_id == item_id))
    return [(c.status, [(r.reason, r.source_extracted_item_id) for r in c.reasons]) for c in checks]


def upload_again(
    client, db_session, bar, operator, mode="full_replace", filename="sample.jpg"
) -> tuple[MenuImport, list, list]:
    """Another upload to the bar; the mock extractor reads "sample" photos as the sample, others differently."""
    response = client.post(
        f"/api/bars/{bar.id}/menu-imports",
        headers={**operator, "Idempotency-Key": str(uuid4())},
        data={"mode": mode},
        files=[("images", (filename, JPEG, "image/jpeg"))],
    )
    assert response.status_code == 202, response.text
    db_session.expire_all()
    menu_import = db_session.get(MenuImport, response.json()["menuImportId"])
    return menu_import, load_items(db_session, menu_import), pending_changes(db_session, menu_import)


def accept_all(items, changes, decisions) -> dict:
    """A body deciding every line: `decisions` by line index, the rest rejected or confirmed as non-products."""
    body = {"reviewVersion": 1, "itemDecisions": [], "changeDecisions": []}
    for index, item in enumerate(items):
        base = {"extractedItemId": str(item.id)}
        if index in decisions:
            body["itemDecisions"].append({**base, "finalLineType": "product", "options": options_of(item), **decisions[index]})
        elif item.extracted_line_type.value != "product":
            body["itemDecisions"].append({**base, "action": "confirm_non_product", "finalLineType": item.extracted_line_type.value})
        else:
            body["itemDecisions"].append({**base, "action": "reject", "finalLineType": "product"})
    decided = {str(items[i].id) for i in decisions}
    body["changeDecisions"] = [
        {"changeId": str(c.id), "decision": "apply" if c.extracted_item_id is None or str(c.extracted_item_id) in decided else "ignore"}
        for c in changes
    ]
    return body


# ---- publishing without a product ----


def test_an_unlinked_whisky_is_published_and_checked(client, db_session, sample, operator, glenfiddich):
    unknown = sample.items[3]
    body = without_product(valid_body(sample, glenfiddich), 3)

    result = apply(client, sample.menu_import.id, body, operator)

    assert (result["result"]["added"], result["result"]["createdProducts"], result["result"]["unlinkedWhisky"]) == (1, 0, 1)
    assert menu_items(client, sample.bar) == [
        ("글렌피딕 12년", str(glenfiddich[12].id), "whisky", [9000, 17000]),
        ("Unknown Distillery 25", None, "whisky", [45000]),
    ]
    item = db_session.scalar(select(BarMenuItem).where(BarMenuItem.bar_id == sample.bar.id, BarMenuItem.product_id.is_(None)))
    assert item.name_key == "unknowndistillery25"
    assert checks_of(db_session, item.id) == [(CheckStatus.OPEN, [(CheckReason.UNLINKED, unknown.id)])]
    line = db_session.get(ExtractedItem, unknown.id)
    assert (line.selected_product_id, line.selected_match_method, line.corrected_kind, line.review_status) == (
        None,
        None,
        None,
        ReviewStatus.CONFIRMED,
    )
    # The same answer again for a repeated request (spec 8.8).
    assert apply(client, sample.menu_import.id, body, operator)["result"]["unlinkedWhisky"] == 1


def test_a_non_whisky_menu_opens_no_check(client, db_session, sample, operator, glenfiddich):
    body = without_product(valid_body(sample, glenfiddich), 3, kind="other", correctedProductName="하이볼")

    result = apply(client, sample.menu_import.id, body, operator)

    assert result["result"]["unlinkedWhisky"] == 0
    assert menu_items(client, sample.bar)[-1] == ("하이볼", None, "other", [45000])
    item = db_session.scalar(select(BarMenuItem).where(BarMenuItem.bar_id == sample.bar.id, BarMenuItem.product_id.is_(None)))
    assert checks_of(db_session, item.id) == []
    line = db_session.get(ExtractedItem, sample.items[3].id)
    assert (line.corrected_kind, line.corrected_product_name, line.review_status) == (
        MenuItemKind.OTHER,
        "하이볼",
        ReviewStatus.CORRECTED,
    )


def test_an_option_added_in_review_is_published(client, db_session, sample, operator, glenfiddich):
    body = without_product(valid_body(sample, glenfiddich), 3)
    body["itemDecisions"][3]["options"].append({"optionLabel": "병", "priceKrw": 900000})

    apply(client, sample.menu_import.id, body, operator)

    assert menu_items(client, sample.bar)[-1] == ("Unknown Distillery 25", None, "whisky", [45000, 900000])


# ---- a later upload of the same menu ----


@pytest.fixture
def published(client, db_session, sample, operator, glenfiddich):
    """The sample applied with Unknown Distillery 25 published without a product."""
    apply(client, sample.menu_import.id, without_product(valid_body(sample, glenfiddich), 3), operator)
    db_session.expire_all()
    return db_session.scalar(select(BarMenuItem).where(BarMenuItem.bar_id == sample.bar.id, BarMenuItem.product_id.is_(None)))


def test_the_same_menu_again_finds_the_unlinked_item_by_its_name_key(
    client, db_session, sample, operator, glenfiddich, published
):
    menu_import, items, changes = upload_again(client, db_session, sample.bar, operator)
    # Nothing changed on the photo, so the unlinked item needs no change. (The 12 is updated: its two lines
    # now make one change with both lines' options, spec 8.12.)
    assert published.id not in {c.bar_menu_item_id for c in changes}

    body = accept_all(
        items,
        changes,
        {
            1: {"action": "select_existing_product", "productId": str(glenfiddich[12].id)},
            3: {"action": "publish_without_product", "kind": "whisky"},
        },
    )
    apply(client, menu_import.id, body, operator)

    assert [name for name, *_ in menu_items(client, sample.bar)] == ["글렌피딕 12년", "Unknown Distillery 25"]
    # Still the same item, and its check gains the new line as another source.
    assert checks_of(db_session, published.id) == [
        (CheckStatus.OPEN, [(CheckReason.UNLINKED, sample.items[3].id), (CheckReason.UNLINKED, items[3].id)])
    ]


@pytest.mark.parametrize("mode", ["full_replace", "partial_update"])
def test_a_line_matched_to_a_new_product_links_the_unlinked_item(
    client, db_session, sample, operator, glenfiddich, published, mode
):
    """Once the catalog has the product, the same line is matched and links the item (spec 5.4)."""
    product = make_product(db_session, glenfiddich["brand"], "Unknown Distillery 25")
    db_session.commit()
    menu_import, items, changes = upload_again(client, db_session, sample.bar, operator, mode)
    takeover = [c for c in changes if c.bar_menu_item_id == published.id]
    assert [(c.change_type, c.extracted_item_id) for c in takeover] == [(MenuChangeType.UPDATE, items[3].id)]

    body = accept_all(
        items,
        changes,
        {
            1: {"action": "select_existing_product", "productId": str(glenfiddich[12].id)},
            3: {"action": "select_existing_product", "productId": str(product.id)},
        },
    )
    result = apply(client, menu_import.id, body, operator)

    assert result["result"]["unlinkedWhisky"] == 0
    assert [(name, product_id) for name, product_id, *_ in menu_items(client, sample.bar)] == [
        ("글렌피딕 12년", str(glenfiddich[12].id)),
        ("Unknown Distillery 25", str(product.id)),
    ]
    db_session.expire_all()
    linked = db_session.get(BarMenuItem, published.id)
    assert (linked.product_id, linked.name_key) == (product.id, None)
    # Linked by the review, so the unlinked check closes with its reason kept.
    assert checks_of(db_session, published.id) == [(CheckStatus.DISMISSED, [(CheckReason.UNLINKED, sample.items[3].id)])]
    found = client.get("/api/search/bars", params={"query": "Unknown Distillery 25"}).json()["items"]
    assert [i["barId"] for i in found] == [str(sample.bar.id)]


def test_a_takeover_uses_the_item_of_a_product_the_bar_sold_before(
    client, db_session, sample, operator, glenfiddich, published
):
    product = make_product(db_session, glenfiddich["brand"], "Unknown Distillery 25")
    sold_before = BarMenuItem(bar_id=sample.bar.id, product_id=product.id)
    db_session.add(sold_before)
    published.sold_out_at = db_session.scalar(select(ExtractedItem.reviewed_at).limit(1))
    db_session.commit()
    menu_import, items, changes = upload_again(client, db_session, sample.bar, operator)

    body = accept_all(
        items,
        changes,
        {
            1: {"action": "select_existing_product", "productId": str(glenfiddich[12].id)},
            3: {"action": "select_existing_product", "productId": str(product.id)},
        },
    )
    result = apply(client, menu_import.id, body, operator)

    # Linked, so not counted as waiting for an operator (spec 8.8).
    assert result["result"]["unlinkedWhisky"] == 0
    db_session.expire_all()
    menu = client.get(f"/api/bars/{sample.bar.id}/menu", headers=operator).json()["items"]
    assert [(i["barMenuItemId"], i["soldOut"]) for i in menu][-1] == (str(sold_before.id), True)
    # The unlinked item left the board and is not reused; its check closed.
    assert db_session.get(BarMenuItem, published.id).product_id is None
    assert checks_of(db_session, published.id)[0][0] == CheckStatus.DISMISSED


def test_removing_or_reclassifying_an_unlinked_item_closes_its_check(
    client, db_session, sample, operator, glenfiddich, published
):
    menu_import, items, changes = upload_again(client, db_session, sample.bar, operator)

    body = accept_all(
        items,
        changes,
        {
            1: {"action": "select_existing_product", "productId": str(glenfiddich[12].id)},
            3: {"action": "publish_without_product", "kind": "other"},
        },
    )
    apply(client, menu_import.id, body, operator)

    assert menu_items(client, sample.bar)[-1][2] == "other"
    assert checks_of(db_session, published.id)[0][0] == CheckStatus.DISMISSED


def test_an_applied_removal_closes_the_check(client, db_session, sample, operator, glenfiddich, published):
    # A different menu photo has no such line, so the full replace proposes removing the unlinked item.
    menu_import, items, changes = upload_again(client, db_session, sample.bar, operator, filename="other.jpg")
    removal = [c for c in changes if c.change_type == MenuChangeType.REMOVE and c.bar_menu_item_id == published.id]
    assert len(removal) == 1

    # Every line rejected; every removal applied.
    apply(client, menu_import.id, accept_all(items, changes, {}), operator)

    assert menu_items(client, sample.bar) == []
    assert checks_of(db_session, published.id)[0][0] == CheckStatus.DISMISSED


# ---- the review data (spec 5.4) ----


def test_the_review_shows_kinds_and_an_unlinked_item_before_the_change(
    client, db_session, sample, operator, glenfiddich, published
):
    # Another photo, so the full replace proposes removing the unlinked item: a change with only `before`.
    menu_import, items, _ = upload_again(client, db_session, sample.bar, operator, filename="other.jpg")

    review = client.get(f"/api/menu-imports/{menu_import.id}", headers=operator).json()

    lines = [line for image in review["images"] for line in image["items"]]
    assert {(line["effectiveLineType"], line["extractedKind"]) for line in lines} <= {
        ("product", "whisky"),
        ("section_header", None),
        ("description", None),
        ("unknown", None),
    }
    assert db_session.get(ExtractedItem, items[0].id).extracted_kind in (MenuItemKind.WHISKY, None)
    removal = next(c for c in review["proposedChanges"] if c["barMenuItemId"] == str(published.id))
    assert (removal["changeType"], removal["after"]) == ("remove", None)
    assert removal["before"] == {
        "productId": None,
        "kind": "whisky",
        "displayName": "Unknown Distillery 25",
        "options": [
            {"menuEntryOptionId": removal["before"]["options"][0]["menuEntryOptionId"], "optionLabel": "잔", "pourMl": None, "priceKrw": 45000}
        ],
    }
    assert all(c["after"]["kind"] == "whisky" for c in review["proposedChanges"] if c["after"])


def test_extracted_product_lines_are_stored_as_whisky(db_session, sample):
    db_session.expire_all()
    kinds = {(item.extracted_line_type.value, item.extracted_kind) for item in sample.items}

    assert kinds == {
        ("section_header", None),
        ("product", MenuItemKind.WHISKY),
        ("description", None),
    }


# ---- ignoring a change (spec 8.7) ----


def ignore(body, change):
    for decision in body["changeDecisions"]:
        if decision["changeId"] == str(change.id):
            decision["decision"] = "ignore"
    return body


def test_an_ignored_change_skips_the_line_only_while_it_is_still_the_target(
    client, db_session, sample, operator, glenfiddich
):
    """The 12 line's proposed update is ignored, but the reviewer decided the line is the 15: it is
    published as the 15. The 12 stays as it was."""
    body = ignore(valid_body(sample, glenfiddich), sample.changes[MenuChangeType.UPDATE])
    body["itemDecisions"][1]["productId"] = str(glenfiddich[15].id)
    body = without_product(body, 3)

    apply(client, sample.menu_import.id, body, operator)

    assert [(name, product, prices) for name, product, _, prices in menu_items(client, sample.bar)] == [
        ("글렌피딕 12년", str(glenfiddich[15].id), [9000, 17000]),
        ("Unknown Distillery 25", None, [45000]),
        ("글렌피딕 12년", str(glenfiddich[12].id), [8000, 17000]),
    ]


def test_an_ignored_change_still_skips_a_line_kept_as_proposed(client, db_session, sample, operator, glenfiddich):
    body = ignore(valid_body(sample, glenfiddich), sample.changes[MenuChangeType.UPDATE])
    body = ignore(without_product(body, 3), sample.changes[MenuChangeType.ADD])

    result = apply(client, sample.menu_import.id, body, operator)

    # The 12 keeps its old prices, and the unknown line, published without a product as proposed, is skipped.
    assert (result["result"]["added"], result["result"]["updated"], result["result"]["unlinkedWhisky"]) == (0, 0, 0)
    assert [(name, prices) for name, _, _, prices in menu_items(client, sample.bar)] == [("글렌피딕 12년", [8000, 17000])]


def test_a_corrected_spelling_of_an_unlinked_item_is_published(
    client, db_session, sample, operator, glenfiddich, published
):
    menu_import, items, changes = upload_again(client, db_session, sample.bar, operator)

    body = accept_all(
        items,
        changes,
        {
            1: {"action": "select_existing_product", "productId": str(glenfiddich[12].id)},
            # The same name key and options, a different spelling.
            3: {"action": "publish_without_product", "kind": "whisky", "correctedProductName": "UnknownDistillery 25"},
        },
    )
    result = apply(client, menu_import.id, body, operator)

    assert result["result"]["updated"] == 1
    assert menu_items(client, sample.bar)[-1][0] == "UnknownDistillery 25"
    db_session.expire_all()
    assert db_session.get(BarMenuItem, published.id).name_key == "unknowndistillery25"


@pytest.mark.parametrize("decided_as", ["as_proposed", "renamed", "product"])
def test_an_ignored_add_of_a_line_without_a_proposed_product_follows_its_target(
    client, db_session, sample, operator, glenfiddich, decided_as
):
    """The unknown line was proposed without a product, so its target is its name key (spec 8.7). Kept as
    proposed, the ignored add skips it; with another name key or a product, it follows the decision."""
    unknown = sample.items[3]
    decision = {
        "as_proposed": {"action": "publish_without_product", "kind": "whisky"},
        "renamed": {"action": "publish_without_product", "kind": "whisky", "correctedProductName": "Old Distillery 30"},
        "product": {"action": "select_existing_product", "productId": str(glenfiddich[15].id)},
    }[decided_as]
    body = ignore(valid_body(sample, glenfiddich), sample.changes[MenuChangeType.ADD])
    body["itemDecisions"][3] = {
        "extractedItemId": str(unknown.id),
        "finalLineType": "product",
        "options": options_of(unknown),
        **decision,
    }

    apply(client, sample.menu_import.id, body, operator)

    names = [(name, product) for name, product, *_ in menu_items(client, sample.bar)]
    assert names[0] == ("글렌피딕 12년", str(glenfiddich[12].id))
    assert names[1:] == {
        "as_proposed": [],
        "renamed": [("Old Distillery 30", None)],
        "product": [("Unknown Distillery 25", str(glenfiddich[15].id))],
    }[decided_as]


def test_an_ignored_add_of_a_proposed_product_skips_the_line_only_while_it_is_that_product(
    client, db_session, sample, operator, glenfiddich
):
    """A line proposed as a product not on the board makes an add with no board item to compare."""
    # The catalog gets Unknown Distillery 25 and the bar stops selling it.
    apply(client, sample.menu_import.id, valid_body(sample, glenfiddich), operator)
    menu = client.get(f"/api/bars/{sample.bar.id}/menu").json()
    unknown_item = next(i["barMenuItemId"] for i in menu["items"] if i["displayName"] == "Unknown Distillery 25")
    deleted = client.delete(
        f"/api/bars/{sample.bar.id}/menu/items/{unknown_item}",
        params={"menuVersion": menu["menuVersion"]},
        headers=operator,
    )
    assert deleted.status_code == 200, deleted.text
    menu_import, items, changes = upload_again(client, db_session, sample.bar, operator)
    [add] = [c for c in changes if c.change_type == MenuChangeType.ADD]
    assert (add.extracted_item_id, add.bar_menu_item_id) == (items[3].id, None)
    proposed = items[3].candidates[0].product_id

    def ignored_lines_when_line_is(product_id):
        body = accept_all(
            items,
            changes,
            {
                1: {"action": "select_existing_product", "productId": str(glenfiddich[12].id)},
                3: {"action": "select_existing_product", "productId": str(product_id)},
            },
        )
        ignore(body, add)
        request = ReviewAndApplyRequest.model_validate(body)
        return validate_review(db_session, menu_import, request, operator=True).ignored_lines

    assert ignored_lines_when_line_is(proposed) == {items[3].id}
    assert ignored_lines_when_line_is(glenfiddich[15].id) == set()
