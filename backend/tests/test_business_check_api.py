"""The business registration check before applying (API spec 3.11.16), its share of the daily NTS limit
(3.11.14), and applications that use a recent match instead of calling NTS (3.11.2, step 5).

The NTS check is a fake `BusinessVerifier`; no test calls the real API.
"""

from datetime import date, timedelta
from uuid import UUID

import pytest

from app.adapters.business_verification import BusinessCheck, BusinessVerificationUnavailable
from app.api import deps
from app.main import app
from app.models import (
    BarOwnerApplication,
    BusinessStatus,
    BusinessVerificationResult,
    OwnerApplicationStatus,
    UserType,
)
from app.schemas.owner_application import BusinessFieldsInput
from app.services.business_check import RECENT_CHECK_TTL, RecentBusinessChecks, RecentMatch
from app.services.request_limits import BUSINESS_VERIFICATION, DAILY_LIMIT
from tests.factories import make_user
from tests.test_owner_applications_api import (  # noqa: F401 (fixtures)
    NOW,
    OTHER_SUBJECT,
    SUBJECT,
    apply,
    applicant,
    auth,
    bearer,
    error_of,
    field_errors,
    limiter,
    new_bar_body,
    verifier,
)

FIELDS = {"businessRegistrationNumber": "123-45-67891", "representativeName": "김사장", "openingDate": "2020-03-02"}


@pytest.fixture
def recent():
    fresh = RecentBusinessChecks()
    app.dependency_overrides[deps.get_recent_business_checks] = lambda: fresh
    yield fresh
    app.dependency_overrides.pop(deps.get_recent_business_checks, None)


@pytest.fixture
def clock(limiter):
    """The request time, moved by setting `clock.now`; starts at NOW like the limiter fixture."""

    class Clock:
        now = NOW

    app.dependency_overrides[deps.get_clock] = lambda: lambda: Clock.now
    return Clock


def check(client, headers, **changes):
    return client.post("/api/owner-applications/business-verification", json=FIELDS | changes, headers=headers)


def result_of(response) -> str:
    assert response.status_code == 200, response.text
    return response.json()["result"]


def stored(db_session, response) -> BarOwnerApplication:
    assert response.status_code == 201, response.text
    return db_session.get(BarOwnerApplication, UUID(response.json()["applicationId"]))


def used(limiter) -> int:
    return limiter.used(SUBJECT, BUSINESS_VERIFICATION, NOW)


# ---- the check (3.11.16) ----


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        pytest.param(BusinessCheck(True, BusinessStatus.CLOSED), "matched", id="matched"),
        pytest.param(BusinessCheck(False), "not_matched", id="not matched"),
        pytest.param(BusinessVerificationUnavailable("timeout"), "unavailable", id="NTS unreachable"),
    ],
)
def test_returns_only_the_result_and_counts_the_call(client, auth, verifier, limiter, recent, answer, expected):
    verifier.answer = answer

    response = check(client, auth)

    assert response.json() == {"result": expected}
    assert verifier.calls == [("1234567891", "김사장", date(2020, 3, 2))]
    assert used(limiter) == 1


def test_without_an_nts_key_the_result_is_unavailable_and_not_counted(client, auth, limiter, recent):
    assert result_of(check(client, auth)) == "unavailable"
    assert used(limiter) == 0


