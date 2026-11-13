"""A bar's approved owner managing it (API spec 2.2): the menu import and review flow end to end, and
the inactive bar's menu. The full allow/deny matrix is in test_route_permissions.py."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import BarOwner, BarStatus, ImportStatus, MenuBoard, Product, User, UserType
from tests.factories import make_bar, make_owner, make_user
from tests.review_support import JPEG, make_glenfiddich, upload_sample_review, valid_body

OWNER_SUBJECT = "owner-subject"


@pytest.fixture
def reviewer(db_session):
    return make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)


def owner_of(db_session, supabase, reviewer, bar, subject=OWNER_SUBJECT, *, revoked=False) -> dict:
    ownership = make_owner(db_session, make_user(db_session, subject), bar, reviewer)
    if revoked:
        ownership.revoked_at = datetime(2026, 10, 20, tzinfo=timezone.utc)
        ownership.revoked_by_user_id = reviewer.id
        db_session.flush()
    return {"Authorization": f"Bearer {supabase.token(sub=subject)}"}


def test_the_owner_uploads_reviews_and_publishes_the_menu(client, db_session, supabase, reviewer, image_storage):
    glenfiddich = make_glenfiddich(db_session)
    bar = make_bar(db_session, "Owner Bar")
    owner = owner_of(db_session, supabase, reviewer, bar)

    sample = upload_sample_review(client, db_session, owner, glenfiddich, bar=bar)
    status = client.get(f"/api/menu-imports/{sample.menu_import.id}", headers=owner)
    assert status.json()["status"] == "ready_for_review"
    brands = client.get("/api/catalog/brands", params={"query": "글렌피딕"}, headers=owner)
    assert [brand["canonicalName"] for brand in brands.json()["items"]] == ["Glenfiddich"]

    # Only an operator may create the new product the sample body creates (spec 2.2, 8.1).
    url = f"/api/menu-imports/{sample.menu_import.id}/review-and-apply"
    refused = client.post(url, headers=owner, json=valid_body(sample, glenfiddich))
    assert refused.status_code == 422, refused.text
    assert [(e["path"], e["code"]) for e in refused.json()["error"]["fieldErrors"]] == [
        ("itemDecisions[3].action", "OPERATOR_ONLY")
    ]
    body = valid_body(sample, glenfiddich)
    unknown = body["itemDecisions"][3]
    body["itemDecisions"][3] = {
        "action": "publish_without_product",
        "extractedItemId": unknown["extractedItemId"],
        "finalLineType": "product",
        "kind": "whisky",
        "options": unknown["options"],
    }

    response = client.post(url, headers=owner, json=body)

    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert sample.menu_import.status == ImportStatus.APPLIED
    board = db_session.get(MenuBoard, sample.board.id)
    assert board.last_import_id == sample.menu_import.id
    listed = client.get(f"/api/bars/{bar.id}/menu-imports", headers=owner).json()["items"]
    assert [item["status"] for item in listed] == ["applied"]
    # The owner's review grew no catalog: the new whisky is on the menu without a product.
    assert db_session.scalar(select(Product).where(Product.created_from_extracted_item_id == sample.items[3].id)) is None
    menu = client.get(f"/api/bars/{bar.id}/menu").json()["items"]
    assert [(i["displayName"], i["productId"], i["kind"]) for i in menu] == [
        ("글렌피딕 12년", str(glenfiddich[12].id), "whisky"),
        ("Unknown Distillery 25", None, "whisky"),
    ]


def test_the_owner_cancels_an_import_and_uploads_again(client, db_session, supabase, reviewer, image_storage):
    glenfiddich = make_glenfiddich(db_session)
    bar = make_bar(db_session, "Owner Bar")
    owner = owner_of(db_session, supabase, reviewer, bar)
    sample = upload_sample_review(client, db_session, owner, glenfiddich, bar=bar)

    canceled = client.post(f"/api/menu-imports/{sample.menu_import.id}/cancel", headers=owner)

    assert canceled.status_code == 200
    assert client.get(f"/api/bars/{bar.id}", headers=owner).json()["activeMenuImport"] is None
    again = client.post(
        f"/api/bars/{bar.id}/menu-imports",
        headers={**owner, "Idempotency-Key": "again"},
        data={"mode": "partial_update"},
        files=[("images", ("sample.jpg", JPEG, "image/jpeg"))],
    )
    assert again.status_code == 202, again.text


def test_a_revoked_owner_loses_access_on_the_next_request(client, db_session, supabase, reviewer):
    bar = make_bar(db_session, "Owner Bar")
    owner = owner_of(db_session, supabase, reviewer, bar)
    assert client.get(f"/api/bars/{bar.id}", headers=owner).status_code == 200

    bar_owner = db_session.scalar(select(BarOwner).where(BarOwner.bar_id == bar.id))
    bar_owner.revoked_at = datetime(2026, 10, 21, tzinfo=timezone.utc)
    bar_owner.revoked_by_user_id = reviewer.id
    db_session.flush()

    assert client.get(f"/api/bars/{bar.id}", headers=owner).status_code == 403


# ---- the public menu of an inactive bar ----


def test_the_owner_sees_the_menu_of_an_inactive_bar(client, db_session, supabase, reviewer):
    bar = make_bar(db_session, "Closed Bar", status=BarStatus.INACTIVE)
    owner = owner_of(db_session, supabase, reviewer, bar)

    response = client.get(f"/api/bars/{bar.id}/menu", headers=owner)

    assert response.status_code == 200
    assert response.json()["barId"] == str(bar.id)


@pytest.mark.parametrize("who", ["owner of another bar", "former owner"])
def test_other_callers_get_not_found_for_an_inactive_bar(client, db_session, supabase, reviewer, who):
    bar = make_bar(db_session, "Closed Bar", status=BarStatus.INACTIVE)
    if who == "former owner":
        headers = owner_of(db_session, supabase, reviewer, bar, revoked=True)
    else:
        headers = owner_of(db_session, supabase, reviewer, make_bar(db_session, "Open Bar"))

    response = client.get(f"/api/bars/{bar.id}/menu", headers=headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BAR_NOT_FOUND"
