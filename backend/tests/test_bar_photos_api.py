"""The bar photo APIs (API spec 3.16): add, delete, reorder, and the public photo files.

Who may call them is in test_route_permissions.py; how a photo is checked and re-encoded is in
test_bar_photo_image.py. The test session never commits, so the deferred position constraint is
checked by hand (`positions`).
"""

import io
import logging
from datetime import datetime, timezone
from uuid import UUID

import pytest
from PIL import Image
from sqlalchemy import select, text

from app.core.errors import ApiError
from app.core.security import Principal
from app.models import BarOwner, BarPhoto, BarStatus, UserType
from app.services.bar_photos import add_photo
from app.services.menu_import_upload import ImageUpload
from tests.factories import make_bar, make_bar_photo, make_owner, make_user
from tests.sql_support import recorded_statements

OWNER_SUBJECT = "owner-subject"
MISSING_ID = "99999999-9999-4999-8999-999999999999"
BASE = "http://testserver/api/bar-photos"


def jpeg(color="red", size=(640, 320)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="JPEG")
    return out.getvalue()


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def bar(db_session):
    return make_bar(db_session, "관악 위스키 바")


@pytest.fixture
def owner_user(db_session, bar):
    user = make_user(db_session, OWNER_SUBJECT)
    make_owner(db_session, user, bar, make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR))
    return user


@pytest.fixture
def owner(supabase, owner_user):
    return {"Authorization": f"Bearer {supabase.token(sub=OWNER_SUBJECT)}"}


def add(client, headers, bar_id, data=None, content_type="image/jpeg"):
    files = [("image", ("photo.jpg", data if data is not None else jpeg(), content_type))]
    return client.post(f"/api/bars/{bar_id}/photos", headers=headers, files=files)


def added(client, headers, bar, *colors) -> list[str]:
    """Add one photo per color through the API; their ids in display order."""
    for color in colors:
        response = add(client, headers, bar.id, jpeg(color))
        assert response.status_code == 201, response.text
    return [photo["photoId"] for photo in response.json()["photos"]]


def delete(client, headers, bar_id, photo_id):
    return client.delete(f"/api/bars/{bar_id}/photos/{photo_id}", headers=headers)


def reorder(client, headers, bar_id, photo_ids):
    return client.put(f"/api/bars/{bar_id}/photos/order", headers=headers, json={"photoIds": photo_ids})


def positions(db_session, bar) -> list[tuple[str, int]]:
    """(photo id, position) of the bar in display order, after the check a commit would run."""
    db_session.flush()
    db_session.execute(text("SET CONSTRAINTS uq_bar_photos_sort_order IMMEDIATE"))
    db_session.expire_all()
    rows = db_session.execute(
        select(BarPhoto.id, BarPhoto.sort_order).where(BarPhoto.bar_id == bar.id).order_by(BarPhoto.sort_order)
    )
    return [(str(photo_id), order) for photo_id, order in rows]


def stored_files(image_storage) -> set[str]:
    return {str(path.relative_to(image_storage.root)) for path in image_storage.root.rglob("*") if path.is_file()}


def response_photos(*photo_ids) -> list[dict]:
    return [
        {"photoId": photo_id, "imageUrl": f"{BASE}/{photo_id}", "thumbnailUrl": f"{BASE}/{photo_id}/thumbnail"}
        for photo_id in photo_ids
    ]


def error(response) -> tuple[int, str, dict | None]:
    body = response.json()["error"]
    return response.status_code, body["code"], body["details"]


def field_errors(response) -> list[tuple[str, str]]:
    assert response.status_code == 422, response.text
    return [(e["path"], e["code"]) for e in response.json()["error"]["fieldErrors"]]


class FailingStorage:
    """Delegates to real storage but fails on the given save call, or on every delete."""

    def __init__(self, storage, *, fail_on_save=None, fail_deletes=False):
        self.storage, self.fail_on_save, self.fail_deletes, self.saves = storage, fail_on_save, fail_deletes, 0

    def __getattr__(self, name):
        return getattr(self.storage, name)

    def save(self, key, data, content_type):
        self.saves += 1
        if self.saves == self.fail_on_save:
            raise OSError("disk full")
        self.storage.save(key, data, content_type)

    def delete(self, key):
        if self.fail_deletes:
            raise OSError("bucket unreachable")
        self.storage.delete(key)


