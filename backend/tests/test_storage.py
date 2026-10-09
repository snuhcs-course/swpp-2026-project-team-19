# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #11, #16). Reviewed by Haeul Yang.
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app.adapters.storage import LocalImageStorage, S3ImageStorage
from app.api.deps import get_image_storage, s3_client
from app.main import app
from tests.fake_s3 import FakeS3Client

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


# ---- S3 ----


@pytest.fixture
def s3():
    return FakeS3Client()


def test_s3_save_read_delete(s3):
    storage = S3ImageStorage(s3, "menu-photos")

    storage.save(KEY, b"jpeg-bytes", "image/jpeg")

    assert s3.objects[("menu-photos", KEY)] == (b"jpeg-bytes", "image/jpeg")
    assert storage.read(KEY) == b"jpeg-bytes"
    storage.delete(KEY)
    storage.delete(KEY)  # a missing key is not an error
    with pytest.raises(FileNotFoundError):
        storage.read(KEY)


def test_s3_errors_other_than_a_missing_key_pass_through(s3):
    def denied(**_):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "GetObject")

    s3.get_object = denied

    with pytest.raises(ClientError):
        S3ImageStorage(s3, "menu-photos").read(KEY)


def test_s3_url_is_presigned_and_expires(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATESTTESTTESTTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
    storage = S3ImageStorage(s3_client("ap-northeast-2"), "menu-photos", url_ttl=timedelta(minutes=15))
    before = datetime.now(timezone.utc)

    url, expires_at = storage.url(KEY)

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.hostname == "menu-photos.s3.ap-northeast-2.amazonaws.com"
    assert parsed.path == f"/{KEY}"
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-Expires"] == ["900"]
    assert timedelta(minutes=14) < expires_at - before <= timedelta(minutes=15, seconds=1)


@pytest.fixture
def configured(monkeypatch):
    """get_image_storage() built from environment variables, with its cache reset around the test."""

    def build(**env):
        for name in ("IMAGE_STORAGE", "S3_BUCKET", "AWS_REGION", "S3_URL_TTL_SECONDS"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        get_image_storage.cache_clear()
        return get_image_storage()

    yield build
    get_image_storage.cache_clear()


def test_s3_storage_is_configured_from_the_environment(configured):
    storage = configured(IMAGE_STORAGE="s3", S3_BUCKET="menu-photos", AWS_REGION="ap-northeast-2", S3_URL_TTL_SECONDS="600")

    assert isinstance(storage, S3ImageStorage)
    assert (storage.bucket, storage.url_ttl) == ("menu-photos", timedelta(minutes=10))
    assert storage.client.meta.region_name == "ap-northeast-2"


@pytest.mark.parametrize(("env", "message"), [({"IMAGE_STORAGE": "s3"}, "S3_BUCKET"), ({"IMAGE_STORAGE": "gcs"}, "gcs")])
def test_invalid_storage_settings(configured, env, message):
    with pytest.raises(RuntimeError, match=message):
        configured(**env)


def test_server_start_fails_when_s3_is_not_configured(configured, monkeypatch):
    monkeypatch.setenv("IMAGE_STORAGE", "s3")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    get_image_storage.cache_clear()

    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        with TestClient(app):
            pass


def test_media_route_is_off_with_s3(s3):
    app.dependency_overrides[get_image_storage] = lambda: S3ImageStorage(s3, "menu-photos")
    try:
        assert TestClient(app).get(f"/media/{KEY}").status_code == 404
    finally:
        app.dependency_overrides.pop(get_image_storage, None)