def test_needs_a_token_but_no_users_row(client, supabase, verifier, limiter, recent):
    assert error_of(client.post("/api/owner-applications/business-verification", json=FIELDS)) == (
        401,
        "UNAUTHENTICATED",
    )
    assert result_of(check(client, bearer(supabase, OTHER_SUBJECT))) == "matched"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        pytest.param(
            {"businessRegistrationNumber": "1234567890"},
            [("businessRegistrationNumber", "INVALID_BUSINESS_NUMBER")],
            id="check digit",
        ),
        pytest.param({"representativeName": "  "}, [("representativeName", "STRING_TOO_SHORT")], id="blank name"),
        pytest.param({"openingDate": "2020-3-2"}, [("openingDate", "DATE_FROM_DATETIME_PARSING")], id="date format"),
        # 2026-10-30 is today in Korea at NOW, so the day after is in the future.
        pytest.param({"openingDate": "2026-10-31"}, [("openingDate", "DATE_IN_FUTURE")], id="future date"),
        pytest.param({"contactPhone": "010-1234-5678"}, [("contactPhone", "EXTRA_FORBIDDEN")], id="other field"),
    ],
)
def test_field_rules_follow_applying(client, auth, verifier, limiter, recent, change, expected):
    assert field_errors(check(client, auth, **change)) == expected
    assert verifier.calls == []
    assert used(limiter) == 0


def test_today_in_korea_is_not_in_the_future(client, auth, verifier, limiter, recent):
    assert result_of(check(client, auth, openingDate="2026-10-30")) == "matched"


def test_missing_fields_are_listed_together(client, auth, verifier, limiter, recent):
    response = client.post("/api/owner-applications/business-verification", json={}, headers=auth)

    assert field_errors(response) == [
        ("businessRegistrationNumber", "MISSING"),
        ("representativeName", "MISSING"),
        ("openingDate", "MISSING"),
    ]


# ---- one daily limit with applying (3.11.14) ----


def test_checking_and_applying_share_the_daily_limit(client, auth, verifier, limiter, recent):
    verifier.answer = BusinessCheck(False)
    for _ in range(DAILY_LIMIT - 1):
        assert result_of(check(client, auth)) == "not_matched"
    assert error_of(apply(client, auth, new_bar_body())) == (422, "BUSINESS_VERIFICATION_FAILED")

    refused = check(client, auth)

    assert error_of(refused) == (429, "RATE_LIMITED")
    assert refused.json()["error"]["details"] == {"retryAfter": "2026-10-30T15:00:00Z"}
    assert error_of(apply(client, auth, new_bar_body())) == (429, "RATE_LIMITED")
    assert len(verifier.calls) == DAILY_LIMIT


# ---- applying with a recent match (3.11.2, step 5) ----


def test_applying_after_a_match_does_not_call_nts_again(client, db_session, auth, verifier, limiter, recent, clock):
    verifier.answer = BusinessCheck(True, BusinessStatus.SUSPENDED)
    assert result_of(check(client, auth)) == "matched"
    clock.now = NOW + timedelta(minutes=10)

    application = stored(db_session, apply(client, auth, new_bar_body(businessRegistrationNumber="123 45 67891")))

    assert len(verifier.calls) == 1
    assert used(limiter) == 1
    assert application.business_verification_result == BusinessVerificationResult.MATCHED
    assert application.business_status == BusinessStatus.SUSPENDED
    # The time of the check that matched, not of the application.
    assert application.business_checked_at == NOW


def test_a_match_is_used_even_when_the_limit_is_used_up(client, db_session, auth, verifier, limiter, recent):
    assert result_of(check(client, auth)) == "matched"
    for _ in range(DAILY_LIMIT - 1):
        check(client, auth, representativeName="이사장")
    assert error_of(check(client, auth)) == (429, "RATE_LIMITED")

    application = stored(db_session, apply(client, auth, new_bar_body()))

    assert application.business_verification_result == BusinessVerificationResult.MATCHED


def test_a_match_is_used_even_without_an_nts_key(client, db_session, auth, verifier, limiter, recent):
    assert result_of(check(client, auth)) == "matched"
    app.dependency_overrides[deps.get_business_verifier] = lambda: None

    application = stored(db_session, apply(client, auth, new_bar_body()))

    assert application.business_verification_result == BusinessVerificationResult.MATCHED