@pytest.fixture
def use_storage():
    from app.api.deps import get_image_storage
    from app.main import app

    def use(storage):
        app.dependency_overrides[get_image_storage] = lambda: storage

    return use


# ---- adding (3.16.2) ----


def test_adding_stores_the_re_encoded_photo_and_its_thumbnail(client, db_session, image_storage, operator, bar):
    upload = jpeg()

    response = add(client, operator, bar.id, upload)

    assert response.status_code == 201, response.text
    [photo] = db_session.scalars(select(BarPhoto).where(BarPhoto.bar_id == bar.id)).all()
    assert response.json() == {"photos": response_photos(str(photo.id))}
    assert photo.sort_order == 1
    assert photo.storage_key == f"bars/{bar.id}/photos/{photo.id}.jpg"
    assert photo.thumbnail_storage_key == f"bars/{bar.id}/photos/{photo.id}-thumb.jpg"
    # A temporary-login operator has no users row.
    assert photo.uploaded_by_user_id is None
    assert stored_files(image_storage) == {photo.storage_key, photo.thumbnail_storage_key}
    assert image_storage.read(photo.storage_key) != upload
    assert Image.open(io.BytesIO(image_storage.read(photo.storage_key))).size == (640, 320)
    assert Image.open(io.BytesIO(image_storage.read(photo.thumbnail_storage_key))).size == (480, 240)


def test_new_photos_go_last(client, db_session, image_storage, owner, bar):
    first, second, third = added(client, owner, bar, "red", "green", "blue")

    assert positions(db_session, bar) == [(first, 1), (second, 2), (third, 3)]


def test_the_owner_is_recorded_and_an_inactive_bar_takes_photos(
    client, db_session, image_storage, owner, owner_user, bar
):
    bar.status = BarStatus.INACTIVE
    db_session.flush()

    response = add(client, owner, bar.id)

    assert response.status_code == 201, response.text
    assert db_session.scalar(select(BarPhoto.uploaded_by_user_id)) == owner_user.id


def test_the_same_file_is_not_added_twice(client, db_session, image_storage, operator, bar):
    [photo_id] = added(client, operator, bar, "red")
    files = stored_files(image_storage)

    response = add(client, operator, bar.id, jpeg("red"))

    assert error(response) == (409, "PHOTO_EXISTS", {"photoId": photo_id})
    assert stored_files(image_storage) == files
    assert len(positions(db_session, bar)) == 1


def test_another_bar_may_have_the_same_file(client, db_session, image_storage, operator, bar):
    added(client, operator, bar, "red")

    assert add(client, operator, make_bar(db_session, "Other").id, jpeg("red")).status_code == 201


def test_a_bar_takes_at_most_15_photos(client, db_session, image_storage, operator, bar):
    for order in range(1, 16):
        make_bar_photo(db_session, bar, order)

    response = add(client, operator, bar.id)

    assert error(response) == (409, "PHOTO_LIMIT_REACHED", {"maxPhotos": 15})
    assert stored_files(image_storage) == set()


def test_resending_the_15th_photo_is_photo_exists_not_the_limit(client, db_session, image_storage, operator, bar):
    for order in range(1, 15):
        make_bar_photo(db_session, bar, order)
    [*_, last] = added(client, operator, bar, "red")

    assert error(add(client, operator, bar.id, jpeg("red"))) == (409, "PHOTO_EXISTS", {"photoId": last})


def test_a_missing_image_is_reported_before_the_bar(client, image_storage, operator):
    response = client.post(f"/api/bars/{MISSING_ID}/photos", headers=operator, data={"note": "x"})

    assert field_errors(response) == [("image", "MISSING")]


