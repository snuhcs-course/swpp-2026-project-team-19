"""An owner adding menu photos to a bar that already has a menu (API spec 4, 5.4, 8), end to end through the API
with the mock extractor, as the app and the owner web do it: a partial update, reviewed and published by the
owner. The new items are added after the menu; the items the photos do not show stay, with their sold-out marks
and discounts. test_owner_access_api.py covers the owner's first menu (full_replace)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models import MenuItemKind, UserType
from tests.factories import make_bar, make_owner, make_user, publish_menu
from tests.review_support import JPEG, make_glenfiddich


@pytest.fixture
def reviewer(db_session):
    return make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)


@pytest.fixture
def owned(db_session, supabase, reviewer):
    """A bar whose menu has Glenfiddich 12 (30ml and 60ml discounted), Glenfiddich 15 (discounted, to be sold out)
    and a highball without a product; and its owner's headers."""
    glenfiddich = make_glenfiddich(db_session)
    bar = make_bar(db_session, "Owner Bar")
    make_owner(db_session, make_user(db_session, "owner-subject"), bar, reviewer)
    started, ends = datetime.now(timezone.utc) - timedelta(days=1), datetime.now(timezone.utc) + timedelta(days=30)
    publish_menu(
        db_session,
        bar,
        [
            (
                glenfiddich[12],
                "글렌피딕 12년",
                [(None, 15, 8000), (None, 30, 17000, (16000, started, ends)), (None, 60, 30000, (27000, started, ends))],
            ),
            (glenfiddich[15], "글렌피딕 15년", [(None, 30, 21000, (19000, started, ends))]),
            (MenuItemKind.OTHER, "하우스 하이볼", [(None, None, 9000)]),
        ],
    )
    return bar, glenfiddich, {"Authorization": f"Bearer {supabase.token(sub='owner-subject')}"}


def upload(client, bar, owner, key):
    return client.post(
        f"/api/bars/{bar.id}/menu-imports",
        headers={**owner, "Idempotency-Key": key},
        data={"mode": "partial_update"},
        files=[("images", ("sample.jpg", JPEG, "image/jpeg"))],  # the mock extractor's sample menu
    )


def lines_of(review):
    return {
        line["extractedProductName"] or line["effectiveLineType"]: line
        for image in review["images"]
        for line in image["items"]
    }


def sent_options(line, default_pour=30):
    """The line's options as the clients send them (8.1): a glass without a pour takes the bar's default pour."""
    return [
        {
            "extractedOptionId": o["extractedOptionId"],
            "optionLabel": None,
            "pourMl": o["extractedPourMl"] or default_pour,
            "priceKrw": o["extractedPriceKrw"],
        }
        for o in line["options"]
    ]


def owner_body(review, glenfiddich, *, keep_unseen_servings):
    """What the app and the owner web send for the sample photo: Glenfiddich 12 at the photo's prices, the
    ambiguous line left out, Unknown Distillery 25 without a product (owners never create one), the header and
    description rejected. With `keep_unseen_servings`, the 60ml the photo does not show goes back as saved
    (OwnerReviewOptionContract.kt `ownerFinalReviewOptions`)."""
    lines = lines_of(review)
    exact, unknown = lines["글렌피딕 12년"], lines["Unknown Distillery 25"]
    gf12 = sent_options(exact)
    if keep_unseen_servings:
        gf12.append({"extractedOptionId": None, "optionLabel": None, "pourMl": 60, "priceKrw": 30000})
    published = {exact["extractedItemId"]: None, unknown["extractedItemId"]: None}
    decisions = []
    for image in review["images"]:
        for line in image["items"]:
            if line is exact:
                decisions.append(
                    {
                        "action": "select_existing_product",
                        "extractedItemId": line["extractedItemId"],
                        "finalLineType": "product",
                        "productId": str(glenfiddich[12].id),
                        "options": gf12,
                    }
                )
            elif line is unknown:
                decisions.append(
                    {
                        "action": "publish_without_product",
                        "extractedItemId": line["extractedItemId"],
                        "finalLineType": "product",
                        "kind": "whisky",
                        "correctedProductName": "Unknown Distillery 25",
                        "options": sent_options(line),
                    }
                )
            else:
                decisions.append(
                    {"action": "reject", "extractedItemId": line["extractedItemId"], "finalLineType": line["effectiveLineType"]}
                )
    # A change applies when one of its lines is published; a removal never does (photoImportChangeDecision).
    applies = lambda c: c["changeType"] != "remove" and any(i in published for i in c["extractedItemIds"])  # noqa: E731
    changes = [{"changeId": c["changeId"], "decision": "apply" if applies(c) else "ignore"} for c in review["proposedChanges"]]
    return {"reviewVersion": review["reviewVersion"], "itemDecisions": decisions, "changeDecisions": changes}


