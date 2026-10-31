"""Resuming menu imports that a server restart interrupted (app.services.menu_import_processing)."""

import io
import logging
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import app.main
from app.adapters.extraction import MockMenuExtractor
from app.main import recover_unfinished_imports
from app.models import ExtractedItem, ImportMode, ImportStatus, MenuImport, PipelineStatus
from app.services import menu_import_processing
from app.services.menu_import_processing import (
    MAX_RECOVERIES,
    find_unfinished_imports,
    process_menu_import,
    recover_imports,
)
from app.services.menu_import_upload import ImageUpload, create_menu_import
from tests.factories import make_bar

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"


class Crash(BaseException):
    """Stands for the process dying: not an Exception, so processing does not catch it."""


class CrashingExtractor(MockMenuExtractor):
    def __init__(self, crash_on_call: int) -> None:
        self.calls = 0
        self.crash_on_call = crash_on_call

    def extract(self, image, content_type, filename):
        self.calls += 1
        if self.calls == self.crash_on_call:
            raise Crash
        return super().extract(image, content_type, filename)


@pytest.fixture
def factory(db_session):
    return lambda: nullcontext(db_session)


def new_import(db_session, storage, *, images: int = 3, key: str = "key-1") -> MenuImport:
    """An `uploaded` import whose processing never started, as if the server stopped right after the upload."""
    uploads = [ImageUpload(f"page-{n}.jpg", "image/jpeg", io.BytesIO(JPEG)) for n in range(1, images + 1)]
    menu_import, _ = create_menu_import(
        db_session,
        storage,
        MockMenuExtractor(),
        bar_id=str(make_bar(db_session, key).id),
        idempotency_key=key,
        mode=ImportMode.FULL_REPLACE,
        owner_note=None,
        uploads=uploads,
    )
    return menu_import


def interrupted_import(db_session, factory, storage, *, crash_on_call: int = 2) -> MenuImport:
    """A `processing` import stopped while extracting image `crash_on_call`."""
    menu_import = new_import(db_session, storage)
    menu_import.status = ImportStatus.PROCESSING
    db_session.commit()
    with pytest.raises(Crash):
        process_menu_import(factory, storage, CrashingExtractor(crash_on_call), menu_import.id)
    return menu_import


def run_statuses(db_session, menu_import) -> list[PipelineStatus]:
    db_session.refresh(menu_import)
    return [image.extraction_run.status for image in menu_import.images]


def item_count(db_session, run_id) -> int:
    stmt = select(func.count()).select_from(ExtractedItem).where(ExtractedItem.extraction_run_id == run_id)
    return db_session.scalar(stmt)


def recover(factory, storage, import_ids):
    recover_imports(import_ids, factory, storage, MockMenuExtractor())


def test_an_interruption_leaves_a_running_run(db_session, factory, image_storage):
    menu_import = interrupted_import(db_session, factory, image_storage)

    assert menu_import.status == ImportStatus.PROCESSING
    assert run_statuses(db_session, menu_import) == [
        PipelineStatus.SUCCEEDED,
        PipelineStatus.RUNNING,
        PipelineStatus.QUEUED,
    ]


def test_resumes_from_the_interrupted_image(db_session, factory, image_storage):
    menu_import = interrupted_import(db_session, factory, image_storage)
    first_run = menu_import.images[0].extraction_run
    first_items = item_count(db_session, first_run.id)

    recover(factory, image_storage, [menu_import.id])

    db_session.refresh(menu_import)
    assert (menu_import.status, menu_import.recovery_count) == (ImportStatus.READY_FOR_REVIEW, 1)
    assert run_statuses(db_session, menu_import) == [PipelineStatus.SUCCEEDED] * 3
    # The image finished before the restart is not extracted again.
    assert item_count(db_session, first_run.id) == first_items
    assert all(item_count(db_session, image.extraction_run.id) == first_items for image in menu_import.images)


def test_resumes_an_import_whose_processing_never_started(db_session, factory, image_storage):
    menu_import = new_import(db_session, image_storage)

    recover(factory, image_storage, find_unfinished_imports(factory))

    db_session.refresh(menu_import)
    assert (menu_import.status, menu_import.recovery_count) == (ImportStatus.READY_FOR_REVIEW, 1)


def test_finds_only_unfinished_imports(db_session, image_storage):
    imports = {status: new_import(db_session, image_storage, images=1, key=status.value) for status in ImportStatus}
    for status, menu_import in imports.items():
        menu_import.status = status
    db_session.flush()

    found = find_unfinished_imports(lambda: nullcontext(db_session))

    assert set(found) == {imports[ImportStatus.UPLOADED].id, imports[ImportStatus.PROCESSING].id}


