"""POST /api/menu-imports/{menuImportId}/cancel (spec 5.7) and canceling while the import is processed."""

import io
from contextlib import nullcontext
from datetime import timezone
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import func, select

from app.adapters.extraction import ExtractionError, MockMenuExtractor
from app.models import (
    ExtractedItem,
    ImportMode,
    ImportStatus,
    MenuBoard,
    MenuImage,
    MenuImport,
    MenuImportChange,
    PipelineStatus,
    ResolutionCandidate,
)
from app.services import menu_import_processing
from app.services.menu_import_cancel import cancel_menu_import
from app.services.menu_import_processing import process_menu_import, start_processing
from app.services.menu_import_upload import ImageUpload, create_menu_import
from tests.factories import make_bar

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def factory(db_session):
    return lambda: nullcontext(db_session)


def new_import(db_session, storage, *, status=ImportStatus.UPLOADED, images=2, key="key-1") -> MenuImport:
    uploads = [ImageUpload(f"page-{n}.jpg", "image/jpeg", io.BytesIO(JPEG)) for n in range(1, images + 1)]
    menu_import, _ = create_menu_import(
        db_session,
        storage,
        MockMenuExtractor(),
        bar=make_bar(db_session, key),
        idempotency_key=key,
        mode=ImportMode.FULL_REPLACE,
        owner_note=None,
        uploads=uploads,
    )
    menu_import.status = status
    db_session.commit()
    return menu_import


def cancel(client, headers, menu_import_id):
    return client.post(f"/api/menu-imports/{menu_import_id}/cancel", headers=headers)


def count(db_session, model, *where) -> int:
    return db_session.scalar(select(func.count()).select_from(model).where(*where))


def run_statuses(db_session, menu_import) -> list[PipelineStatus]:
    db_session.expire_all()
    return [image.extraction_run.status for image in db_session.get(MenuImport, menu_import.id).images]


# ---- the API ----


