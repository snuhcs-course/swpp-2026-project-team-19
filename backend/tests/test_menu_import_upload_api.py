import re
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import BarStatus, ExtractionApproach, ImportStatus, MenuImport
from app.services import menu_import_upload
from tests.factories import make_bar

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"
PNG = b"\x89PNG\r\n\x1a\n" + b"png-body"
HEIC = b"\x00\x00\x00\x18ftypheic" + b"heic-body"
GIF = b"GIF89a" + b"gif-body"


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def bar(db_session):
    return make_bar(db_session, "Seorosang")


def upload(client, bar_id, headers, *, key="key-1", images=None, mode="full_replace", note=None):
    images = images if images is not None else [("page-1.jpg", JPEG, "image/jpeg"), ("page-2.png", PNG, "image/png")]
    data = {"mode": mode} if note is None else {"mode": mode, "ownerNote": note}
    return client.post(
        f"/api/bars/{bar_id}/menu-imports",
        headers={**headers, "Idempotency-Key": key} if key is not None else headers,
        data=data,
        files=[("images", image) for image in images],
    )


def import_count(db_session):
    return db_session.scalar(select(func.count()).select_from(MenuImport))


def test_upload_stores_images_and_creates_rows(client, db_session, image_storage, operator, bar):
    response = upload(client, bar.id, operator, note=" 2026년 10월 메뉴판 ")

    assert response.status_code == 202, response.text
    body = response.json()
    # Processing is scheduled before the response; TestClient runs it right after.
    assert body["status"] == "processing"
    assert body["imageCount"] == 2
    assert body["statusUrl"] == f"/api/menu-imports/{body['menuImportId']}"
    assert body["pollAfterMs"] == 3000
    assert response.headers["Location"] == body["statusUrl"]
    assert response.headers["Retry-After"] == "3"

    menu_import = db_session.get(MenuImport, body["menuImportId"])
    assert (menu_import.bar_id, menu_import.mode.value) == (bar.id, "full_replace")
    assert menu_import.owner_note == "2026년 10월 메뉴판"
    assert re.fullmatch(r"[0-9a-f]{64}", menu_import.request_fingerprint)
    images = menu_import.images
    assert [(i.image_order, i.original_filename) for i in images] == [(1, "page-1.jpg"), (2, "page-2.png")]
    assert images[0].storage_key == f"menus/{bar.id}/{menu_import.id}/page-1.jpg"
    assert images[1].storage_key.endswith("/page-2.png")
    assert [image_storage.read(i.storage_key) for i in images] == [JPEG, PNG]
    for image in images:
        run = image.extraction_run
        assert (run.approach, run.provider, run.pipeline_version) == (
            ExtractionApproach.VISION_LLM,
            "mock",
            "bottlemap-menu-mock-v1",
        )


def test_blank_note_becomes_null(client, db_session, image_storage, operator, bar):
    response = upload(client, bar.id, operator, note="   ")

    assert response.status_code == 202, response.text
    assert db_session.get(MenuImport, response.json()["menuImportId"]).owner_note is None


def test_generic_content_type_is_judged_by_the_file_content(client, image_storage, operator, bar):
    response = upload(client, bar.id, operator, images=[("photo", PNG, "application/octet-stream")])

    assert response.status_code == 202, response.text


def test_retry_with_same_key_and_content_returns_the_existing_import(client, db_session, image_storage, operator, bar):
    first = upload(client, bar.id, operator)
    stored = sorted(p for p in image_storage.root.rglob("*") if p.is_file())

    retry = upload(client, bar.id, operator)

    assert retry.status_code == 202
    assert retry.json() == {**first.json(), "status": "ready_for_review"}  # the import's current status
    assert import_count(db_session) == 1
    assert sorted(p for p in image_storage.root.rglob("*") if p.is_file()) == stored