def menu_rows(menu):
    return [
        (
            item["displayName"],
            item["soldOut"],
            [(o["pourMl"], o["priceKrw"], o["discount"]["discountedPriceKrw"] if o["discount"] else None) for o in item["options"]],
        )
        for item in menu["items"]
    ]


def test_an_owners_partial_update_adds_new_items_and_keeps_the_rest_with_discounts_and_sold_out(client, owned):
    bar, glenfiddich, owner = owned
    menu = client.get(f"/api/bars/{bar.id}/menu", headers=owner).json()
    gf15 = next(item for item in menu["items"] if item["displayName"] == "글렌피딕 15년")
    sold_out_url = f"/api/bars/{bar.id}/menu/items/{gf15['barMenuItemId']}/sold-out"
    sold = client.put(sold_out_url, headers=owner, json={"soldOut": True})
    assert sold.status_code == 200, sold.text

    key = str(uuid4())
    accepted = upload(client, bar, owner, key)
    assert accepted.status_code == 202, accepted.text
    # A lost answer sent again with the same key and photo is the same import (4.3), not a second one.
    again = upload(client, bar, owner, key)
    assert (again.status_code, again.json()["menuImportId"]) == (202, accepted.json()["menuImportId"])
    import_id = accepted.json()["menuImportId"]
    active = client.get(f"/api/bars/{bar.id}", headers=owner).json()["activeMenuImport"]
    assert active == {"menuImportId": import_id, "status": "ready_for_review"}

    review = client.get(accepted.json()["statusUrl"], headers=owner).json()
    assert (review["status"], review["mode"]) == ("ready_for_review", "partial_update")
    # A partial update never proposes removing what the photos do not show (matching flow 13).
    assert "remove" not in {change["changeType"] for change in review["proposedChanges"]}

    body = owner_body(review, glenfiddich, keep_unseen_servings=True)
    applied = client.post(f"/api/menu-imports/{import_id}/review-and-apply", headers=owner, json=body)
    assert applied.status_code == 200, applied.text
    result = applied.json()["result"]
    assert (result["added"], result["removed"], result["unlinkedWhisky"]) == (1, 0, 1)

    after = client.get(f"/api/bars/{bar.id}/menu", headers=owner).json()
    assert after["menuVersion"] == menu["menuVersion"] + 1
    assert menu_rows(after) == [
        # The photo's new 15ml price drops nothing else: the unchanged 30ml and the 60ml sent back keep discounts.
        ("글렌피딕 12년", False, [(15, 9000, None), (30, 17000, 16000), (60, 30000, 27000)]),
        ("글렌피딕 15년", True, [(30, 21000, 19000)]),
        ("하우스 하이볼", False, [(None, 9000, None)]),
        ("Unknown Distillery 25", False, [(30, 45000, None)]),
    ]
    # Customers see the same menu without the sold-out item (3.9).
    public = client.get(f"/api/bars/{bar.id}/menu").json()["items"]
    assert [item["displayName"] for item in public] == ["글렌피딕 12년", "하우스 하이볼", "Unknown Distillery 25"]
    assert client.get(f"/api/bars/{bar.id}", headers=owner).json()["activeMenuImport"] is None
    assert client.get(f"/api/menu-imports/{import_id}", headers=owner).json()["status"] == "applied"


def test_a_partial_update_replaces_every_option_of_an_item_it_updates(client, owned):
    """Why the clients send the servings the photos do not show: an updated item takes exactly the options sent."""
    bar, glenfiddich, owner = owned
    accepted = upload(client, bar, owner, str(uuid4()))
    review = client.get(accepted.json()["statusUrl"], headers=owner).json()

    body = owner_body(review, glenfiddich, keep_unseen_servings=False)
    applied = client.post(f"/api/menu-imports/{accepted.json()['menuImportId']}/review-and-apply", headers=owner, json=body)

    assert applied.status_code == 200, applied.text
    rows = menu_rows(client.get(f"/api/bars/{bar.id}/menu", headers=owner).json())
    assert rows[0] == ("글렌피딕 12년", False, [(15, 9000, None), (30, 17000, 16000)])
    assert [row[0] for row in rows[1:]] == ["글렌피딕 15년", "하우스 하이볼", "Unknown Distillery 25"]
