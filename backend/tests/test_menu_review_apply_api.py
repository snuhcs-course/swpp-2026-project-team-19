from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core.errors import ApiError
from app.core.security import Principal
from app.models import (
    BarMenuItem,
    BarStatus,
    Brand,
    ExtractedItem,
    ImportStatus,
    MatchMethod,
    MenuBoard,
    MenuChangeDecision,
    MenuChangeType,
    MenuEntryOption,
    MenuImport,
    MenuImportChange,
    Product,
    ReviewStatus,
    UserType,
)
from app.schemas.menu_review import ReviewAndApplyRequest
from app.services import menu_review_apply, serializable
from app.services.menu_review_apply import review_and_apply
from tests.factories import make_bar, make_owner, make_user
from tests.sql_support import recorded_statements
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


def submit(client, menu_import_id, body, headers):
    return client.post(f"/api/menu-imports/{menu_import_id}/review-and-apply", json=body, headers=headers)


def applied(client, sample, body, operator):
    response = submit(client, sample.menu_import.id, body, operator)
    assert response.status_code == 200, response.text
    return response.json()


def set_decision(body, change, decision):
    for entry in body["changeDecisions"]:
        if entry["changeId"] == str(change.id):
            entry["decision"] = decision


def stored_changes(db_session, menu_import):
    db_session.expire_all()
    rows = db_session.scalars(select(MenuImportChange).where(MenuImportChange.menu_import_id == menu_import.id))
    return sorted((r.change_type, r.decision, r.extracted_item_id, r.bar_menu_item_id) for r in rows)


def body_from_review(review):
    """What a client would submit when accepting every proposal of the review screen."""
    decisions = []
    for image in review["images"]:
        for item in image["items"]:
            base = {"extractedItemId": item["extractedItemId"], "finalLineType": item["effectiveLineType"]}
            options = [
                {
                    "extractedOptionId": o["extractedOptionId"],
                    "optionLabel": o["extractedOptionLabel"],
                    "pourMl": o["extractedPourMl"],
                    "priceKrw": o["extractedPriceKrw"],
                }
                for o in item["options"]
            ]
            if item["effectiveLineType"] != "product":
                decisions.append({**base, "action": "confirm_non_product"})
            elif item["proposedProductId"]:
                decisions.append(
                    {**base, "action": "select_existing_product", "productId": item["proposedProductId"], "options": options}
                )
            else:
                draft = item["newProductDraft"]
                decisions.append(
                    {
                        **base,
                        "options": options,
                        "action": "create_product",
                        "brand": {"type": "new", "canonicalName": draft["brandText"] or draft["displayName"]},
                        "product": {
                            "category": draft["category"],
                            "displayName": draft["displayName"],
                            "ageYears": draft["ageYears"],
                            "editionName": draft["editionName"],
                            "abv": draft["abv"],
                        },
                    }
                )
    return {
        "reviewVersion": review["reviewVersion"],
        "itemDecisions": decisions,
        "changeDecisions": [{"changeId": c["changeId"], "decision": "apply"} for c in review["proposedChanges"]],
    }


def customer_search(client, query):
    return client.get("/api/search/bars", params={"query": query}).json()


def prices_found(client, query):
    return [[o["priceKrw"] for o in i["options"]] for i in customer_search(client, query)["items"]]