@pytest.mark.parametrize(
    "change",
    [{"mode": "partial_update"}, {"note": "other"}, {"images": [("page-1.jpg", JPEG, "image/jpeg")]}],
)
def test_same_key_with_different_content_is_rejected(client, db_session, image_storage, operator, bar, change):
    first = upload(client, bar.id, operator)

    response = upload(client, bar.id, operator, **change)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert error["details"] == {"menuImportId": first.json()["menuImportId"]}
    assert import_count(db_session) == 1


def test_file_names_are_not_part_of_the_request_content(client, image_storage, operator, bar):
    first = upload(client, bar.id, operator)

    retry = upload(client, bar.id, operator, images=[("a.jpg", JPEG, "image/jpeg"), ("b.png", PNG, "image/png")])

    assert retry.json()["menuImportId"] == first.json()["menuImportId"]


def test_unfinished_import_blocks_a_new_one_for_the_same_bar(client, db_session, image_storage, operator, bar):
    first = upload(client, bar.id, operator, key="key-1")

    response = upload(client, bar.id, operator, key="key-2")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "ACTIVE_IMPORT_EXISTS"
    assert error["details"] == {"menuImportId": first.json()["menuImportId"], "status": "ready_for_review"}


@pytest.mark.parametrize("finished", [ImportStatus.APPLIED, ImportStatus.FAILED])
def test_finished_imports_do_not_block(client, db_session, image_storage, operator, bar, finished):
    first = upload(client, bar.id, operator, key="key-1")
    db_session.get(MenuImport, first.json()["menuImportId"]).status = finished
    db_session.flush()

    assert upload(client, bar.id, operator, key="key-2").status_code == 202


def test_unfinished_import_of_another_bar_does_not_block(client, db_session, image_storage, operator, bar):
    other = make_bar(db_session, "Other Bar")
    upload(client, other.id, operator, key="key-1")

    assert upload(client, bar.id, operator, key="key-2").status_code == 202


@pytest.mark.parametrize("bar_id", [str(uuid4()), "not-a-uuid", "inactive"])
def test_missing_or_inactive_bar_returns_not_found(client, db_session, image_storage, operator, bar_id):
    if bar_id == "inactive":
        bar_id = str(make_bar(db_session, status=BarStatus.INACTIVE).id)

    response = upload(client, bar_id, operator)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BAR_NOT_FOUND"


def test_customer_is_forbidden_and_anonymous_is_unauthenticated(client, image_storage, token_for, bar):
    customer = {"Authorization": f"Bearer {token_for('customer')}"}

    assert upload(client, bar.id, customer).json()["error"]["code"] == "FORBIDDEN"
    assert upload(client, bar.id, {}).json()["error"]["code"] == "UNAUTHENTICATED"


def test_too_many_images(client, db_session, image_storage, operator, bar):
    images = [(f"p{n}.jpg", JPEG, "image/jpeg") for n in range(menu_import_upload.MAX_IMAGES + 1)]

    response = upload(client, bar.id, operator, images=images)

    assert response.status_code == 413
    assert response.json()["error"]["details"]["maxImages"] == menu_import_upload.MAX_IMAGES
    assert import_count(db_session) == 0


@pytest.mark.parametrize(("limit", "value"), [("MAX_IMAGE_BYTES", len(JPEG) - 1), ("MAX_TOTAL_BYTES", len(JPEG) + 1)])
def test_size_limits(client, db_session, image_storage, operator, bar, monkeypatch, limit, value):
    monkeypatch.setattr(menu_import_upload, limit, value)

    response = upload(client, bar.id, operator, images=[("a.jpg", JPEG, "image/jpeg"), ("b.jpg", JPEG, "image/jpeg")])

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


def test_image_at_exactly_the_size_limit_is_accepted(client, image_storage, operator, bar, monkeypatch):
    monkeypatch.setattr(menu_import_upload, "MAX_IMAGE_BYTES", len(JPEG))

    assert upload(client, bar.id, operator, images=[("a.jpg", JPEG, "image/jpeg")]).status_code == 202