def test_two_images_are_rejected_before_the_bar(client, image_storage, operator):
    files = [("image", ("a.jpg", jpeg("red"), "image/jpeg")), ("image", ("b.jpg", jpeg("blue"), "image/jpeg"))]

    response = client.post(f"/api/bars/{MISSING_ID}/photos", headers=operator, files=files)

    assert field_errors(response) == [("image", "TOO_LONG")]


def test_the_bar_is_checked_before_the_photo(client, image_storage, operator):
    assert error(add(client, operator, MISSING_ID, b"not an image"))[:2] == (404, "BAR_NOT_FOUND")


@pytest.mark.parametrize(
    ("data", "content_type", "expected"),
    [
        pytest.param(b"GIF89a" + b"gif-body", "image/gif", (415, "UNSUPPORTED_IMAGE_TYPE"), id="GIF"),
        pytest.param(jpeg() + b"\0" * (2 * 1024 * 1024), "image/jpeg", (413, "UPLOAD_TOO_LARGE"), id="over 2 MB"),
        pytest.param(jpeg(size=(2049, 8)), "image/jpeg", (422, "VALIDATION_FAILED"), id="over 2048 px"),
    ],
)
def test_a_rejected_photo_stores_nothing(client, db_session, image_storage, operator, bar, data, content_type, expected):
    assert error(add(client, operator, bar.id, data, content_type))[:2] == expected
    assert stored_files(image_storage) == set()
    assert positions(db_session, bar) == []


def test_the_checks_under_the_lock_follow_it(client, db_session, image_storage, operator, bar):
    with recorded_statements(db_session) as statements:
        assert add(client, operator, bar.id).status_code == 201

    lock = next(i for i, sql in enumerate(statements) if "FOR UPDATE" in sql)
    assert "FROM bars" in statements[lock]
    duplicate = next(i for i, sql in enumerate(statements) if "bar_photos.content_sha256 =" in sql)
    insert = next(i for i, sql in enumerate(statements) if sql.startswith("INSERT INTO bar_photos"))
    assert lock < duplicate < insert


def test_an_owner_revoked_before_the_lock_is_forbidden(db_session, image_storage, bar, owner_user):
    """The route found the caller to be the owner; the check under the lock refuses a revocation since."""
    ownership = db_session.scalar(select(BarOwner).where(BarOwner.user_id == owner_user.id))
    ownership.revoked_at, ownership.revoked_by_user_id = datetime.now(timezone.utc), owner_user.id
    db_session.flush()
    caller = Principal(kind="supabase", subject=OWNER_SUBJECT, claims={})

    with pytest.raises(ApiError) as caught:
        add_photo(db_session, image_storage, caller, bar.id, ImageUpload("a.jpg", "image/jpeg", io.BytesIO(jpeg())), "")

    assert (caught.value.status_code, caught.value.code) == (403, "FORBIDDEN")
    assert stored_files(image_storage) == set()


def test_a_storage_failure_removes_the_stored_file(client, db_session, image_storage, operator, bar, use_storage):
    use_storage(FailingStorage(image_storage, fail_on_save=2))

    with pytest.raises(OSError, match="disk full"):
        add(client, operator, bar.id)

    assert stored_files(image_storage) == set()
    assert positions(db_session, bar) == []


def test_a_database_failure_removes_both_files(client, db_session, image_storage, operator, bar, monkeypatch):
    def fail():
        raise RuntimeError("connection lost")

    monkeypatch.setattr(db_session, "commit", fail)

    with pytest.raises(RuntimeError, match="connection lost"):
        add(client, operator, bar.id)

    assert stored_files(image_storage) == set()


def test_a_cleanup_failure_keeps_the_original_error(client, image_storage, operator, bar, use_storage, caplog):
    use_storage(FailingStorage(image_storage, fail_on_save=2, fail_deletes=True))

    with pytest.raises(OSError, match="disk full"):
        add(client, operator, bar.id)

    assert f"Could not delete bars/{bar.id}/photos/" in caplog.text


# ---- deleting (3.16.3) ----


