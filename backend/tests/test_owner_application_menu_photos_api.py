"""Menu photos of an owner application (API spec, section 3.11.15), and their removal on cancel (3.11.5)."""

import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, select, update

from app.adapters.storage import LocalImageStorage
from app.api.deps import get_image_storage
from app.main import app
from app.models import BarOwnerApplication, BarOwnerApplicationMenuImage, OwnerApplicationStatus, UserType
from app.services import menu_import_upload
from app.services.image_links import ImageLinks
from tests.factories import make_application, make_application_menu_image, make_bar, make_user

SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"
OTHER_SUBJECT = "5d1c2b3a-0000-4000-8000-000000000002"
MISSING_ID = "99999999-9999-4999-8999-999999999999"

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"
PNG = b"\x89PNG\r\n\x1a\n" + b"png-body"
GIF = b"GIF89a" + b"gif-body"


class HookedStorage(LocalImageStorage):
    """Local storage that can fail or run code while saving, and fail while deleting."""

    def __init__(self, root) -> None:
        super().__init__(root)
        self.on_save = None
        self.fail_delete = False

    def save(self, key: str, data: bytes, content_type: str) -> None:
        if self.on_save is not None:
            self.on_save(key)
        super().save(key, data, content_type)

    def delete(self, key: str) -> None:
        if self.fail_delete:
            raise OSError("storage is down")
        super().delete(key)


@pytest.fixture
def storage(tmp_path):
    hooked = HookedStorage(tmp_path / "images")
    app.dependency_overrides[get_image_storage] = lambda: hooked
    yield hooked
    app.dependency_overrides.pop(get_image_storage, None)


@pytest.fixture
def applicant(db_session):
    return make_user(db_session, SUBJECT)


@pytest.fixture
def auth(supabase, applicant):
    return {"Authorization": f"Bearer {supabase.token(sub=SUBJECT)}"}


@pytest.fixture
def pending(db_session, applicant):
    return make_application(db_session, applicant)


def put_photos(client, headers, application_id, images=None):
    images = images if images is not None else [("page-1.jpg", JPEG, "image/jpeg"), ("page-2.png", PNG, "image/png")]
    return client.put(
        f"/api/owner-applications/{application_id}/menu-photos",
        headers=headers,
        files=[("images", image) for image in images],
    )


