"""POST /api/owner-applications/business-certificate-ocr (spec 3.11.12, OCR limit of 3.11.14).

CLOVA is replaced by a fake `call_ocr` or an httpx MockTransport; no test calls the real API.
"""

import logging
from datetime import UTC, datetime

import httpx
import pytest

from app.adapters import clova_certificate_ocr
from app.adapters.clova_certificate_ocr import (
    CERTIFICATE_OCR_MAX_ATTEMPTS,
    CERTIFICATE_OCR_TIMEOUT_S,
    ClovaCertificateOcr,
)
from app.api import deps
from app.extraction import clova
from app.extraction.clova import ClovaOCRError, ClovaSettings
from app.main import app
from app.services.request_limits import BUSINESS_CERTIFICATE_OCR, InMemoryDailyLimiter
from tests.certificate_support import individual_certificate, jpeg, png

PATH = "/api/owner-applications/business-certificate-ocr"
SETTINGS = ClovaSettings(invoke_url="https://ocr.example.test/custom/v1/1/abc/general", secret="clova-secret")
# 2026-10-28 18:00 KST; the limit resets at 2026-10-29 00:00 KST = 2026-10-28T15:00:00Z.
NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
NEXT_DAY = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
READ_VALUES = ["1234567891", "123-45-67891", "김사장", "신림", "몰트", "서울특별시", "관악구", "2020-03-02", "1980"]


class Clock:
    now = NOW

    def __call__(self) -> datetime:
        return self.now