def test_deleting_moves_the_later_photos_forward_and_removes_the_files(
    client, db_session, image_storage, operator, bar
):
    first, second, third = added(client, operator, bar, "red", "green", "blue")
    deleted = db_session.get(BarPhoto, UUID(second))
    keys = {deleted.storage_key, deleted.thumbnail_storage_key}

    response = delete(client, operator, bar.id, second)

    assert response.status_code == 200, response.text
    assert response.json() == {"photos": response_photos(first, third)}
    assert positions(db_session, bar) == [(first, 1), (third, 2)]
    assert not keys & stored_files(image_storage)
    assert len(stored_files(image_storage)) == 4


def test_deleting_the_cover_makes_the_next_photo_the_cover(client, db_session, image_storage, owner, bar):
    first, second = added(client, owner, bar, "red", "green")

    assert delete(client, owner, bar.id, first).json() == {"photos": response_photos(second)}
    assert positions(db_session, bar) == [(second, 1)]


def test_the_last_photo_can_be_deleted(client, db_session, image_storage, operator, bar):
    [photo_id] = added(client, operator, bar, "red")

    assert delete(client, operator, bar.id, photo_id).json() == {"photos": []}
    assert stored_files(image_storage) == set()


def test_a_deleted_photo_can_be_added_again(client, db_session, image_storage, operator, bar):
    [photo_id] = added(client, operator, bar, "red")
    delete(client, operator, bar.id, photo_id)

    assert add(client, operator, bar.id, jpeg("red")).status_code == 201


@pytest.mark.parametrize("photo_id", ["already deleted", "of another bar", "missing", "not-a-uuid"])
def test_deleting_a_photo_the_bar_does_not_have_is_not_found(client, db_session, image_storage, operator, bar, photo_id):
    [kept] = added(client, operator, bar, "red")
    if photo_id == "already deleted":
        photo_id = added(client, operator, bar, "green")[-1]
        delete(client, operator, bar.id, photo_id)
    elif photo_id == "of another bar":
        photo_id = str(make_bar_photo(db_session, make_bar(db_session, "Other")).id)
    elif photo_id == "missing":
        photo_id = MISSING_ID

    assert error(delete(client, operator, bar.id, photo_id)) == (404, "PHOTO_NOT_FOUND", {"photoId": photo_id})
    assert positions(db_session, bar) == [(kept, 1)]


def test_a_file_that_cannot_be_deleted_is_only_logged(client, db_session, image_storage, operator, bar, use_storage, caplog):
    [photo_id] = added(client, operator, bar, "red")
    use_storage(FailingStorage(image_storage, fail_deletes=True))

    with caplog.at_level(logging.WARNING):
        response = delete(client, operator, bar.id, photo_id)

    assert response.json() == {"photos": []}
    assert positions(db_session, bar) == []
    assert f"Could not delete bars/{bar.id}/photos/{photo_id}.jpg of a deleted photo" in caplog.text


# ---- reordering (3.16.4) ----


def test_reordering_sets_the_positions_and_the_cover(client, db_session, image_storage, owner, bar):
    first, second, third = added(client, owner, bar, "red", "green", "blue")

    response = reorder(client, owner, bar.id, [third, first, second])

    assert response.status_code == 200, response.text
    assert response.json() == {"photos": response_photos(third, first, second)}
    assert positions(db_session, bar) == [(third, 1), (first, 2), (second, 3)]


def test_sending_the_same_order_again_gives_the_same_result(client, db_session, image_storage, operator, bar):
    first, second = added(client, operator, bar, "red", "green")

    responses = [reorder(client, operator, bar.id, [second, first]) for _ in range(2)]

    assert [r.json() for r in responses] == [{"photos": response_photos(second, first)}] * 2
    assert positions(db_session, bar) == [(second, 1), (first, 2)]


def test_a_bar_without_photos_takes_an_empty_order(client, operator, bar):
    assert reorder(client, operator, bar.id, []).json() == {"photos": []}


