"""An operator resetting today's request counts without a restart (API spec, section 3.11.19).
The NTS check is a fake; no test calls it."""

from datetime import datetime, timezone

import pytest

from app.adapters.business_verification import BusinessCheck
from app.api import deps
from app.main import app
from app.models import UserType
from app.services.request_limits import (
    BUSINESS_CERTIFICATE_OCR,
    BUSINESS_VERIFICATION,
    BUSINESS_VERIFICATION_DAILY_LIMIT,
    InMemoryDailyLimiter,
)
from tests.factories import make_user
from tests.test_owner_applications_api import FakeVerifier

PATH = "/api/request-limits/reset"
OPERATOR_SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"
APPLICANT_SUBJECT = "5d1c2b3a-0000-4000-8000-000000000002"
OTHER_SUBJECT = "6f1c2d3e-4b5a-4c6d-8e7f-0a1b2c3d4e5f"
NO_ROW_SUBJECT = "7a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
MISSING_ID = "99999999-9999-4999-8999-999999999999"
# 2026-10-30 18:00 KST.
NOW = datetime(2026, 10, 30, 9, tzinfo=timezone.utc)
FIELDS = {"businessRegistrationNumber": "1234567891", "representativeName": "김사장", "openingDate": "2020-03-02"}


@pytest.fixture
def limiter():
    fresh = InMemoryDailyLimiter()
    app.dependency_overrides[deps.get_request_limiter] = lambda: fresh
    app.dependency_overrides[deps.get_clock] = lambda: lambda: NOW
    yield fresh
    app.dependency_overrides.pop(deps.get_request_limiter, None)
    app.dependency_overrides.pop(deps.get_clock, None)


@pytest.fixture
def operator(db_session):
    return make_user(db_session, OPERATOR_SUBJECT, user_type=UserType.OPERATOR)


@pytest.fixture
def auth(supabase, operator):
    return {"Authorization": f"Bearer {supabase.token(sub=OPERATOR_SUBJECT)}"}


@pytest.fixture
def applicant(db_session):
    return make_user(db_session, APPLICANT_SUBJECT)


@pytest.fixture
def other(db_session):
    return make_user(db_session, OTHER_SUBJECT)


def use_up(limiter, subject: str, kind: str, times: int = 1) -> None:
    for _ in range(times):
        assert limiter.acquire(subject, kind, NOW).counted


def reset(client, headers, body=None):
    return client.post(PATH, headers=headers) if body is None else client.post(PATH, headers=headers, json=body)


def cleared(response) -> int:
    assert response.status_code == 200, response.text
    return response.json()["clearedCount"]