def error_of(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def photo_rows(db_session, application) -> list[BarOwnerApplicationMenuImage]:
    return list(
        db_session.scalars(
            select(BarOwnerApplicationMenuImage)
            .where(BarOwnerApplicationMenuImage.application_id == application.id)
            .order_by(BarOwnerApplicationMenuImage.image_order)
        )
    )


def stored_files(storage) -> set[str]:
    return {path.relative_to(storage.root).as_posix() for path in storage.root.rglob("*") if path.is_file()}


def test_stores_the_photos_in_order(client, db_session, storage, auth, pending):
    response = put_photos(client, auth, pending.id)

    assert response.status_code == 200, response.text
    rows = photo_rows(db_session, pending)
    assert [(row.image_order, row.original_filename) for row in rows] == [(1, "page-1.jpg"), (2, "page-2.png")]
    assert [row.content_sha256 for row in rows] == [hashlib.sha256(JPEG).hexdigest(), hashlib.sha256(PNG).hexdigest()]
    assert rows[0].storage_key.startswith(f"owner-applications/{pending.id}/")
    assert rows[0].storage_key.endswith("/page-1.jpg") and rows[1].storage_key.endswith("/page-2.png")
    assert stored_files(storage) == {row.storage_key for row in rows}
    assert storage.read(rows[0].storage_key) == JPEG
    photos = response.json()["menuPhotos"]
    assert [photo["imageOrder"] for photo in photos] == [1, 2]
    assert photos[0]["imageUrl"] == f"http://testserver/media/{rows[0].storage_key}"
    assert photos[0]["imageUrlExpiresAt"] is None


def test_each_upload_replaces_all_photos(client, db_session, storage, auth, pending):
    put_photos(client, auth, pending.id)
    first = {row.storage_key for row in photo_rows(db_session, pending)}

    response = put_photos(client, auth, pending.id, images=[("only.png", PNG, "image/png")])

    assert response.status_code == 200
    rows = photo_rows(db_session, pending)
    assert [(row.image_order, row.original_filename) for row in rows] == [(1, "only.png")]
    assert stored_files(storage) == {rows[0].storage_key}
    assert first.isdisjoint(stored_files(storage))
    assert len(response.json()["menuPhotos"]) == 1


def test_locks_the_application_before_swapping_the_rows(client, db_session, storage, auth, pending):
    statements = []

    def listen(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(db_session.get_bind(), "before_cursor_execute", listen)
    try:
        assert put_photos(client, auth, pending.id).status_code == 200
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", listen)

    assert any("FROM bar_owner_applications" in s and "FOR UPDATE" in s for s in statements)


def test_an_application_finished_while_storing_keeps_its_photos(client, db_session, storage, auth, pending):
    old = make_application_menu_image(db_session, pending)
    storage.save(old.storage_key, JPEG, "image/jpeg")

    def cancel_meanwhile(key):
        # Another request cancels the application while the photos are being stored.
        db_session.execute(
            update(BarOwnerApplication)
            .where(BarOwnerApplication.id == pending.id)
            .values(status=OwnerApplicationStatus.CANCELED)
        )

    storage.on_save = cancel_meanwhile
    response = put_photos(client, auth, pending.id)

    assert error_of(response) == (409, "INVALID_APPLICATION_STATE")
    assert response.json()["error"]["details"] == {"status": "canceled"}
    assert [row.storage_key for row in photo_rows(db_session, pending)] == [old.storage_key]
    assert stored_files(storage) == {old.storage_key}


def test_a_storage_failure_changes_nothing(client, db_session, storage, auth, pending):
    old = make_application_menu_image(db_session, pending)
    saved = []

    def fail_on_second(key):
        saved.append(key)
        if len(saved) == 2:
            raise OSError("storage is down")

    storage.on_save = fail_on_second
    with pytest.raises(OSError):
        put_photos(client, auth, pending.id)

    assert [row.storage_key for row in photo_rows(db_session, pending)] == [old.storage_key]
    assert stored_files(storage) == set()


def test_a_failed_delete_of_replaced_files_does_not_fail_the_upload(client, db_session, storage, auth, pending):
    old = make_application_menu_image(db_session, pending)
    storage.save(old.storage_key, JPEG, "image/jpeg")
    storage.fail_delete = True

    response = put_photos(client, auth, pending.id)

    assert response.status_code == 200
    assert old.storage_key not in {row.storage_key for row in photo_rows(db_session, pending)}


@pytest.mark.parametrize(
    "status", [OwnerApplicationStatus.CANCELED, OwnerApplicationStatus.REJECTED, OwnerApplicationStatus.APPROVED]
)
def test_only_pending_applications_take_photos(client, db_session, storage, auth, applicant, status):
    operator = make_user(db_session, "operator-subject", user_type=UserType.OPERATOR)
    finished = make_application(db_session, applicant, make_bar(db_session), status=status, reviewer=operator)

    response = put_photos(client, auth, finished.id)

    assert error_of(response) == (409, "INVALID_APPLICATION_STATE")
    assert response.json()["error"]["details"] == {"status": status.value}
    assert stored_files(storage) == set()


@pytest.mark.parametrize("target", ["someone else's", "missing", "malformed"])
def test_other_applications_look_missing(client, db_session, storage, auth, target):
    other = make_application(db_session, make_user(db_session, OTHER_SUBJECT))
    application_id = {"someone else's": str(other.id), "missing": MISSING_ID, "malformed": "x"}[target]

    assert error_of(put_photos(client, auth, application_id)) == (404, "OWNER_APPLICATION_NOT_FOUND")
    assert photo_rows(db_session, other) == []


def test_an_operator_uploads_only_to_their_own(client, db_session, storage, supabase):
    operator = make_user(db_session, SUBJECT, user_type=UserType.OPERATOR)
    headers = {"Authorization": f"Bearer {supabase.token(sub=SUBJECT)}"}
    others = make_application(db_session, make_user(db_session, OTHER_SUBJECT))
    mine = make_application(db_session, operator)

    assert error_of(put_photos(client, headers, others.id)) == (404, "OWNER_APPLICATION_NOT_FOUND")
    response = put_photos(client, headers, mine.id)
    assert response.status_code == 200
    assert response.json()["businessVerification"]["result"] == "unavailable"


def test_needs_a_users_row_and_a_token(client, db_session, storage, supabase):
    other = make_application(db_session, make_user(db_session, OTHER_SUBJECT))
    headers = {"Authorization": f"Bearer {supabase.token(sub=SUBJECT)}"}

    assert error_of(put_photos(client, headers, other.id)) == (404, "OWNER_APPLICATION_NOT_FOUND")
    assert error_of(put_photos(client, {}, other.id)) == (401, "UNAUTHENTICATED")


def test_images_are_required(client, storage, auth, pending):
    response = client.put(f"/api/owner-applications/{pending.id}/menu-photos", headers=auth)

    assert error_of(response) == (422, "VALIDATION_FAILED")
    assert [(e["path"], e["code"]) for e in response.json()["error"]["fieldErrors"]] == [("images", "MISSING")]


def test_the_application_is_checked_before_the_photos(client, db_session, storage, auth):
    images = [(f"p{n}.jpg", JPEG, "image/jpeg") for n in range(menu_import_upload.MAX_IMAGES + 1)]

    assert error_of(put_photos(client, auth, MISSING_ID, images=images)) == (404, "OWNER_APPLICATION_NOT_FOUND")


def test_upload_limits_follow_menu_imports(client, db_session, storage, auth, pending, monkeypatch):
    old = make_application_menu_image(db_session, pending)
    too_many = [(f"p{n}.jpg", JPEG, "image/jpeg") for n in range(menu_import_upload.MAX_IMAGES + 1)]

    response = put_photos(client, auth, pending.id, images=too_many)
    assert error_of(response) == (413, "UPLOAD_TOO_LARGE")
    assert response.json()["error"]["details"] == {
        "maxImages": 15,
        "maxImageBytes": 10 * 1024 * 1024,
        "maxTotalBytes": 60 * 1024 * 1024,
    }

    with monkeypatch.context() as patch:
        patch.setattr(menu_import_upload, "MAX_TOTAL_BYTES", len(JPEG) + 1)
        assert error_of(put_photos(client, auth, pending.id)) == (413, "UPLOAD_TOO_LARGE")

    response = put_photos(client, auth, pending.id, images=[("a.jpg", JPEG, "image/jpeg"), ("b.gif", GIF, "image/gif")])
    assert error_of(response) == (415, "UNSUPPORTED_IMAGE_TYPE")
    assert response.json()["error"]["details"]["imageOrder"] == 2

    assert [row.storage_key for row in photo_rows(db_session, pending)] == [old.storage_key]
    assert stored_files(storage) == set()


def test_fifteen_photos_are_accepted(client, db_session, storage, auth, pending):
    images = [(f"p{n}.jpg", JPEG, "image/jpeg") for n in range(15)]

    response = put_photos(client, auth, pending.id, images=images)

    assert response.status_code == 200
    assert [photo["imageOrder"] for photo in response.json()["menuPhotos"]] == list(range(1, 16))


def test_a_long_file_name_is_cut_to_fit(client, db_session, storage, auth, pending):
    long_name = "메" * 300 + ".jpg"

    response = put_photos(client, auth, pending.id, images=[(long_name, JPEG, "image/jpeg")])

    assert response.status_code == 200, response.text
    [row] = photo_rows(db_session, pending)
    assert row.original_filename == long_name[:255]


# ---- photos in the other application responses ----


def test_my_list_and_the_detail_show_the_photos(client, db_session, storage, auth, applicant, pending):
    make_application_menu_image(db_session, pending, image_order=2)
    make_application_menu_image(db_session, pending, image_order=1)
    without = make_application(db_session, applicant, make_bar(db_session))

    items = client.get("/api/me/owner-applications", headers=auth).json()["items"]
    listed = {item["applicationId"]: item for item in items}
    detail = client.get(f"/api/owner-applications/{pending.id}", headers=auth).json()

    assert [photo["imageOrder"] for photo in listed[str(pending.id)]["menuPhotos"]] == [1, 2]
    assert listed[str(without.id)]["menuPhotos"] == []
    assert detail["menuPhotos"] == listed[str(pending.id)]["menuPhotos"]


def test_an_operator_sees_the_photos(client, db_session, storage, token_for, pending):
    make_application_menu_image(db_session, pending)
    operator = {"Authorization": f"Bearer {token_for('operator')}"}

    response = client.get(f"/api/owner-applications/{pending.id}", headers=operator)

    assert len(response.json()["menuPhotos"]) == 1


# ---- cancel (3.11.5) deletes the photos ----


def test_canceling_deletes_the_photos(client, db_session, storage, auth, pending):
    put_photos(client, auth, pending.id)

    response = client.post(f"/api/owner-applications/{pending.id}/cancel", headers=auth)

    assert response.status_code == 200
    assert response.json()["menuPhotos"] == []
    assert photo_rows(db_session, pending) == []
    assert stored_files(storage) == set()


# ---- viewing URLs ----


class SignedStorage:
    def url(self, key: str):
        return f"https://bucket.example.com/{key}?signature=abc", datetime(2026, 10, 31, 9, tzinfo=timezone.utc)


def test_signed_urls_are_kept_as_they_are():
    links = ImageLinks(SignedStorage(), "http://testserver/")

    assert links.url("a.jpg") == (
        "https://bucket.example.com/a.jpg?signature=abc",
        datetime(2026, 10, 31, 9, tzinfo=timezone.utc),
    )