@pytest.mark.parametrize("status", [ImportStatus.READY_FOR_REVIEW, ImportStatus.FAILED])
def test_an_import_finished_after_it_was_found_is_left_alone(db_session, factory, image_storage, status):
    menu_import = new_import(db_session, image_storage)
    menu_import.status = status
    db_session.commit()

    recover(factory, image_storage, [menu_import.id])

    db_session.refresh(menu_import)
    assert (menu_import.status, menu_import.recovery_count) == (status, 0)


def test_past_the_limit_the_interrupted_image_fails(client, db_session, factory, image_storage, token_for):
    menu_import = interrupted_import(db_session, factory, image_storage)
    menu_import.recovery_count = MAX_RECOVERIES
    db_session.commit()

    recover(factory, image_storage, [menu_import.id])

    db_session.refresh(menu_import)
    assert menu_import.status == ImportStatus.FAILED
    assert menu_import.completed_at is not None
    assert run_statuses(db_session, menu_import) == [
        PipelineStatus.SUCCEEDED,
        PipelineStatus.FAILED,
        PipelineStatus.QUEUED,
    ]
    operator = {"Authorization": f"Bearer {token_for('operator')}"}
    body = client.get(f"/api/menu-imports/{menu_import.id}", headers=operator).json()
    assert body["failure"]["code"] == "IMAGE_EXTRACTION_FAILED"
    assert body["progress"] == {"totalImages": 3, "completedImages": 1, "failedImages": 1}


def test_past_the_limit_without_an_interrupted_image_processing_fails(
    client, db_session, factory, image_storage, token_for
):
    menu_import = new_import(db_session, image_storage)
    menu_import.recovery_count = MAX_RECOVERIES
    db_session.commit()

    recover(factory, image_storage, [menu_import.id])

    operator = {"Authorization": f"Bearer {token_for('operator')}"}
    body = client.get(f"/api/menu-imports/{menu_import.id}", headers=operator).json()
    assert (body["status"], body["failure"]["code"]) == ("failed", "PROCESSING_FAILED")


def test_counts_each_recovery_up_to_the_limit(db_session, factory, image_storage):
    menu_import = new_import(db_session, image_storage)

    for attempt in range(1, MAX_RECOVERIES + 1):
        # Every resumed run dies on its first image again.
        assert menu_import_processing._prepare_resume(factory, menu_import.id)
        with pytest.raises(Crash):
            process_menu_import(factory, image_storage, CrashingExtractor(1), menu_import.id)
        db_session.refresh(menu_import)
        assert menu_import.recovery_count == attempt

    recover(factory, image_storage, [menu_import.id])
    db_session.refresh(menu_import)
    assert menu_import.status == ImportStatus.FAILED


def test_one_import_that_cannot_be_recovered_does_not_stop_the_rest(
    db_session, factory, image_storage, monkeypatch, caplog
):
    broken = new_import(db_session, image_storage, key="broken")
    healthy = new_import(db_session, image_storage, key="healthy")
    original = menu_import_processing.process_menu_import

    def process(session_factory, storage, extractor, import_id, **kwargs):
        if import_id == broken.id:
            raise RuntimeError("storage is down")
        original(session_factory, storage, extractor, import_id, **kwargs)

    monkeypatch.setattr(menu_import_processing, "process_menu_import", process)
    with caplog.at_level(logging.ERROR):
        recover(factory, image_storage, [broken.id, healthy.id])

    db_session.refresh(healthy)
    assert healthy.status == ImportStatus.READY_FOR_REVIEW
    assert f"Menu import {broken.id} could not be recovered" in caplog.text


# ---- start-up (app.main) ----


def test_start_up_resumes_in_a_background_thread(db_session, factory, image_storage, monkeypatch):
    menu_import = new_import(db_session, image_storage)
    monkeypatch.setattr(app.main, "get_session_factory", lambda: factory)
    monkeypatch.setattr(app.main, "get_image_storage", lambda: image_storage)

    thread = recover_unfinished_imports()
    thread.join(timeout=30)

    assert thread.daemon and not thread.is_alive()
    db_session.refresh(menu_import)
    assert menu_import.status == ImportStatus.READY_FOR_REVIEW


def test_start_up_without_unfinished_imports_starts_nothing(db_session, factory, monkeypatch):
    monkeypatch.setattr(app.main, "get_session_factory", lambda: factory)

    assert recover_unfinished_imports() is None


def test_an_unreachable_database_does_not_stop_the_start(monkeypatch, caplog):
    def unreachable(session_factory):
        raise OSError("connection refused")

    monkeypatch.setattr(app.main, "find_unfinished_imports", unreachable)
    with caplog.at_level(logging.ERROR):
        assert recover_unfinished_imports() is None

    assert "Could not look for menu imports to recover" in caplog.text


def test_the_app_starts_recovery_when_it_starts(monkeypatch):
    calls = []
    monkeypatch.setattr(app.main, "recover_unfinished_imports", lambda: calls.append("recover"))

    with TestClient(app.main.app):
        pass

    assert calls == ["recover"]