@pytest.mark.parametrize("status", [ImportStatus.UPLOADED, ImportStatus.PROCESSING, ImportStatus.READY_FOR_REVIEW])
def test_cancels_an_unfinished_import(client, db_session, image_storage, operator, status):
    menu_import = new_import(db_session, image_storage, status=status)

    response = cancel(client, operator, menu_import.id)

    assert response.status_code == 200, response.text
    db_session.refresh(menu_import)
    assert menu_import.status == ImportStatus.CANCELED
    assert menu_import.completed_at is not None
    assert response.json() == {
        "menuImportId": str(menu_import.id),
        "barId": str(menu_import.bar_id),
        "status": "canceled",
        "canceledAt": menu_import.completed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def test_the_status_api_returns_the_canceled_response(client, db_session, image_storage, operator):
    menu_import = new_import(db_session, image_storage)
    canceled = cancel(client, operator, menu_import.id).json()

    response = client.get(f"/api/menu-imports/{menu_import.id}", headers=operator)

    assert response.status_code == 200
    assert response.json() == canceled


def test_canceling_again_returns_the_same_response(client, db_session, image_storage, operator):
    menu_import = new_import(db_session, image_storage)
    first = cancel(client, operator, menu_import.id)

    second = cancel(client, operator, menu_import.id)

    assert second.status_code == 200
    assert second.json() == first.json()


@pytest.mark.parametrize("status", [ImportStatus.APPLIED, ImportStatus.FAILED])
def test_a_finished_import_cannot_be_canceled(client, db_session, image_storage, operator, status):
    menu_import = new_import(db_session, image_storage, status=status)

    response = cancel(client, operator, menu_import.id)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_IMPORT_STATE"
    assert error["details"] == {"menuImportId": str(menu_import.id), "status": status.value}
    db_session.refresh(menu_import)
    assert (menu_import.status, menu_import.completed_at) == (status, None)


@pytest.mark.parametrize("menu_import_id", [str(uuid4()), "not-a-uuid"])
def test_an_unknown_import_is_not_found(client, operator, menu_import_id):
    response = cancel(client, operator, menu_import_id)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MENU_IMPORT_NOT_FOUND"


def test_a_ready_import_is_canceled_without_touching_the_menu_or_its_records(
    client, db_session, image_storage, operator
):
    menu_import = new_import(db_session, image_storage, status=ImportStatus.PROCESSING)
    process_menu_import(lambda: nullcontext(db_session), image_storage, MockMenuExtractor(), menu_import.id)
    db_session.refresh(menu_import)
    assert menu_import.status == ImportStatus.READY_FOR_REVIEW
    items = count(db_session, ExtractedItem)
    changes = count(db_session, MenuImportChange, MenuImportChange.menu_import_id == menu_import.id)

    assert cancel(client, operator, menu_import.id).status_code == 200

    assert count(db_session, MenuBoard, MenuBoard.bar_id == menu_import.bar_id) == 0
    assert count(db_session, MenuImage, MenuImage.menu_import_id == menu_import.id) == 2
    assert count(db_session, ExtractedItem) == items > 0
    assert count(db_session, MenuImportChange, MenuImportChange.menu_import_id == menu_import.id) == changes
    assert run_statuses(db_session, menu_import) == [PipelineStatus.SUCCEEDED] * 2


def test_the_bar_takes_a_new_upload_after_a_cancel(client, db_session, image_storage, operator):
    menu_import = new_import(db_session, image_storage)
    upload = {
        "headers": {**operator, "Idempotency-Key": "key-2"},
        "data": {"mode": "full_replace"},
        "files": [("images", ("page.jpg", JPEG, "image/jpeg"))],
    }
    blocked = client.post(f"/api/bars/{menu_import.bar_id}/menu-imports", **upload)
    assert blocked.json()["error"]["code"] == "ACTIVE_IMPORT_EXISTS"

    cancel(client, operator, menu_import.id)
    response = client.post(f"/api/bars/{menu_import.bar_id}/menu-imports", **upload)

    assert response.status_code == 202, response.text


def test_a_canceled_import_cannot_be_reviewed(client, db_session, image_storage, operator):
    menu_import = new_import(db_session, image_storage, status=ImportStatus.READY_FOR_REVIEW)
    menu_import.review_version = 1
    db_session.commit()
    cancel(client, operator, menu_import.id)

    response = client.post(
        f"/api/menu-imports/{menu_import.id}/review-and-apply",
        headers=operator,
        json={"reviewVersion": menu_import.review_version, "itemDecisions": [], "changeDecisions": []},
    )

    assert response.status_code == 409
    assert response.json()["error"]["details"]["status"] == "canceled"


def test_the_bar_lists_its_canceled_imports(client, db_session, image_storage, operator):
    menu_import = new_import(db_session, image_storage)
    cancel(client, operator, menu_import.id)

    response = client.get(f"/api/bars/{menu_import.bar_id}/menu-imports?status=canceled", headers=operator)

    assert response.status_code == 200
    [item] = response.json()["items"]
    assert (item["menuImportId"], item["status"]) == (str(menu_import.id), "canceled")
    assert item["completedAt"] is not None
    active = client.get(f"/api/bars/{menu_import.bar_id}/menu-imports?status=active", headers=operator)
    assert active.json()["items"] == []


# ---- canceling while the import is processed ----


class CancelingExtractor(MockMenuExtractor):
    """Cancels the import while extracting image `on_call`, as a request in another session would."""

    def __init__(self, session, menu_import_id, on_call, error=None) -> None:
        self.session, self.menu_import_id, self.on_call, self.error = session, menu_import_id, on_call, error
        self.calls = 0

    def extract(self, image, content_type, filename):
        self.calls += 1
        result = super().extract(image, content_type, filename)
        if self.calls == self.on_call:
            cancel_menu_import(self.session, self.menu_import_id)
            if self.error is not None:
                raise self.error
        return result


@pytest.mark.parametrize("error", [None, ExtractionError("model failed")])
def test_a_cancel_during_extraction_stores_nothing_more(db_session, factory, image_storage, error):
    menu_import = new_import(db_session, image_storage, status=ImportStatus.PROCESSING, images=3)
    extractor = CancelingExtractor(db_session, menu_import.id, on_call=2, error=error)

    process_menu_import(factory, image_storage, extractor, menu_import.id)

    assert extractor.calls == 2
    db_session.expire_all()
    menu_import = db_session.get(MenuImport, menu_import.id)
    assert menu_import.status == ImportStatus.CANCELED
    first, second, third = (image.extraction_run for image in menu_import.images)
    assert (first.status, second.status, third.status) == (
        PipelineStatus.SUCCEEDED,
        PipelineStatus.FAILED,
        PipelineStatus.QUEUED,
    )
    # The run canceled mid-extraction keeps the cancel as its record, not the result or the error.
    assert second.raw_output["error"] == "Canceled"
    assert count(db_session, ExtractedItem, ExtractedItem.extraction_run_id == second.id) == 0
    assert count(db_session, ExtractedItem, ExtractedItem.extraction_run_id == first.id) > 0


def test_a_cancel_between_images_stops_before_the_next(db_session, factory, image_storage, monkeypatch):
    menu_import = new_import(db_session, image_storage, status=ImportStatus.PROCESSING, images=2)
    real_check = menu_import_processing._still_processing
    checks = []

    def cancel_before_the_second_image(session, import_id):
        checks.append(import_id)
        # Checks: before image 1, after image 1, before image 2.
        if len(checks) == 3:
            cancel_menu_import(session, import_id)
        return real_check(session, import_id)

    monkeypatch.setattr(menu_import_processing, "_still_processing", cancel_before_the_second_image)

    process_menu_import(factory, image_storage, MockMenuExtractor(), menu_import.id)

    assert len(checks) == 3
    assert run_statuses(db_session, menu_import) == [PipelineStatus.SUCCEEDED, PipelineStatus.QUEUED]
    assert db_session.get(MenuImport, menu_import.id).status == ImportStatus.CANCELED


def test_matching_after_a_cancel_is_rolled_back(db_session, factory, image_storage, monkeypatch):
    menu_import = new_import(db_session, image_storage, status=ImportStatus.PROCESSING)
    real_resolve = menu_import_processing._resolve_and_draft

    def cancel_then_resolve(session, menu_import, llm_layer=None):
        # A cancel committed before matching ends: the job's draft must not be kept.
        cancel_menu_import(session, menu_import.id)
        real_resolve(session, menu_import, llm_layer)

    monkeypatch.setattr(menu_import_processing, "_resolve_and_draft", cancel_then_resolve)

    process_menu_import(factory, image_storage, MockMenuExtractor(), menu_import.id)

    db_session.expire_all()
    menu_import = db_session.get(MenuImport, menu_import.id)
    assert (menu_import.status, menu_import.review_version) == (ImportStatus.CANCELED, 0)
    assert count(db_session, MenuImportChange, MenuImportChange.menu_import_id == menu_import.id) == 0
    assert count(db_session, ResolutionCandidate) == 0


def test_an_error_after_a_cancel_keeps_the_import_canceled(db_session, factory, image_storage, monkeypatch):
    menu_import = new_import(db_session, image_storage, status=ImportStatus.PROCESSING)

    def cancel_then_crash(session, menu_import, llm_layer=None):
        cancel_menu_import(session, menu_import.id)
        raise RuntimeError("bug")

    monkeypatch.setattr(menu_import_processing, "_resolve_and_draft", cancel_then_crash)

    process_menu_import(factory, image_storage, MockMenuExtractor(), menu_import.id)

    db_session.expire_all()
    assert db_session.get(MenuImport, menu_import.id).status == ImportStatus.CANCELED


def test_an_import_canceled_before_processing_is_not_processed(db_session, factory, image_storage):
    menu_import = new_import(db_session, image_storage, status=ImportStatus.PROCESSING)
    cancel_menu_import(db_session, menu_import.id)

    process_menu_import(factory, image_storage, MockMenuExtractor(), menu_import.id)

    assert run_statuses(db_session, menu_import) == [PipelineStatus.QUEUED] * 2


def test_a_cancel_before_processing_starts_is_kept(db_session, factory, image_storage):
    # Canceled after the upload committed the import but before the request started processing it.
    menu_import = new_import(db_session, image_storage)
    cancel_menu_import(db_session, menu_import.id)
    db_session.expire_all()
    tasks = BackgroundTasks()

    start_processing(
        db_session, tasks, menu_import, session_factory=factory, storage=image_storage, extractor=MockMenuExtractor()
    )

    assert tasks.tasks == []
    db_session.expire_all()
    assert db_session.get(MenuImport, menu_import.id).status == ImportStatus.CANCELED