def error_of(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def field_errors(response) -> list[tuple[str, str]]:
    assert response.status_code == 422, response.text
    return [(error["path"], error["code"]) for error in response.json()["error"]["fieldErrors"]]


# ---- the flow it is for ----


def test_a_user_out_of_nts_checks_can_check_again_after_a_reset(client, supabase, limiter, auth, applicant):
    verifier = FakeVerifier()
    verifier.answer = BusinessCheck(False)
    app.dependency_overrides[deps.get_business_verifier] = lambda: verifier
    applicant_auth = {"Authorization": f"Bearer {supabase.token(sub=APPLICANT_SUBJECT)}"}

    def check():
        return client.post("/api/owner-applications/business-verification", json=FIELDS, headers=applicant_auth)

    try:
        for _ in range(BUSINESS_VERIFICATION_DAILY_LIMIT):
            assert check().status_code == 200
        assert error_of(check()) == (429, "RATE_LIMITED")

        assert cleared(reset(client, auth, {"userId": str(applicant.id)})) == 1

        assert check().status_code == 200
    finally:
        app.dependency_overrides.pop(deps.get_business_verifier, None)
    assert len(verifier.calls) == BUSINESS_VERIFICATION_DAILY_LIMIT + 1
    assert limiter.used(APPLICANT_SUBJECT, BUSINESS_VERIFICATION, NOW) == 1


# ---- scope ----


@pytest.mark.parametrize("body", [None, {}, {"userId": None, "kind": None}])
def test_no_body_clears_every_user_and_kind(client, limiter, auth, applicant, body):
    use_up(limiter, APPLICANT_SUBJECT, BUSINESS_VERIFICATION, 3)
    use_up(limiter, APPLICANT_SUBJECT, BUSINESS_CERTIFICATE_OCR)
    use_up(limiter, NO_ROW_SUBJECT, BUSINESS_CERTIFICATE_OCR)

    assert cleared(reset(client, auth, body)) == 3

    for subject in (APPLICANT_SUBJECT, NO_ROW_SUBJECT):
        for kind in (BUSINESS_VERIFICATION, BUSINESS_CERTIFICATE_OCR):
            assert limiter.used(subject, kind, NOW) == 0


def test_a_user_id_clears_only_that_user(client, limiter, auth, applicant, other):
    use_up(limiter, APPLICANT_SUBJECT, BUSINESS_VERIFICATION, 2)
    use_up(limiter, APPLICANT_SUBJECT, BUSINESS_CERTIFICATE_OCR)
    use_up(limiter, OTHER_SUBJECT, BUSINESS_VERIFICATION)

    assert cleared(reset(client, auth, {"userId": str(applicant.id)})) == 2

    assert limiter.used(APPLICANT_SUBJECT, BUSINESS_VERIFICATION, NOW) == 0
    assert limiter.used(APPLICANT_SUBJECT, BUSINESS_CERTIFICATE_OCR, NOW) == 0
    assert limiter.used(OTHER_SUBJECT, BUSINESS_VERIFICATION, NOW) == 1


def test_a_kind_clears_only_that_kind(client, limiter, auth, applicant, other):
    use_up(limiter, APPLICANT_SUBJECT, BUSINESS_VERIFICATION)
    use_up(limiter, APPLICANT_SUBJECT, BUSINESS_CERTIFICATE_OCR)
    use_up(limiter, OTHER_SUBJECT, BUSINESS_CERTIFICATE_OCR)

    assert cleared(reset(client, auth, {"kind": "business_certificate_ocr"})) == 2

    assert limiter.used(APPLICANT_SUBJECT, BUSINESS_VERIFICATION, NOW) == 1
    assert limiter.used(APPLICANT_SUBJECT, BUSINESS_CERTIFICATE_OCR, NOW) == 0
    assert limiter.used(OTHER_SUBJECT, BUSINESS_CERTIFICATE_OCR, NOW) == 0


def test_a_user_id_and_a_kind_together(client, limiter, auth, applicant, other):
    use_up(limiter, APPLICANT_SUBJECT, BUSINESS_VERIFICATION)
    use_up(limiter, APPLICANT_SUBJECT, BUSINESS_CERTIFICATE_OCR)
    use_up(limiter, OTHER_SUBJECT, BUSINESS_VERIFICATION)

    body = {"userId": str(applicant.id), "kind": "business_verification"}
    assert cleared(reset(client, auth, body)) == 1

    assert limiter.used(APPLICANT_SUBJECT, BUSINESS_VERIFICATION, NOW) == 0
    assert limiter.used(APPLICANT_SUBJECT, BUSINESS_CERTIFICATE_OCR, NOW) == 1
    assert limiter.used(OTHER_SUBJECT, BUSINESS_VERIFICATION, NOW) == 1


def test_nothing_to_clear_is_200_with_zero(client, limiter, auth, applicant):
    assert cleared(reset(client, auth, {"userId": str(applicant.id)})) == 0
    assert cleared(reset(client, auth)) == 0


def test_a_user_without_a_row_is_cleared_only_by_a_reset_of_everyone(client, limiter, auth):
    use_up(limiter, NO_ROW_SUBJECT, BUSINESS_CERTIFICATE_OCR)

    assert cleared(reset(client, auth)) == 1

    assert limiter.used(NO_ROW_SUBJECT, BUSINESS_CERTIFICATE_OCR, NOW) == 0


# ---- errors ----


def test_an_unknown_user_id_is_404_and_clears_nothing(client, limiter, auth, applicant):
    use_up(limiter, APPLICANT_SUBJECT, BUSINESS_VERIFICATION)

    assert error_of(reset(client, auth, {"userId": MISSING_ID})) == (404, "USER_NOT_FOUND")

    assert limiter.used(APPLICANT_SUBJECT, BUSINESS_VERIFICATION, NOW) == 1


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"userId": "not-a-uuid"}, [("userId", "UUID_PARSING")]),
        ({"kind": "menu_import"}, [("kind", "LITERAL_ERROR")]),
        ({"subject": OTHER_SUBJECT}, [("subject", "EXTRA_FORBIDDEN")]),
    ],
)
def test_invalid_bodies_are_422_and_clear_nothing(client, limiter, auth, applicant, body, expected):
    use_up(limiter, APPLICANT_SUBJECT, BUSINESS_VERIFICATION)

    assert field_errors(reset(client, auth, body)) == expected

    assert limiter.used(APPLICANT_SUBJECT, BUSINESS_VERIFICATION, NOW) == 1


def test_a_customer_is_403_and_clears_nothing(client, supabase, limiter, applicant):
    use_up(limiter, APPLICANT_SUBJECT, BUSINESS_VERIFICATION)
    headers = {"Authorization": f"Bearer {supabase.token(sub=APPLICANT_SUBJECT)}"}

    assert error_of(reset(client, headers)) == (403, "FORBIDDEN")

    assert limiter.used(APPLICANT_SUBJECT, BUSINESS_VERIFICATION, NOW) == 1
