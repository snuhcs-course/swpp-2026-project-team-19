import pytest
from fastapi.testclient import TestClient

from app.adapters.storage import LocalImageStorage
from app.api.deps import get_image_storage
from app.main import app

KEY = "menus/bar-1/import-1/page-1.jpg"


@pytest.fixture
def storage(tmp_path):
    return LocalImageStorage(tmp_path)


def test_save_read_delete_round_trip(storage, tmp_path):
    storage.save(KEY, b"jpeg-bytes", "image/jpeg")

    assert (tmp_path / KEY).read_bytes() == b"jpeg-bytes"
    assert storage.read(KEY) == b"jpeg-bytes"
    storage.delete(KEY)
    with pytest.raises(FileNotFoundError):
        storage.read(KEY)


def test_deleting_a_missing_key_does_nothing(storage):
    storage.delete(KEY)


@pytest.mark.parametrize("key", ["", "/etc/passwd", "../outside.jpg", "menus/../../outside.jpg", "menus\\x.jpg"])
def test_keys_cannot_leave_the_storage_root(storage, key):
    with pytest.raises(ValueError):
        storage.save(key, b"x", "image/jpeg")


def test_url_is_a_media_path_without_expiry(storage):
    assert storage.url(KEY) == (f"/media/{KEY}", None)


@pytest.fixture
def media_client(storage):
    app.dependency_overrides[get_image_storage] = lambda: storage
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_image_storage, None)


def test_media_route_serves_stored_files(storage, media_client):
    storage.save(KEY, b"jpeg-bytes", "image/jpeg")

    response = media_client.get(f"/media/{KEY}")

    assert response.status_code == 200
    assert response.content == b"jpeg-bytes"
    assert response.headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize("path", [f"/media/{KEY}", "/media/..%2F..%2Fetc%2Fpasswd"])
def test_media_route_returns_404_for_missing_or_invalid_keys(media_client, path):
    response = media_client.get(path)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_media_route_is_not_in_the_api_document():
    assert not any(path.startswith("/media") for path in app.openapi()["paths"])