def test_review_to_customer_search(client, db_session, sample, operator, glenfiddich):
    review = client.get(f"/api/menu-imports/{sample.menu_import.id}", headers=operator).json()
    # Waiting for review changes nothing customers see (API spec, section 3.10.2).
    assert prices_found(client, "글렌피딕 12년") == [[8000, 17000]]
    assert prices_found(client, "글렌피딕 15년") == [[21000]]
    assert customer_search(client, "Unknown Distillery 25")["matchType"] == "none"

    body = applied(client, sample, body_from_review(review), operator)

    assert body["status"] == "applied"
    assert body["reviewVersion"] == 1
    assert body["menuBoardId"] == str(sample.board.id)
    assert body["result"] == {
        "added": 1,
        "updated": 1,
        "removed": 1,
        "ignored": 0,
        "createdBrands": 1,
        "createdProducts": 1,
        "unlinkedWhisky": 0,
    }
    status = client.get(f"/api/menu-imports/{sample.menu_import.id}", headers=operator).json()
    assert (status["status"], status["appliedAt"], status["menuBoardId"]) == (
        "applied",
        body["appliedAt"],
        str(sample.board.id),
    )
    menu = client.get(f"/api/bars/{sample.bar.id}/menu").json()
    assert [(i["displayName"], [o["priceKrw"] for o in i["options"]]) for i in menu["items"]] == [
        ("글렌피딕 12년", [9000, 17000]),
        ("Unknown Distillery 25", [45000]),
    ]
    search = client.get("/api/search/bars", params={"query": "Unknown Distillery 25"}).json()
    assert [(i["barId"], i["menuDisplayName"]) for i in search["items"]] == [
        (str(sample.bar.id), "Unknown Distillery 25")
    ]
    # Once applied: the new price shows, and the removed 15 is recognized but sold nowhere.
    assert prices_found(client, "글렌피딕 12년") == [[9000, 17000]]
    removed = customer_search(client, "글렌피딕 15년")
    assert ([p["resultCount"] for p in removed["matchedProducts"]], removed["items"]) == ([0], [])
    # The bar accepts the next upload.
    response = client.post(
        f"/api/bars/{sample.bar.id}/menu-imports",
        headers={**operator, "Idempotency-Key": str(uuid4())},
        data={"mode": "partial_update"},
        files=[("images", ("sample.jpg", JPEG, "image/jpeg"))],
    )
    assert response.status_code == 202


def test_decisions_are_recorded_on_items_and_options(client, db_session, sample, operator, glenfiddich):
    header, exact, conflict, unknown, description = sample.items
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][1]["options"][0]["priceKrw"] = 9500
    body["itemDecisions"][4]["finalLineType"] = "unknown"

    result = applied(client, sample, body, operator)

    db_session.expire_all()
    rows = {item.id: item for item in db_session.scalars(select(ExtractedItem).where(ExtractedItem.id.in_([i.id for i in sample.items])))}
    assert (rows[header.id].review_status, rows[header.id].corrected_line_type) == (ReviewStatus.CONFIRMED, None)
    assert (rows[description.id].review_status, rows[description.id].corrected_line_type.value) == (
        ReviewStatus.CORRECTED,
        "unknown",
    )
    assert (rows[conflict.id].review_status, rows[conflict.id].selected_product_id) == (ReviewStatus.REJECTED, None)
    kept = rows[exact.id]
    assert (kept.selected_product_id, kept.selected_match_method, kept.match_confidence) == (
        glenfiddich[12].id,
        MatchMethod.ALIAS,
        Decimal("1.0000"),
    )
    # Only the price differed from the extraction; the same pour is not stored as a correction.
    assert [(o.corrected_price_krw, o.corrected_pour_ml) for o in kept.options] == [(9500, None), (None, None)]
    assert kept.review_status == ReviewStatus.CORRECTED
    created = rows[unknown.id]
    assert (created.selected_match_method, created.match_confidence, created.review_status) == (
        MatchMethod.MANUAL,
        None,
        ReviewStatus.CORRECTED,
    )
    assert result["result"]["createdProducts"] == 1
    # initial_resolution_status is never changed by review.
    assert kept.initial_resolution_status.value == "exact_match"


def test_choosing_another_candidate_is_manual_with_its_score(client, db_session, sample, operator, glenfiddich):
    """The 12 line proposes Glenfiddich 12; choosing 15 from search instead is manual."""
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][1]["productId"] = str(glenfiddich[15].id)

    applied(client, sample, body, operator)

    db_session.expire_all()
    exact = db_session.get(ExtractedItem, sample.items[1].id)
    assert (exact.selected_product_id, exact.selected_match_method, exact.review_status) == (
        glenfiddich[15].id,
        MatchMethod.MANUAL,
        ReviewStatus.CORRECTED,
    )