@pytest.mark.parametrize("change", ["one left out", "one unknown", "one more"])
def test_ids_that_are_not_the_bars_photos_are_outdated(client, db_session, image_storage, operator, bar, change):
    first, second = added(client, operator, bar, "red", "green")
    photo_ids = {
        "one left out": [second],
        "one unknown": [second, MISSING_ID],
        "one more": [second, first, MISSING_ID],
    }[change]

    response = reorder(client, operator, bar.id, photo_ids)

    assert error(response) == (409, "PHOTOS_OUTDATED", {"photos": response_photos(first, second)})
    assert positions(db_session, bar) == [(first, 1), (second, 2)]


def test_a_photo_sent_twice_is_rejected_before_the_bar(client, operator):
    response = reorder(client, operator, MISSING_ID, [MISSING_ID, MISSING_ID])

    assert field_errors(response) == [("photoIds[1]", "DUPLICATE_ITEM")]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param({}, [("photoIds", "MISSING")], id="missing"),
        pytest.param({"photoIds": ["not-a-uuid"]}, [("photoIds[0]", "UUID_PARSING")], id="not a UUID"),
        pytest.param({"photoIds": [], "cover": MISSING_ID}, [("cover", "EXTRA_FORBIDDEN")], id="extra field"),
    ],
)
def test_a_malformed_order_is_rejected(client, operator, bar, body, expected):
    response = client.put(f"/api/bars/{bar.id}/photos/order", headers=operator, json=body)

    assert field_errors(response) == expected


# ---- the photo files (3.16.5) ----


@pytest.mark.parametrize("suffix", ["", "/thumbnail"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-token"}], ids=["guest", "invalid token"])
def test_the_files_are_public_jpegs_cached_for_a_day(
    client, db_session, image_storage, operator, bar, suffix, headers
):
    [photo_id] = added(client, operator, bar, "red")
    photo = db_session.get(BarPhoto, UUID(photo_id))
    key = photo.thumbnail_storage_key if suffix else photo.storage_key

    response = client.get(f"/api/bar-photos/{photo_id}{suffix}", headers=headers)

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/jpeg"
    assert response.headers["Cache-Control"] == "public, max-age=86400"
    assert response.content == image_storage.read(key)


def test_the_urls_in_responses_open_the_files(client, image_storage, operator, bar):
    [photo] = add(client, operator, bar.id).json()["photos"]

    for url in (photo["imageUrl"], photo["thumbnailUrl"]):
        assert client.get(url).status_code == 200


def test_photos_of_an_inactive_bar_are_served(client, db_session, image_storage, operator, bar):
    [photo_id] = added(client, operator, bar, "red")
    bar.status = BarStatus.INACTIVE
    db_session.flush()

    assert client.get(f"/api/bar-photos/{photo_id}").status_code == 200


@pytest.mark.parametrize("suffix", ["", "/thumbnail"])
def test_a_deleted_photo_is_not_found_at_once(client, image_storage, operator, bar, use_storage, suffix):
    [photo_id] = added(client, operator, bar, "red")
    # Even while its files could not be removed.
    use_storage(FailingStorage(image_storage, fail_deletes=True))
    delete(client, operator, bar.id, photo_id)

    response = client.get(f"/api/bar-photos/{photo_id}{suffix}")

    assert error(response) == (404, "PHOTO_NOT_FOUND", {"photoId": photo_id})
    assert "Cache-Control" not in response.headers


@pytest.mark.parametrize("photo_id", [MISSING_ID, "not-a-uuid"])
def test_an_unknown_photo_is_not_found(client, photo_id):
    assert error(client.get(f"/api/bar-photos/{photo_id}/thumbnail")) == (
        404,
        "PHOTO_NOT_FOUND",
        {"photoId": photo_id},
    )


def test_a_photo_without_its_file_is_not_found(client, db_session, image_storage, bar, caplog):
    photo = make_bar_photo(db_session, bar)

    with caplog.at_level(logging.WARNING):
        response = client.get(f"/api/bar-photos/{photo.id}")

    assert error(response)[:2] == (404, "PHOTO_NOT_FOUND")
    assert f"Bar photo {photo.id} has no file at {photo.storage_key}" in caplog.text
