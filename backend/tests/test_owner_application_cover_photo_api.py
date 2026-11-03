"""The cover photo of a new_bar owner application (API spec 3.11.17): upload and removal, the photo in
the application responses (3.11.1), its deletion on cancel and rejection (3.11.5, 3.11.8), and its move
to the new bar's photos on approval (3.11.7).

How a photo is checked and re-encoded is in test_bar_photo_image.py; who may call the routes is in
test_route_permissions.py.
"""

import hashlib
import io

import pytest
from PIL import Image
from sqlalchemy import select, update

from app.models import BarOwnerApplication, BarPhoto, OwnerApplicationStatus, OwnerApplicationType, UserType
from tests.factories import make_application, make_bar, make_user, set_cover_photo
from tests.sql_support import recorded_statements
from tests.test_bar_photos_api import FailingStorage, jpeg

SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"
OTHER_SUBJECT = "5d1c2b3a-0000-4000-8000-000000000002"
OPERATOR_SUBJECT = "operator-subject"
MISSING_ID = "99999999-9999-4999-8999-999999999999"
NEW_BAR = {"name": "신림 몰트 하우스", "address": "서울특별시 관악구 신림로 2 3층", "latitude": 37.48, "longitude": 126.93}


class HookedStorage(FailingStorage):
    """Real storage that runs `on_save` before each save."""

    def __init__(self, storage, on_save) -> None:
        super().__init__(storage)
        self.on_save = on_save

    def save(self, key, data, content_type):
        self.on_save(key)
        super().save(key, data, content_type)


@pytest.fixture
def use_storage():
    from app.api.deps import get_image_storage
    from app.main import app

    def use(storage):
        app.dependency_overrides[get_image_storage] = lambda: storage

    return use


@pytest.fixture
def applicant(db_session):
    return make_user(db_session, SUBJECT)


@pytest.fixture
def auth(supabase, applicant):
    return {"Authorization": f"Bearer {supabase.token(sub=SUBJECT)}"}


@pytest.fixture
def operator(supabase, db_session):
    make_user(db_session, OPERATOR_SUBJECT, user_type=UserType.OPERATOR)
    return {"Authorization": f"Bearer {supabase.token(sub=OPERATOR_SUBJECT)}"}


@pytest.fixture
def pending(db_session, applicant):
    return make_application(db_session, applicant)


def put_cover(client, headers, application_id, data=None, content_type="image/jpeg"):
    return client.put(
        f"/api/owner-applications/{application_id}/cover-photo",
        headers=headers,
        files=[("image", ("cover.jpg", jpeg() if data is None else data, content_type))],
    )


def delete_cover(client, headers, application_id):
    return client.delete(f"/api/owner-applications/{application_id}/cover-photo", headers=headers)