def test_changes_left_are_the_applied_and_ignored_ones(client, db_session, sample, operator, glenfiddich):
    """Picking Glenfiddich 15 for the 12 line turns the draft's update of 12 into an update of
    15; the approved removal of 15 changes nothing, so its row goes; 12 stays on the board."""
    _, exact, _, unknown, _ = sample.items
    entry_12, entry_15 = sample.board.entries
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"][1]["productId"] = str(glenfiddich[15].id)
    set_decision(body, sample.changes[MenuChangeType.ADD], "ignore")

    result = applied(client, sample, body, operator)

    assert stored_changes(db_session, sample.menu_import) == sorted(
        [
            (MenuChangeType.ADD, MenuChangeDecision.IGNORE, unknown.id, None),
            (MenuChangeType.UPDATE, MenuChangeDecision.APPLY, exact.id, entry_15.bar_menu_item_id),
        ]
    )
    assert result["result"] == {
        "added": 0,
        "updated": 1,
        "removed": 0,
        "ignored": 1,
        "createdBrands": 1,
        "createdProducts": 1,
        "unlinkedWhisky": 0,
    }
    menu = client.get(f"/api/bars/{sample.bar.id}/menu").json()
    assert [i["productId"] for i in menu["items"]] == [str(glenfiddich[15].id), str(glenfiddich[12].id)]


def test_a_repeated_request_returns_the_stored_result(client, db_session, sample, operator, glenfiddich):
    body = valid_body(sample, glenfiddich)
    first = applied(client, sample, body, operator)

    again = applied(client, sample, body, operator)

    assert again == first
    assert db_session.scalar(select(func.count()).select_from(Brand).where(Brand.canonical_name == "Unknown Distillery")) == 1


def test_an_old_review_version_is_outdated(client, sample, operator, glenfiddich):
    body = valid_body(sample, glenfiddich)
    body["reviewVersion"] = 2

    response = submit(client, sample.menu_import.id, body, operator)

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "REVIEW_OUTDATED",
        "message": "검수 데이터가 변경되었습니다. 최신 내용을 다시 확인해 주세요.",
        "details": {
            "menuImportId": str(sample.menu_import.id),
            "submittedReviewVersion": 2,
            "currentReviewVersion": 1,
            "reviewUrl": f"/api/menu-imports/{sample.menu_import.id}",
        },
        "fieldErrors": [],
    }


def test_a_board_change_rebuilds_the_draft(client, db_session, sample, operator, glenfiddich):
    # The board now has the menu's price for 12, so the proposed update is stale.
    entry_12 = sample.board.entries[0]
    db_session.execute(
        MenuEntryOption.__table__.update()
        .where(MenuEntryOption.menu_board_entry_id == entry_12.id, MenuEntryOption.pour_ml == 15)
        .values(price_krw=9000)
    )
    db_session.commit()

    response = submit(client, sample.menu_import.id, valid_body(sample, glenfiddich), operator)

    assert response.status_code == 409
    assert response.json()["error"]["details"]["currentReviewVersion"] == 2
    review = client.get(f"/api/menu-imports/{sample.menu_import.id}", headers=operator).json()
    assert review["reviewVersion"] == 2
    assert sorted(c["changeType"] for c in review["proposedChanges"]) == ["add", "remove"]
    # Submitting against the new version works.
    body = valid_body(sample, glenfiddich)
    body["reviewVersion"] = 2
    body["changeDecisions"] = [{"changeId": c["changeId"], "decision": "apply"} for c in review["proposedChanges"]]
    assert applied(client, sample, body, operator)["result"]["updated"] == 0


def test_errors_roll_back_everything(client, db_session, sample, operator, glenfiddich):
    body = valid_body(sample, glenfiddich)
    # The new brand would be created first, then the product conflicts with Glenfiddich 12.
    body["itemDecisions"][2] = {
        **body["itemDecisions"][3],
        "extractedItemId": body["itemDecisions"][2]["extractedItemId"],
        "options": options_of(sample.items[2]),
        "brand": {"type": "existing", "brandId": str(glenfiddich["brand"].id)},
        "product": {"displayName": "Glenfiddich Twelve", "ageYears": 12},
    }

    response = submit(client, sample.menu_import.id, body, operator)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_PRODUCT_FOUND"
    db_session.expire_all()
    assert db_session.get(MenuImport, sample.menu_import.id).status == ImportStatus.READY_FOR_REVIEW
    assert db_session.scalar(select(func.count()).select_from(Brand).where(Brand.canonical_name == "Unknown Distillery")) == 0