class FakeCall:
    """Stands in for clova.call_ocr; set `error` to make it fail."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.error: Exception | None = None
        self.response = individual_certificate()

    def __call__(self, settings, image, mime_type):
        self.calls.append(mime_type)
        if self.error is not None:
            raise self.error
        return {"response": self.response, "sentSize": [120, 160], "latencyMs": 1, "attempts": 1}


@pytest.fixture
def clock():
    clock = Clock()
    app.dependency_overrides[deps.get_clock] = lambda: clock
    yield clock
    app.dependency_overrides.pop(deps.get_clock, None)


@pytest.fixture
def limiter():
    limiter = InMemoryDailyLimiter()
    app.dependency_overrides[deps.get_request_limiter] = lambda: limiter
    yield limiter
    app.dependency_overrides.pop(deps.get_request_limiter, None)


@pytest.fixture
def ocr(monkeypatch, clock, limiter):
    """CLOVA configured, with the HTTP call replaced."""
    fake = FakeCall()
    monkeypatch.setattr(clova_certificate_ocr, "call_ocr", fake)
    app.dependency_overrides[deps.get_certificate_ocr] = lambda: ClovaCertificateOcr(SETTINGS)
    yield fake
    app.dependency_overrides.pop(deps.get_certificate_ocr, None)


@pytest.fixture
def no_ocr(clock, limiter):
    app.dependency_overrides[deps.get_certificate_ocr] = lambda: None
    yield
    app.dependency_overrides.pop(deps.get_certificate_ocr, None)


@pytest.fixture
def user(supabase):
    """A Supabase user without a users row."""
    subject = "6f1c2d3e-4b5a-4c6d-8e7f-0a1b2c3d4e5f"
    return subject, {"Authorization": f"Bearer {supabase.token(sub=subject)}"}


def post(client, headers, *images):
    images = images or (("certificate.jpg", jpeg(), "image/jpeg"),)
    return client.post(PATH, headers=headers, files=[("image", image) for image in images])


def error_of(response):
    return response.status_code, response.json()["error"]["code"]


# ---- success ----


def test_reads_the_certificate_without_a_users_row(client, ocr, limiter, user):
    subject, headers = user
    response = post(client, headers)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "businessRegistrationNumber": "1234567891",
        "representativeName": "김사장",
        "openingDate": "2020-03-02",
        "businessName": "신림 몰트 하우스",
        "address": "서울특별시 관악구 신림로 2 3층",
    }
    assert ocr.calls == ["image/jpeg"]
    assert limiter.used(subject, BUSINESS_CERTIFICATE_OCR, NOW) == 1


def test_png_and_a_generic_declared_type_are_accepted(client, ocr, user):
    _, headers = user
    assert post(client, headers, ("c.png", png(), "image/png")).status_code == 200
    assert post(client, headers, ("c.jpg", jpeg(), "application/octet-stream")).status_code == 200
    assert ocr.calls == ["image/png", "image/jpeg"]


def test_nothing_read_is_200_with_all_null_and_counted(client, ocr, limiter, user):
    subject, headers = user
    ocr.response = {"images": [{"inferResult": "SUCCESS", "fields": []}]}
    response = post(client, headers)

    assert response.status_code == 200
    assert set(response.json().values()) == {None}
    assert limiter.used(subject, BUSINESS_CERTIFICATE_OCR, NOW) == 1


def test_temporary_login_tokens_can_call_it(client, ocr, token_for):
    response = post(client, {"Authorization": f"Bearer {token_for('customer')}"})
    assert response.status_code == 200


def test_the_photo_is_not_stored(client, ocr, user, image_storage):
    post(client, user[1])
    assert not image_storage.root.exists() or not any(image_storage.root.rglob("*"))


# ---- request errors (not counted) ----


def test_guest_is_unauthenticated(client, ocr):
    response = post(client, {})
    assert error_of(response) == (401, "UNAUTHENTICATED")
    assert ocr.calls == []


def test_missing_image(client, ocr, limiter, user):
    subject, headers = user
    response = client.post(PATH, headers=headers, data={"note": "x"})

    assert error_of(response) == (422, "VALIDATION_FAILED")
    assert response.json()["error"]["fieldErrors"][0]["path"] == "image"
    assert response.json()["error"]["fieldErrors"][0]["code"] == "MISSING"
    assert limiter.used(subject, BUSINESS_CERTIFICATE_OCR, NOW) == 0


def test_more_than_one_image(client, ocr, limiter, user):
    subject, headers = user
    response = post(client, headers, ("a.jpg", jpeg(), "image/jpeg"), ("b.jpg", jpeg(), "image/jpeg"))

    assert error_of(response) == (422, "VALIDATION_FAILED")
    assert response.json()["error"]["fieldErrors"][0] == {
        "path": "image",
        "code": "TOO_LONG",
        "message": "List should have at most 1 item after validation",
    }
    assert ocr.calls == [] and limiter.used(subject, BUSINESS_CERTIFICATE_OCR, NOW) == 0


def test_too_large(client, ocr, limiter, user):
    subject, headers = user
    big = b"\xff\xd8\xff\xe0" + b"0" * (10 * 1024 * 1024 - 3)
    response = post(client, headers, ("big.jpg", big, "image/jpeg"))

    assert error_of(response) == (413, "UPLOAD_TOO_LARGE")
    assert response.json()["error"]["details"] == {"maxImageBytes": 10 * 1024 * 1024}
    assert ocr.calls == [] and limiter.used(subject, BUSINESS_CERTIFICATE_OCR, NOW) == 0


@pytest.mark.parametrize(
    "image",
    [
        ("c.gif", b"GIF89a-body", "image/gif"),
        ("c.heic", b"\x00\x00\x00\x18ftypheic-body", "image/heic"),
        ("c.jpg", png(), "image/jpeg"),  # declared type disagrees with the content
    ],
)
def test_unsupported_type(client, ocr, limiter, user, image):
    subject, headers = user
    response = post(client, headers, image)

    assert error_of(response) == (415, "UNSUPPORTED_IMAGE_TYPE")
    assert ocr.calls == [] and limiter.used(subject, BUSINESS_CERTIFICATE_OCR, NOW) == 0


def test_undecodable_image_is_415_and_not_counted(client, ocr, limiter, user):
    subject, headers = user
    response = post(client, headers, ("c.jpg", b"\xff\xd8\xff\xe0 not really a jpeg", "image/jpeg"))

    assert error_of(response) == (415, "UNSUPPORTED_IMAGE_TYPE")
    assert ocr.calls == [] and limiter.used(subject, BUSINESS_CERTIFICATE_OCR, NOW) == 0


# ---- OCR unavailable ----


def test_no_ocr_settings_is_503_and_not_counted(client, no_ocr, limiter, user):
    subject, headers = user
    response = post(client, headers)

    assert error_of(response) == (503, "OCR_UNAVAILABLE")
    assert limiter.used(subject, BUSINESS_CERTIFICATE_OCR, NOW) == 0


def test_ocr_failure_is_503_and_counted(client, ocr, limiter, user):
    subject, headers = user
    ocr.error = ClovaOCRError("CLOVA OCR failed after 2 attempt(s): HTTP 500")
    response = post(client, headers)

    assert error_of(response) == (503, "OCR_UNAVAILABLE")
    assert limiter.used(subject, BUSINESS_CERTIFICATE_OCR, NOW) == 1


def test_ocr_is_retried_once_then_503(client, clock, limiter, user, monkeypatch):
    """The real call path with a mock transport: two attempts with the shorter certificate timeout."""
    seen, timeouts = [], []

    def handler(request):
        seen.append(request)
        return httpx.Response(503)

    mock = httpx.Client(transport=httpx.MockTransport(handler))

    def make_client(timeout):
        timeouts.append(timeout)
        return mock

    monkeypatch.setattr(clova.httpx, "Client", make_client)
    monkeypatch.setattr(clova, "sleep", lambda seconds: None)
    app.dependency_overrides[deps.get_certificate_ocr] = lambda: ClovaCertificateOcr(SETTINGS)
    try:
        response = post(client, user[1])
    finally:
        app.dependency_overrides.pop(deps.get_certificate_ocr, None)

    assert error_of(response) == (503, "OCR_UNAVAILABLE")
    assert len(seen) == CERTIFICATE_OCR_MAX_ATTEMPTS == 2
    assert timeouts == [CERTIFICATE_OCR_TIMEOUT_S]
    assert limiter.used(user[0], BUSINESS_CERTIFICATE_OCR, NOW) == 1


def test_ocr_settings_come_from_the_clova_variables(monkeypatch):
    monkeypatch.delenv("CLOVA_OCR_INVOKE_URL", raising=False)
    monkeypatch.delenv("CLOVA_OCR_SECRET", raising=False)
    assert deps.get_certificate_ocr() is None

    monkeypatch.setenv("CLOVA_OCR_INVOKE_URL", "https://ocr.example.test/custom/v1/1/abc")
    monkeypatch.setenv("CLOVA_OCR_SECRET", "clova-secret")
    reader = deps.get_certificate_ocr()
    assert isinstance(reader, ClovaCertificateOcr)
    assert reader.settings.invoke_url == "https://ocr.example.test/custom/v1/1/abc/general"
    assert (reader.settings.timeout_s, reader.settings.max_attempts) == (20.0, 2)


def test_default_limiter_and_clock():
    deps.get_request_limiter.cache_clear()
    try:
        assert deps.get_request_limiter() is deps.get_request_limiter()
        assert isinstance(deps.get_request_limiter(), InMemoryDailyLimiter)
    finally:
        deps.get_request_limiter.cache_clear()
    assert deps.get_clock()().tzinfo is UTC


# ---- daily limit ----


def test_five_calls_a_day_then_429_until_midnight_kst(client, ocr, clock, user):
    _, headers = user
    ocr.error = ClovaOCRError("HTTP 500")
    assert [post(client, headers).status_code for _ in range(2)] == [503, 503]  # failures count
    ocr.error = None
    assert [post(client, headers).status_code for _ in range(3)] == [200, 200, 200]

    response = post(client, headers)
    assert error_of(response) == (429, "RATE_LIMITED")
    assert response.json()["error"]["details"] == {"retryAfter": "2026-10-28T15:00:00Z"}
    assert len(ocr.calls) == 5  # the sixth request did not call CLOVA

    # A request that fails the checks still gets its own error, and is not counted.
    assert error_of(post(client, headers, ("c.gif", b"GIF89a", "image/gif"))) == (415, "UNSUPPORTED_IMAGE_TYPE")

    clock.now = NEXT_DAY
    assert post(client, headers).status_code == 200
    assert len(ocr.calls) == 6


def test_limit_is_per_token_subject(client, ocr, limiter, supabase):
    first = {"Authorization": f"Bearer {supabase.token(sub='11111111-1111-4111-8111-111111111111')}"}
    second = {"Authorization": f"Bearer {supabase.token(sub='22222222-2222-4222-8222-222222222222')}"}
    for _ in range(5):
        post(client, first)

    assert error_of(post(client, first)) == (429, "RATE_LIMITED")
    assert post(client, second).status_code == 200


# ---- privacy ----


def test_values_and_photo_are_never_logged(client, ocr, user, caplog):
    _, headers = user
    caplog.set_level(logging.DEBUG)
    assert post(client, headers).status_code == 200
    ocr.error = ClovaOCRError("CLOVA OCR failed after 2 attempt(s): HTTP 500")
    assert post(client, headers).status_code == 503

    logged = caplog.text + " ".join(str(record.args) for record in caplog.records)
    for value in READ_VALUES:
        assert value not in logged
    assert "OCR failed" in caplog.text  # the failure itself is logged, without values
