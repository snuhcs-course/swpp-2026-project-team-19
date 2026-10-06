from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models import (
    Bar,
    ExtractionApproach,
    ExtractionRun,
    ImportMode,
    ImportStatus,
    MenuImage,
    MenuImport,
    PipelineStatus,
)
from tests.factories import make_bar, make_brand, make_product, publish_menu

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    brand = make_brand(db_session, "Glenfiddich", aliases=("글렌피딕",))
    return {
        12: make_product(db_session, brand, "Glenfiddich 12", aliases=("글렌피딕 12년",), age_years=12),
        15: make_product(db_session, brand, "Glenfiddich 15", aliases=("글렌피딕 15년",), age_years=15),
    }


def upload(client, bar, headers, filenames=("sample.jpg",), mode="full_replace"):
    response = client.post(
        f"/api/bars/{bar.id}/menu-imports",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        data={"mode": mode},
        files=[("images", (name, JPEG, "image/jpeg")) for name in filenames],
    )
    assert response.status_code == 202, response.text
    return response.json()["menuImportId"]


def get_import(client, import_id, headers):
    response = client.get(f"/api/menu-imports/{import_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def make_import(db_session, status, run_statuses):
    """An import in a given state without running the pipeline."""
    bar = make_bar(db_session)
    menu_import = MenuImport(
        idempotency_key=str(uuid4()), request_fingerprint="f", bar_id=bar.id, mode=ImportMode.FULL_REPLACE, status=status
    )
    db_session.add(menu_import)
    db_session.flush()
    for order, run_status in enumerate(run_statuses, start=1):
        image = MenuImage(menu_import_id=menu_import.id, storage_key=f"menus/x/page-{order}.jpg", image_order=order)
        db_session.add(image)
        db_session.flush()
        db_session.add(
            ExtractionRun(
                menu_image_id=image.id,
                approach=ExtractionApproach.VISION_LLM,
                provider="mock",
                model_name="mock",
                pipeline_version="v",
                status=run_status,
            )
        )
    db_session.flush()
    return menu_import


@pytest.mark.parametrize("status", [ImportStatus.UPLOADED, ImportStatus.PROCESSING])
def test_processing_reports_progress(client, db_session, operator, status):
    menu_import = make_import(db_session, status, [PipelineStatus.SUCCEEDED, PipelineStatus.RUNNING, PipelineStatus.QUEUED])

    body = get_import(client, menu_import.id, operator)

    assert body == {
        "menuImportId": str(menu_import.id),
        "status": status.value,
        "progress": {"totalImages": 3, "completedImages": 1, "failedImages": 0},
        "pollAfterMs": 3000,
    }


def test_failed_extraction_is_reported(client, db_session, image_storage, operator):
    import_id = upload(client, make_bar(db_session), operator, filenames=("sample.jpg", "fail.jpg"))

    body = get_import(client, import_id, operator)

    assert body["status"] == "failed"
    assert body["progress"] == {"totalImages": 2, "completedImages": 1, "failedImages": 1}
    assert body["failure"]["code"] == "IMAGE_EXTRACTION_FAILED"
    assert "pollAfterMs" not in body


def test_failure_without_a_failed_image_is_a_processing_failure(client, db_session, operator):
    menu_import = make_import(db_session, ImportStatus.FAILED, [PipelineStatus.SUCCEEDED])

    assert get_import(client, menu_import.id, operator)["failure"]["code"] == "PROCESSING_FAILED"


def test_review_payload(client, db_session, image_storage, operator, glenfiddich):
    bar = make_bar(db_session)
    board = publish_menu(
        db_session,
        bar,
        [
            (glenfiddich[12], "글렌피딕 12년", [(None, 15, 8000), (None, 30, 17000)]),
            (glenfiddich[15], "글렌피딕 15년", [("잔", None, 21000)]),
        ],
    )
    twelve_entry, fifteen_entry = board.entries
    import_id = upload(client, bar, operator)

    body = get_import(client, import_id, operator)

    assert (body["status"], body["mode"], body["reviewVersion"], body["barId"]) == (
        "ready_for_review",
        "full_replace",
        1,
        str(bar.id),
    )
    [image] = body["images"]
    assert image["imageOrder"] == 1
    assert image["imageUrl"].startswith(f"http://testserver/media/menus/{bar.id}/{import_id}/page-1.jpg")
    assert image["imageUrlExpiresAt"] is None
    assert client.get(image["imageUrl"]).content == JPEG

    header, exact, conflict, unknown, description = image["items"]
    assert [i["itemOrder"] for i in image["items"]] == [1, 2, 3, 4, 5]
    assert header == {
        **header,
        "extractedLineType": "section_header",
        "correctedLineType": None,
        "effectiveLineType": "section_header",
        "initialResolutionStatus": None,
        "proposedProductId": None,
        "options": [],
        "candidates": [],
        "newProductDraft": None,
    }
    assert exact["initialResolutionStatus"] == "exact_match"
    assert exact["proposedProductId"] == str(glenfiddich[12].id)
    assert (exact["extractedAgeYears"], exact["extractionConfidence"]) == (12, 0.93)
    assert [(o["optionOrder"], o["extractedPourMl"], o["extractedPriceKrw"]) for o in exact["options"]] == [
        (1, 15, 9000),
        (2, 30, 17000),
    ]
    [candidate] = exact["candidates"]
    assert {k: candidate[k] for k in ("productId", "candidateRank", "displayName", "brandName", "category", "matchMethod", "score")} == {
        "productId": str(glenfiddich[12].id),
        "candidateRank": 1,
        "displayName": "Glenfiddich 12",
        "brandName": "Glenfiddich",
        "category": "whisky",
        "matchMethod": "alias",
        "score": 1.0,
    }
    assert candidate["evidence"]["aliasExact"] is True
    assert exact["newProductDraft"] == {
        "brandText": "글렌피딕",
        "category": "whisky",
        "displayName": "글렌피딕 12년",
        "ageYears": 12,
        "editionName": None,
        "abv": None,
    }
    assert (conflict["initialResolutionStatus"], conflict["proposedProductId"]) == ("ambiguous", str(glenfiddich[12].id))
    assert conflict["candidates"][0]["evidence"]["ageConflict"] is True
    assert (unknown["initialResolutionStatus"], unknown["proposedProductId"], unknown["candidates"]) == ("unmatched", None, [])
    assert unknown["newProductDraft"]["abv"] == 48.0
    assert description["effectiveLineType"] == "description"

    update, add, remove = body["proposedChanges"]
    assert (update["changeType"], update["extractedItemId"], update["barMenuItemId"]) == (
        "update",
        exact["extractedItemId"],
        str(twelve_entry.bar_menu_item_id),
    )
    assert update["before"]["displayName"] == update["after"]["displayName"] == "Glenfiddich 12"
    assert [(o["pourMl"], o["priceKrw"]) for o in update["before"]["options"]] == [(15, 8000), (30, 17000)]
    assert [(o["pourMl"], o["priceKrw"]) for o in update["after"]["options"]] == [(15, 9000), (30, 17000)]
    assert update["after"]["options"][0]["extractedOptionId"] == exact["options"][0]["extractedOptionId"]
    assert update["summary"] == "Glenfiddich 12 가격·용량 변경"

    assert (add["changeType"], add["before"], add["barMenuItemId"]) == ("add", None, None)
    assert add["after"]["productId"] is None
    assert add["after"]["displayName"] == "Unknown Distillery 25"
    assert add["summary"] == "Unknown Distillery 25 추가 (가격 옵션 1개)"

    assert (remove["changeType"], remove["after"], remove["extractedItemId"]) == ("remove", None, None)
    assert remove["barMenuItemId"] == str(fifteen_entry.bar_menu_item_id)
    assert remove["before"]["options"][0]["optionLabel"] == "잔"
    assert remove["summary"] == "Glenfiddich 15 삭제"
    assert {c["decision"] for c in body["proposedChanges"]} == {"pending"}


def test_review_lists_items_of_every_image_in_order(client, db_session, image_storage, operator, glenfiddich):
    import_id = upload(client, make_bar(db_session), operator, filenames=("sample.jpg", "sample-2.jpg"))

    body = get_import(client, import_id, operator)

    assert [image["imageOrder"] for image in body["images"]] == [1, 2]
    assert [len(image["items"]) for image in body["images"]] == [5, 5]
    # Repeated products in the second photo add no changes; each unmatched line does.
    assert [c["changeType"] for c in body["proposedChanges"]] == ["add", "add", "add"]


def test_applied_import(client, db_session, operator):
    menu_import = make_import(db_session, ImportStatus.APPLIED, [PipelineStatus.SUCCEEDED])
    applied_at = datetime(2026, 10, 4, 9, 15, tzinfo=timezone.utc)
    menu_import.review_confirmed_at = applied_at
    menu_import.review_version = 2
    board = publish_menu(db_session, db_session.get(Bar, menu_import.bar_id), [])
    board.last_import_id = menu_import.id
    db_session.flush()

    assert get_import(client, menu_import.id, operator) == {
        "menuImportId": str(menu_import.id),
        "barId": str(menu_import.bar_id),
        "status": "applied",
        "reviewVersion": 2,
        "appliedAt": "2026-10-04T09:15:00Z",
        "menuBoardId": str(board.id),
    }


@pytest.mark.parametrize("import_id", [str(uuid4()), "not-a-uuid"])
def test_unknown_import_returns_not_found(client, operator, import_id):
    response = client.get(f"/api/menu-imports/{import_id}", headers=operator)

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "MENU_IMPORT_NOT_FOUND",
        "message": "메뉴 등록 작업을 찾을 수 없습니다.",
        "details": {"menuImportId": import_id},
        "fieldErrors": [],
    }


def test_operators_only(client, db_session, token_for):
    menu_import = make_import(db_session, ImportStatus.PROCESSING, [PipelineStatus.QUEUED])
    customer = {"Authorization": f"Bearer {token_for('customer')}"}

    assert client.get(f"/api/menu-imports/{menu_import.id}", headers=customer).status_code == 403
    assert client.get(f"/api/menu-imports/{menu_import.id}").status_code == 401