def test_validation_errors_are_422(client, sample, operator, glenfiddich):
    body = valid_body(sample, glenfiddich)
    body["itemDecisions"].pop()

    response = submit(client, sample.menu_import.id, body, operator)

    assert response.status_code == 422
    assert response.json()["error"]["fieldErrors"][0]["code"] == "MISSING_ITEM"


def test_only_ready_imports_can_be_submitted(client, db_session, image_storage, operator, glenfiddich):
    bar = make_bar(db_session)
    response = client.post(
        f"/api/bars/{bar.id}/menu-imports",
        headers={**operator, "Idempotency-Key": str(uuid4())},
        data={"mode": "full_replace"},
        files=[("images", ("fail.jpg", JPEG, "image/jpeg"))],
    )
    import_id = response.json()["menuImportId"]

    response = submit(client, import_id, {"reviewVersion": 1, "itemDecisions": [], "changeDecisions": []}, operator)

    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"menuImportId": import_id, "status": "failed"}


@pytest.mark.parametrize("import_id", [str(uuid4()), "not-a-uuid"])
def test_unknown_import(client, operator, import_id):
    response = submit(client, import_id, {"reviewVersion": 1, "itemDecisions": [], "changeDecisions": []}, operator)

    assert (response.status_code, response.json()["error"]["code"]) == (404, "MENU_IMPORT_NOT_FOUND")


class _SerializationFailure(Exception):
    sqlstate = "40001"


def conflict_error():
    return OperationalError("UPDATE ...", {}, _SerializationFailure())


def test_a_publish_raises_the_menu_version_and_stamps_one_time(client, db_session, sample, operator, glenfiddich):
    body = applied(client, sample, valid_body(sample, glenfiddich), operator)

    menu = client.get(f"/api/bars/{sample.bar.id}/menu").json()
    assert menu["menuVersion"] == 2
    assert menu["publishedAt"] == body["appliedAt"]
    db_session.expire_all()
    assert sample.menu_import.completed_at == sample.menu_import.review_confirmed_at


def discounted(option):
    return option["discount"]["discountedPriceKrw"] if option["discount"] else None


def test_a_publish_keeps_a_discount_only_where_the_option_is_unchanged(
    client, db_session, sample, operator, glenfiddich
):
    now = datetime.now(timezone.utc)
    starts, ends = now - timedelta(days=1), now + timedelta(days=14)
    for option in db_session.scalars(select(MenuEntryOption)):
        option.discount_price_krw = option.price_krw - 1000
        option.discount_starts_at, option.discount_ends_at = starts, ends
    db_session.flush()

    applied(client, sample, valid_body(sample, glenfiddich), operator)

    menu = client.get(f"/api/bars/{sample.bar.id}/menu").json()
    # The 12's 15 ml went from 8000 to 9000, so its discount is dropped; its 30 ml kept 17000.
    assert [
        (i["displayName"], [(o["pourMl"], o["priceKrw"], discounted(o)) for o in i["options"]])
        for i in menu["items"]
    ] == [
        ("글렌피딕 12년", [(15, 9000, None), (30, 17000, 16000)]),
        ("Unknown Distillery 25", [(None, 45000, None)]),
    ]


def test_a_publish_keeps_sold_out_on_kept_items_and_clears_it_on_removed_ones(
    client, db_session, sample, operator, glenfiddich
):
    for item in db_session.scalars(select(BarMenuItem).where(BarMenuItem.bar_id == sample.bar.id)):
        item.sold_out_at = datetime.now(timezone.utc)
    db_session.flush()

    applied(client, sample, valid_body(sample, glenfiddich), operator)

    db_session.expire_all()
    sold_out = {
        item.product_id: item.sold_out_at is not None
        for item in db_session.scalars(select(BarMenuItem).where(BarMenuItem.bar_id == sample.bar.id))
    }
    # The 12 stays on the board with new prices and stays sold out; the 15 was removed.
    assert (sold_out[glenfiddich[12].id], sold_out[glenfiddich[15].id]) == (True, False)
    # The Unknown Distillery 25 the review added starts on sale.
    assert sum(sold_out.values()) == 1