def test_an_expired_match_is_not_used(client, db_session, auth, verifier, limiter, recent, clock):
    assert result_of(check(client, auth)) == "matched"
    clock.now = NOW + RECENT_CHECK_TTL
    verifier.answer = BusinessCheck(False)

    assert error_of(apply(client, auth, new_bar_body())) == (422, "BUSINESS_VERIFICATION_FAILED")
    assert len(verifier.calls) == 2


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"representativeName": "이사장"}, id="name"),
        pytest.param({"openingDate": "2020-03-03"}, id="opening date"),
        pytest.param({"businessRegistrationNumber": "2208162517"}, id="business number"),
    ],
)
def test_a_match_for_other_values_is_not_used(client, auth, verifier, limiter, recent, change):
    assert result_of(check(client, auth)) == "matched"
    verifier.answer = BusinessCheck(False)

    assert error_of(apply(client, auth, new_bar_body(**change))) == (422, "BUSINESS_VERIFICATION_FAILED")
    assert len(verifier.calls) == 2


def test_someone_elses_match_is_not_used(client, db_session, supabase, auth, verifier, limiter, recent):
    assert result_of(check(client, bearer(supabase, OTHER_SUBJECT))) == "matched"
    verifier.answer = BusinessCheck(False)

    assert error_of(apply(client, auth, new_bar_body())) == (422, "BUSINESS_VERIFICATION_FAILED")
    assert used(limiter) == 1


@pytest.mark.parametrize(
    "answer", [BusinessCheck(False), BusinessVerificationUnavailable("timeout")], ids=["not matched", "unavailable"]
)
def test_only_matches_are_remembered(client, db_session, auth, verifier, limiter, recent, answer):
    verifier.answer = answer
    check(client, auth)
    verifier.answer = BusinessCheck(True, BusinessStatus.ACTIVE)

    application = stored(db_session, apply(client, auth, new_bar_body()))

    assert application.business_verification_result == BusinessVerificationResult.MATCHED
    assert len(verifier.calls) == 2


def test_a_match_serves_more_than_one_application(client, db_session, auth, verifier, limiter, recent, applicant):
    """A rejected or canceled applicant who applies again within the time needs no new NTS call."""
    assert result_of(check(client, auth)) == "matched"
    first = stored(db_session, apply(client, auth, new_bar_body()))
    first.status = OwnerApplicationStatus.CANCELED
    db_session.flush()

    stored(db_session, apply(client, auth, new_bar_body()))

    assert len(verifier.calls) == 1


# ---- the store ----


def fields(name: str = "김사장") -> BusinessFieldsInput:
    return BusinessFieldsInput.model_validate(FIELDS | {"representativeName": name})


def test_the_store_forgets_expired_matches_when_adding():
    store = RecentBusinessChecks()
    store.remember("a", fields(), RecentMatch(None, NOW))
    store.remember("a", fields("이사장"), RecentMatch(None, NOW + timedelta(minutes=29)))

    store.remember("b", fields(), RecentMatch(None, NOW + RECENT_CHECK_TTL))

    assert store.recall("a", fields(), NOW) is None
    assert store.recall("a", fields("이사장"), NOW + RECENT_CHECK_TTL) is not None
    assert store.recall("b", fields(), NOW + RECENT_CHECK_TTL) is not None
    assert len(store._matches) == 2


def test_the_store_answers_until_the_time_is_up():
    store = RecentBusinessChecks()
    match = RecentMatch(BusinessStatus.ACTIVE, NOW)
    store.remember("a", fields(), match)

    assert store.recall("a", fields(), NOW + RECENT_CHECK_TTL - timedelta(seconds=1)) == match
    assert store.recall("a", fields(), NOW + RECENT_CHECK_TTL) is None
    assert store.recall("b", fields(), NOW) is None


def test_the_app_keeps_one_store_per_process():
    assert deps.get_recent_business_checks() is deps.get_recent_business_checks()


def test_an_operator_can_check_too(client, db_session, supabase, verifier, limiter, recent):
    make_user(db_session, OTHER_SUBJECT, user_type=UserType.OPERATOR)
    assert result_of(check(client, bearer(supabase, OTHER_SUBJECT))) == "matched"