@pytest.mark.parametrize(
    "images",
    [
        [("a.jpg", JPEG, "image/jpeg"), ("b.gif", GIF, "image/gif")],
        [("a.jpg", JPEG, "image/jpeg"), ("b.heic", HEIC, "image/heic")],  # extraction takes JPEG and PNG only
        [("a.jpg", JPEG, "image/jpeg"), ("b.jpg", PNG, "image/jpeg")],  # declared type disagrees
    ],
)
def test_unsupported_or_mismatched_type(client, db_session, image_storage, operator, bar, images):
    response = upload(client, bar.id, operator, images=images)

    assert response.status_code == 415
    error = response.json()["error"]
    assert (error["code"], error["details"]["imageOrder"]) == ("UNSUPPORTED_IMAGE_TYPE", 2)
    assert not any(p.is_file() for p in image_storage.root.rglob("*"))


@pytest.mark.parametrize(
    ("kwargs", "path", "code"),
    [
        ({"key": None}, "Idempotency-Key", "MISSING"),
        ({"images": []}, "images", "MISSING"),
        ({"mode": "replace_all"}, "mode", "ENUM"),
    ],
)
def test_invalid_request_fields(client, image_storage, operator, bar, kwargs, path, code):
    response = upload(client, bar.id, operator, **kwargs)

    assert response.status_code == 422
    assert [(e["path"], e["code"]) for e in response.json()["error"]["fieldErrors"]] == [(path, code)]


class FailingStorage:
    """Delegates to real storage but fails on the given save call."""

    def __init__(self, storage, fail_on_save):
        self.storage, self.fail_on_save, self.saves = storage, fail_on_save, 0

    def __getattr__(self, name):
        return getattr(self.storage, name)

    def save(self, key, data, content_type):
        self.saves += 1
        if self.saves == self.fail_on_save:
            raise OSError("disk full")
        self.storage.save(key, data, content_type)


def test_storage_failure_removes_already_stored_images(client, db_session, image_storage, operator, bar):
    from app.api.deps import get_image_storage
    from app.main import app

    app.dependency_overrides[get_image_storage] = lambda: FailingStorage(image_storage, fail_on_save=2)

    with pytest.raises(OSError):
        upload(client, bar.id, operator)

    assert not any(p.is_file() for p in image_storage.root.rglob("*"))
    assert import_count(db_session) == 0


def test_cleanup_failure_keeps_the_original_error(client, db_session, image_storage, operator, bar, caplog):
    from app.api.deps import get_image_storage
    from app.main import app

    class StuckStorage(FailingStorage):
        def delete(self, key):
            raise OSError("bucket unreachable")

    app.dependency_overrides[get_image_storage] = lambda: StuckStorage(image_storage, fail_on_save=2)

    with pytest.raises(OSError, match="disk full"):
        upload(client, bar.id, operator)

    assert "Could not delete menus/" in caplog.text
    assert import_count(db_session) == 0


def test_concurrent_retry_that_loses_the_insert_race_returns_the_winner(
    client, db_session, image_storage, operator, bar, monkeypatch
):
    winner = upload(client, bar.id, operator)
    stored = sorted(p for p in image_storage.root.rglob("*") if p.is_file())
    # Simulate a request that checked the key before the winner committed.
    real_find = menu_import_upload._find_by_key
    calls = []

    def find_missing_first_time(session, key):
        calls.append(key)
        return None if len(calls) == 1 else real_find(session, key)

    monkeypatch.setattr(menu_import_upload, "_find_by_key", find_missing_first_time)
    # The unfinished-import check would otherwise answer first.
    monkeypatch.setattr(menu_import_upload, "UNFINISHED_STATUSES", ())

    response = upload(client, bar.id, operator)

    assert response.status_code == 202
    assert response.json()["menuImportId"] == winner.json()["menuImportId"]
    assert len(calls) == 2  # the pre-check missed it; the lookup after the unique violation found it
    assert import_count(db_session) == 1
    # The loser's images were removed; only the winner's remain.
    assert sorted(p for p in image_storage.root.rglob("*") if p.is_file()) == stored