def test_the_bar_row_is_locked_before_the_import(client, db_session, sample, operator, glenfiddich):
    with recorded_statements(db_session) as statements:
        applied(client, sample, valid_body(sample, glenfiddich), operator)

    locks = [i for i, sql in enumerate(statements) if "FOR UPDATE" in sql]
    assert ["FROM bars" in statements[i] for i in locks[:2]] == [True, False]
    assert "FROM menu_imports" in statements[locks[1]]
    stamp = next(i for i, sql in enumerate(statements) if "clock_timestamp()" in sql)
    assert locks[0] < stamp < locks[1]


def test_an_owner_revoked_before_the_lock_is_forbidden(db_session, sample, glenfiddich):
    """The route let the owner in; the transaction checks again once the bar row is locked."""
    reviewer = make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)
    ownership = make_owner(db_session, make_user(db_session, "owner-subject"), sample.bar, reviewer)
    ownership.revoked_at, ownership.revoked_by_user_id = datetime.now(timezone.utc), reviewer.id
    db_session.flush()
    owner = Principal(kind="supabase", subject="owner-subject", claims={})
    request = ReviewAndApplyRequest.model_validate(valid_body(sample, glenfiddich))

    with pytest.raises(ApiError) as caught:
        review_and_apply(lambda: nullcontext(db_session), sample.menu_import.id, request, owner)

    assert (caught.value.status_code, caught.value.code) == (403, "FORBIDDEN")
    db_session.expire_all()
    assert sample.menu_import.status == ImportStatus.READY_FOR_REVIEW
    assert db_session.get(MenuBoard, sample.board.id).version == 1


def test_an_inactive_bar_takes_no_review_publish(client, db_session, sample, operator, glenfiddich):
    sample.bar.status = BarStatus.INACTIVE
    # Committed so the failed request's rollback keeps it.
    db_session.commit()

    response = submit(client, sample.menu_import.id, valid_body(sample, glenfiddich), operator)

    assert (response.status_code, response.json()["error"]["code"]) == (404, "BAR_NOT_FOUND")
    assert response.json()["error"]["details"] == {"barId": str(sample.bar.id)}
    db_session.expire_all()
    assert sample.menu_import.status == ImportStatus.READY_FOR_REVIEW
    assert db_session.get(MenuBoard, sample.board.id).version == 1


def test_a_temporary_operator_without_a_users_row_creates_catalog_rows_without_a_creator(
    client, db_session, sample, operator, glenfiddich
):
    applied(client, sample, valid_body(sample, glenfiddich), operator)

    created = db_session.scalar(select(Product).where(Product.created_from_extracted_item_id == sample.items[3].id))
    assert (created.created_by_user_id, created.brand.created_by_user_id) == (None, None)


def test_serialization_failures_are_retried(client, sample, operator, glenfiddich, monkeypatch):
    real = menu_review_apply._apply_once
    calls = []

    def flaky(session, menu_import_id, request, principal):
        calls.append(1)
        if len(calls) == 1:
            raise conflict_error()
        return real(session, menu_import_id, request, principal)

    monkeypatch.setattr(menu_review_apply, "_apply_once", flaky)
    monkeypatch.setattr(serializable, "sleep", lambda seconds: None)

    applied(client, sample, valid_body(sample, glenfiddich), operator)

    assert len(calls) == 2


def test_repeated_conflicts_are_503(client, sample, operator, glenfiddich, monkeypatch):
    calls = []

    def always(session, menu_import_id, request, principal):
        calls.append(1)
        raise conflict_error()

    monkeypatch.setattr(menu_review_apply, "_apply_once", always)
    monkeypatch.setattr(serializable, "sleep", lambda seconds: None)

    response = submit(client, sample.menu_import.id, valid_body(sample, glenfiddich), operator)

    assert (response.status_code, response.json()["error"]["code"]) == (503, "TEMPORARY_WRITE_CONFLICT")
    assert len(calls) == 3


def test_operators_only(client, sample, token_for, glenfiddich):
    body = valid_body(sample, glenfiddich)
    customer = {"Authorization": f"Bearer {token_for('customer')}"}

    assert submit(client, sample.menu_import.id, body, customer).status_code == 403
    assert submit(client, sample.menu_import.id, body, {}).status_code == 401