def error_of(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def cover_of(db_session, application) -> tuple[str | None, str | None, str | None]:
    db_session.refresh(application)
    return (
        application.cover_photo_storage_key,
        application.cover_photo_thumbnail_storage_key,
        application.cover_photo_sha256,
    )


def stored_files(storage) -> set[str]:
    return {path.relative_to(storage.root).as_posix() for path in storage.root.rglob("*") if path.is_file()}


def stored_cover(db_session, storage, application) -> list[str]:
    """Give `application` a cover photo with both files stored; returns the keys."""
    set_cover_photo(db_session, application)
    keys = [application.cover_photo_storage_key, application.cover_photo_thumbnail_storage_key]
    for key in keys:
        storage.save(key, jpeg(), "image/jpeg")
    return keys


# ---- upload ----


def test_stores_the_re_encoded_photo_and_its_thumbnail(client, db_session, image_storage, auth, pending):
    out = io.BytesIO()
    Image.new("RGBA", (1000, 500), (0, 0, 255, 0)).save(out, format="PNG")
    upload = out.getvalue()

    response = put_cover(client, auth, pending.id, upload, "image/png")

    assert response.status_code == 200, response.text
    image_key, thumbnail_key, sha = cover_of(db_session, pending)
    assert image_key.startswith(f"owner-applications/{pending.id}/cover/") and image_key.endswith(".jpg")
    assert thumbnail_key == image_key.removesuffix(".jpg") + "-thumb.jpg"
    assert sha == hashlib.sha256(upload).hexdigest()
    assert stored_files(image_storage) == {image_key, thumbnail_key}
    with Image.open(io.BytesIO(image_storage.read(image_key))) as image:
        assert (image.format, image.size, image.getpixel((0, 0))) == ("JPEG", (1000, 500), (255, 255, 255))
    with Image.open(io.BytesIO(image_storage.read(thumbnail_key))) as thumbnail:
        assert thumbnail.size == (480, 240)
    assert response.json()["coverPhoto"] == {
        "imageUrl": f"http://testserver/media/{image_key}",
        "thumbnailUrl": f"http://testserver/media/{thumbnail_key}",
        "imageUrlExpiresAt": None,
    }


def test_an_upload_replaces_the_photo(client, db_session, image_storage, auth, pending):
    old = stored_cover(db_session, image_storage, pending)

    response = put_cover(client, auth, pending.id, jpeg("green"))

    assert response.status_code == 200
    image_key, thumbnail_key, sha = cover_of(db_session, pending)
    assert sha == hashlib.sha256(jpeg("green")).hexdigest()
    assert stored_files(image_storage) == {image_key, thumbnail_key}
    assert image_key not in old


def test_resending_the_same_photo_gives_the_same_result(client, db_session, image_storage, auth, pending):
    first = put_cover(client, auth, pending.id).json()["coverPhoto"]
    second = put_cover(client, auth, pending.id).json()["coverPhoto"]

    assert cover_of(db_session, pending)[2] == hashlib.sha256(jpeg()).hexdigest()
    assert len(stored_files(image_storage)) == 2
    assert first is not None and second is not None


def test_locks_the_application_before_storing_the_keys(client, db_session, image_storage, auth, pending):
    with recorded_statements(db_session) as statements:
        assert put_cover(client, auth, pending.id).status_code == 200

    lock = next(i for i, sql in enumerate(statements) if "FROM bar_owner_applications" in sql and "FOR UPDATE" in sql)
    write = next(i for i, sql in enumerate(statements) if sql.startswith("UPDATE bar_owner_applications"))
    assert lock < write


def test_an_application_finished_while_storing_keeps_its_photo(
    client, db_session, image_storage, auth, pending, use_storage
):
    old = stored_cover(db_session, image_storage, pending)

    def cancel_meanwhile(key):
        # Another request cancels the application while the photo is being stored; a real cancel
        # would also clear the photo, which the CHECK constraint makes it do.
        db_session.execute(
            update(BarOwnerApplication)
            .where(BarOwnerApplication.id == pending.id)
            .values(
                status=OwnerApplicationStatus.CANCELED,
                cover_photo_storage_key=None,
                cover_photo_thumbnail_storage_key=None,
                cover_photo_sha256=None,
            )
        )

    use_storage(HookedStorage(image_storage, cancel_meanwhile))
    response = put_cover(client, auth, pending.id)

    assert error_of(response) == (409, "INVALID_APPLICATION_STATE")
    assert response.json()["error"]["details"] == {"status": "canceled"}
    assert stored_files(image_storage) == set(old)


@pytest.mark.parametrize("fail_on_save", [1, 2])
def test_a_storage_failure_changes_nothing(client, db_session, image_storage, auth, pending, use_storage, fail_on_save):
    old = stored_cover(db_session, image_storage, pending)
    use_storage(FailingStorage(image_storage, fail_on_save=fail_on_save, write_before_failing=True))

    with pytest.raises(OSError, match="disk full"):
        put_cover(client, auth, pending.id)

    assert cover_of(db_session, pending)[0] == old[0]
    assert stored_files(image_storage) == set(old)


def test_a_failed_delete_of_the_replaced_files_does_not_fail_the_upload(
    client, db_session, image_storage, auth, pending, use_storage
):
    old = stored_cover(db_session, image_storage, pending)
    use_storage(FailingStorage(image_storage, fail_deletes=True))

    response = put_cover(client, auth, pending.id, jpeg("green"))

    assert response.status_code == 200
    assert cover_of(db_session, pending)[0] not in old


# ---- check order and errors ----


def test_an_image_is_required_and_only_one(client, image_storage, auth, pending):
    missing = client.put(f"/api/owner-applications/{pending.id}/cover-photo", headers=auth)
    two = client.put(
        f"/api/owner-applications/{MISSING_ID}/cover-photo",
        headers=auth,
        files=[("image", ("a.jpg", jpeg(), "image/jpeg")), ("image", ("b.jpg", jpeg("blue"), "image/jpeg"))],
    )

    assert [(e["path"], e["code"]) for e in missing.json()["error"]["fieldErrors"]] == [("image", "MISSING")]
    # Before the application, which does not exist.
    assert [(e["path"], e["code"]) for e in two.json()["error"]["fieldErrors"]] == [("image", "TOO_LONG")]


@pytest.mark.parametrize("target", ["someone else's", "missing", "malformed"])
def test_other_applications_look_missing(client, db_session, image_storage, auth, target):
    other = make_application(db_session, make_user(db_session, OTHER_SUBJECT))
    application_id = {"someone else's": str(other.id), "missing": MISSING_ID, "malformed": "x"}[target]

    # A photo that would fail its own checks: the application comes first.
    assert error_of(put_cover(client, auth, application_id, b"GIF89a", "image/gif")) == (
        404,
        "OWNER_APPLICATION_NOT_FOUND",
    )
    assert error_of(delete_cover(client, auth, application_id)) == (404, "OWNER_APPLICATION_NOT_FOUND")
    assert cover_of(db_session, other) == (None, None, None)


def test_needs_a_token(client, image_storage, pending):
    assert error_of(put_cover(client, {}, pending.id)) == (401, "UNAUTHENTICATED")
    assert error_of(delete_cover(client, {}, pending.id)) == (401, "UNAUTHENTICATED")


def test_an_existing_bar_application_takes_no_cover_photo(client, db_session, image_storage, auth, applicant):
    existing = make_application(db_session, applicant, make_bar(db_session))

    for response in (put_cover(client, auth, existing.id, b"GIF89a", "image/gif"), delete_cover(client, auth, existing.id)):
        assert error_of(response) == (409, "INVALID_APPLICATION_TYPE")
        assert response.json()["error"]["details"] == {"applicationType": "existing_bar"}
    assert stored_files(image_storage) == set()


@pytest.mark.parametrize(
    "status", [OwnerApplicationStatus.CANCELED, OwnerApplicationStatus.REJECTED, OwnerApplicationStatus.APPROVED]
)
def test_only_pending_applications_change_their_photo(client, db_session, image_storage, auth, applicant, status):
    reviewer = make_user(db_session, OPERATOR_SUBJECT, user_type=UserType.OPERATOR)
    finished = make_application(
        db_session,
        applicant,
        make_bar(db_session) if status == OwnerApplicationStatus.APPROVED else None,
        application_type=OwnerApplicationType.NEW_BAR,
        status=status,
        reviewer=reviewer,
    )

    for response in (put_cover(client, auth, finished.id, b"GIF89a", "image/gif"), delete_cover(client, auth, finished.id)):
        assert error_of(response) == (409, "INVALID_APPLICATION_STATE")
        assert response.json()["error"]["details"] == {"status": status.value}
    assert stored_files(image_storage) == set()


@pytest.mark.parametrize(
    ("data", "content_type", "expected"),
    [
        pytest.param(b"GIF89a" + b"gif-body", "image/gif", (415, "UNSUPPORTED_IMAGE_TYPE"), id="GIF"),
        pytest.param(jpeg() + b"\0" * (2 * 1024 * 1024), "image/jpeg", (413, "UPLOAD_TOO_LARGE"), id="over 2 MB"),
        pytest.param(jpeg(size=(2049, 8)), "image/jpeg", (422, "VALIDATION_FAILED"), id="over 2048 px"),
    ],
)
def test_a_rejected_photo_keeps_the_old_one(client, db_session, image_storage, auth, pending, data, content_type, expected):
    old = stored_cover(db_session, image_storage, pending)

    response = put_cover(client, auth, pending.id, data, content_type)

    assert error_of(response) == expected
    if expected[0] == 413:
        assert response.json()["error"]["details"] == {"maxImageBytes": 2 * 1024 * 1024}
    if expected[0] == 422:
        assert response.json()["error"]["fieldErrors"][0]["code"] == "IMAGE_DIMENSIONS_TOO_LARGE"
    assert cover_of(db_session, pending)[0] == old[0]
    assert stored_files(image_storage) == set(old)


def test_an_operator_changes_only_their_own(client, db_session, image_storage, supabase):
    operator = make_user(db_session, SUBJECT, user_type=UserType.OPERATOR)
    headers = {"Authorization": f"Bearer {supabase.token(sub=SUBJECT)}"}
    others = make_application(db_session, make_user(db_session, OTHER_SUBJECT))
    mine = make_application(db_session, operator)

    assert error_of(put_cover(client, headers, others.id)) == (404, "OWNER_APPLICATION_NOT_FOUND")
    response = put_cover(client, headers, mine.id)
    assert response.status_code == 200
    assert response.json()["businessVerification"]["result"] == "unavailable"


# ---- removal ----


def test_deleting_removes_the_photo_and_its_files(client, db_session, image_storage, auth, pending):
    stored_cover(db_session, image_storage, pending)

    response = delete_cover(client, auth, pending.id)

    assert response.status_code == 200
    assert response.json()["coverPhoto"] is None
    assert cover_of(db_session, pending) == (None, None, None)
    assert stored_files(image_storage) == set()
    # Nothing left to delete is fine too.
    assert delete_cover(client, auth, pending.id).status_code == 200


def test_a_failed_file_delete_still_removes_the_photo(client, db_session, image_storage, auth, pending, use_storage):
    old = stored_cover(db_session, image_storage, pending)
    use_storage(FailingStorage(image_storage, fail_deletes=True))

    assert delete_cover(client, auth, pending.id).status_code == 200
    assert cover_of(db_session, pending) == (None, None, None)
    assert stored_files(image_storage) == set(old)


# ---- the photo in the other application APIs ----


def test_the_applicant_and_operators_see_the_photo(client, db_session, image_storage, auth, operator, applicant, pending):
    image_key, thumbnail_key = stored_cover(db_session, image_storage, pending)
    without = make_application(db_session, applicant, make_bar(db_session))
    expected = {
        "imageUrl": f"http://testserver/media/{image_key}",
        "thumbnailUrl": f"http://testserver/media/{thumbnail_key}",
        "imageUrlExpiresAt": None,
    }

    listed = {item["applicationId"]: item for item in client.get("/api/me/owner-applications", headers=auth).json()["items"]}
    operator_list = client.get("/api/owner-applications", headers=operator).json()["items"]

    assert listed[str(pending.id)]["coverPhoto"] == expected
    assert listed[str(without.id)]["coverPhoto"] is None
    assert client.get(f"/api/owner-applications/{pending.id}", headers=operator).json()["coverPhoto"] == expected
    assert {item["applicationId"]: item["coverPhoto"] for item in operator_list}[str(pending.id)] == expected


def test_canceling_deletes_the_photo(client, db_session, image_storage, auth, pending):
    stored_cover(db_session, image_storage, pending)

    response = client.post(f"/api/owner-applications/{pending.id}/cancel", headers=auth)

    assert response.status_code == 200
    assert response.json()["coverPhoto"] is None
    assert cover_of(db_session, pending) == (None, None, None)
    assert stored_files(image_storage) == set()


def test_rejecting_deletes_the_photo(client, db_session, image_storage, operator, pending):
    stored_cover(db_session, image_storage, pending)

    response = client.post(
        f"/api/owner-applications/{pending.id}/reject", headers=operator, json={"reason": "확인할 수 없습니다."}
    )

    assert response.status_code == 200
    assert response.json()["coverPhoto"] is None
    assert cover_of(db_session, pending) == (None, None, None)
    assert stored_files(image_storage) == set()


def test_approval_makes_the_photo_the_new_bar_cover(client, db_session, image_storage, operator, applicant, pending):
    image_key, thumbnail_key = stored_cover(db_session, image_storage, pending)

    response = client.post(f"/api/owner-applications/{pending.id}/approve", headers=operator, json={"bar": NEW_BAR})

    assert response.status_code == 200, response.text
    assert response.json()["coverPhoto"] is None
    assert cover_of(db_session, pending) == (None, None, None)
    photo = db_session.scalar(select(BarPhoto).where(BarPhoto.bar_id == pending.bar_id))
    assert (photo.storage_key, photo.thumbnail_storage_key, photo.content_sha256, photo.sort_order) == (
        image_key,
        thumbnail_key,
        "c" * 64,
        1,
    )
    assert photo.uploaded_by_user_id == applicant.id
    # The files stay: they are the bar photo's now, served at its public URL.
    assert stored_files(image_storage) == {image_key, thumbnail_key}
    menu = client.get(f"/api/bars/{pending.bar_id}/menu").json()
    assert [p["photoId"] for p in menu["photos"]] == [str(photo.id)]
    served = client.get(f"/api/bar-photos/{photo.id}/thumbnail")
    assert served.status_code == 200 and served.content == image_storage.read(thumbnail_key)


def test_approval_without_a_photo_leaves_the_bar_without_photos(client, db_session, image_storage, operator, pending):
    response = client.post(f"/api/owner-applications/{pending.id}/approve", headers=operator, json={"bar": NEW_BAR})

    assert response.status_code == 200
    db_session.refresh(pending)
    assert db_session.scalar(select(BarPhoto).where(BarPhoto.bar_id == pending.bar_id)) is None
