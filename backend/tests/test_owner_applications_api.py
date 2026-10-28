"""Applying to own a bar, and reading one's applications (API spec, sections 3.11.2 to 3.11.4).

The NTS check is a fake `BusinessVerifier`; no test calls the real API.
"""

from datetime import date, datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.adapters.business_verification import BusinessCheck, BusinessVerificationUnavailable
from app.api import deps
from app.main import app
from app.models import (
    BarOwnerApplication,
    BarStatus,
    BusinessStatus,
    BusinessVerificationResult,
    OwnerApplicationStatus,
    UserType,
)
from app.services.request_limits import BUSINESS_VERIFICATION, DAILY_LIMIT, InMemoryDailyLimiter
from tests.factories import BUSINESS_NUMBER, make_application, make_bar, make_owner, make_user

SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"
OTHER_SUBJECT = "5d1c2b3a-0000-4000-8000-000000000002"
# 00:30 on 2026-10-30 in Korea, still 2026-10-29 in UTC.
NOW = datetime(2026, 10, 29, 15, 30, tzinfo=timezone.utc)
MISSING_ID = "99999999-9999-4999-8999-999999999999"


class FakeVerifier:
    def __init__(self, answer: BusinessCheck | Exception = BusinessCheck(True, BusinessStatus.ACTIVE)) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str, date]] = []
        self.during_call = None  # run inside verify(), e.g. to create a concurrent duplicate

    def verify(self, number: str, name: str, opened: date) -> BusinessCheck:
        self.calls.append((number, name, opened))
        if self.during_call is not None:
            self.during_call()
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def verifier():
    fake = FakeVerifier()
    app.dependency_overrides[deps.get_business_verifier] = lambda: fake
    yield fake
    app.dependency_overrides.pop(deps.get_business_verifier, None)


@pytest.fixture
def limiter():
    fresh = InMemoryDailyLimiter()
    app.dependency_overrides[deps.get_request_limiter] = lambda: fresh
    app.dependency_overrides[deps.get_clock] = lambda: lambda: NOW
    yield fresh
    app.dependency_overrides.pop(deps.get_request_limiter, None)
    app.dependency_overrides.pop(deps.get_clock, None)


@pytest.fixture
def applicant(db_session):
    return make_user(db_session, SUBJECT, email="owner@example.com", display_name="김사장")


def bearer(supabase, subject: str = SUBJECT) -> dict:
    return {"Authorization": f"Bearer {supabase.token(sub=subject)}"}


@pytest.fixture
def auth(supabase, applicant):
    return bearer(supabase)


def existing_bar_body(bar, **changes) -> dict:
    body = {
        "applicationType": "existing_bar",
        "barId": str(bar.id),
        "businessRegistrationNumber": "123-45-67891",
        "representativeName": "김사장",
        "openingDate": "2020-03-02",
        "contactPhone": "010-1234-5678",
        "applicantNote": "대표 본인입니다",
    }
    return body | changes


def new_bar_body(**changes) -> dict:
    body = {
        "applicationType": "new_bar",
        "proposedBar": {"name": "신림 몰트 하우스", "address": "서울특별시 관악구 신림로 2 3층", "phone": "02-1234-5678"},
        "businessRegistrationNumber": "1234567891",
        "representativeName": "김사장",
        "openingDate": "2020-03-02",
        "contactPhone": "010-1234-5678",
    }
    return body | changes


def apply(client, headers, body):
    return client.post("/api/owner-applications", json=body, headers=headers)


def error_of(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def field_errors(response) -> list[tuple[str, str]]:
    assert response.status_code == 422
    return [(error["path"], error["code"]) for error in response.json()["error"]["fieldErrors"]]


def application_count(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(BarOwnerApplication))


# ---- applying (3.11.2) ----


def test_applies_for_an_existing_bar(client, db_session, auth, applicant, verifier, limiter):
    bar = make_bar(db_session, "관악 위스키 바")

    response = apply(client, auth, existing_bar_body(bar))

    assert response.status_code == 201
    body = response.json()
    assert response.headers["Location"] == f"/api/owner-applications/{body['applicationId']}"
    assert body == {
        "applicationId": body["applicationId"],
        "applicationType": "existing_bar",
        "status": "pending",
        "applicant": {"userId": str(applicant.id), "email": "owner@example.com", "displayName": "김사장"},
        "bar": {"barId": str(bar.id), "name": "관악 위스키 바", "address": "관악 위스키 바 address"},
        "proposedBar": None,
        "businessRegistrationNumber": BUSINESS_NUMBER,
        "representativeName": "김사장",
        "openingDate": "2020-03-02",
        "businessStatus": "active",
        "businessVerification": None,
        "contactPhone": "010-1234-5678",
        "applicantNote": "대표 본인입니다",
        "rejectionReason": None,
        "reviewedAt": None,
        "createdAt": body["createdAt"],
        "updatedAt": body["updatedAt"],
    }
    assert verifier.calls == [(BUSINESS_NUMBER, "김사장", date(2020, 3, 2))]
    stored = db_session.get(BarOwnerApplication, UUID(body["applicationId"]))
    assert stored.business_verification_result == BusinessVerificationResult.MATCHED
    assert stored.business_status == BusinessStatus.ACTIVE
    assert stored.business_checked_at == NOW


def test_applies_for_a_new_bar(client, auth, verifier, limiter):
    response = apply(client, auth, new_bar_body(applicantNote="   "))

    assert response.status_code == 201
    body = response.json()
    assert body["bar"] is None
    assert body["proposedBar"] == {
        "name": "신림 몰트 하우스",
        "address": "서울특별시 관악구 신림로 2 3층",
        "phone": "02-1234-5678",
    }
    assert body["applicantNote"] is None


def test_values_are_trimmed_and_an_empty_phone_is_null(client, auth, verifier, limiter):
    body = new_bar_body(representativeName="  김사장 ", proposedBar={"name": " 바 ", "address": " 주소 ", "phone": " "})

    response = apply(client, auth, body)

    assert response.status_code == 201
    assert response.json()["representativeName"] == "김사장"
    assert response.json()["proposedBar"] == {"name": "바", "address": "주소", "phone": None}


def test_an_operator_sees_the_check_result(client, db_session, supabase, verifier, limiter):
    make_user(db_session, SUBJECT, user_type=UserType.OPERATOR)

    response = apply(client, bearer(supabase), new_bar_body())

    assert response.json()["businessVerification"] == {"result": "matched", "checkedAt": "2026-10-29T15:30:00Z"}


@pytest.mark.parametrize(
    ("code", "status"),
    [(BusinessStatus.CLOSED, "closed"), (None, None)],
)
def test_a_match_keeps_the_nts_status(client, auth, verifier, limiter, code, status):
    verifier.answer = BusinessCheck(True, code)

    response = apply(client, auth, new_bar_body())

    assert response.status_code == 201
    assert response.json()["businessStatus"] == status


def test_a_mismatch_creates_nothing(client, db_session, auth, verifier, limiter):
    verifier.answer = BusinessCheck(False)

    response = apply(client, auth, new_bar_body())

    assert error_of(response) == (422, "BUSINESS_VERIFICATION_FAILED")
    assert application_count(db_session) == 0


def test_an_unreachable_check_is_stored_as_unavailable(client, db_session, auth, verifier, limiter):
    verifier.answer = BusinessVerificationUnavailable("timeout")

    response = apply(client, auth, new_bar_body())

    assert response.status_code == 201
    assert response.json()["businessStatus"] is None
    stored = db_session.get(BarOwnerApplication, UUID(response.json()["applicationId"]))
    assert stored.business_verification_result == BusinessVerificationResult.UNAVAILABLE
    assert limiter.used(SUBJECT, BUSINESS_VERIFICATION, NOW) == 1


def test_without_an_nts_key_applications_are_unavailable_and_not_counted(client, db_session, auth, limiter):
    response = apply(client, auth, new_bar_body())

    assert response.status_code == 201
    stored = db_session.get(BarOwnerApplication, UUID(response.json()["applicationId"]))
    assert stored.business_verification_result == BusinessVerificationResult.UNAVAILABLE
    assert limiter.used(SUBJECT, BUSINESS_VERIFICATION, NOW) == 0


def test_the_nts_check_is_limited_per_day(client, auth, verifier, limiter):
    verifier.answer = BusinessCheck(False)
    for _ in range(DAILY_LIMIT):
        assert error_of(apply(client, auth, new_bar_body())) == (422, "BUSINESS_VERIFICATION_FAILED")

    response = apply(client, auth, new_bar_body())

    assert error_of(response) == (429, "RATE_LIMITED")
    # Midnight KST at the end of 2026-10-30.
    assert response.json()["error"]["details"] == {"retryAfter": "2026-10-30T15:00:00Z"}
    assert len(verifier.calls) == DAILY_LIMIT


BAD_NUMBER = ("businessRegistrationNumber", "INVALID_BUSINESS_NUMBER")


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        pytest.param({"businessRegistrationNumber": "1234567890"}, BAD_NUMBER, id="check digit"),
        pytest.param({"businessRegistrationNumber": "12345"}, BAD_NUMBER, id="too short"),
        pytest.param({"openingDate": "2020-3-2"}, ("openingDate", "DATE_FROM_DATETIME_PARSING"), id="date format"),
        pytest.param({"openingDate": 1583107200}, ("openingDate", "DATE_TYPE"), id="date as a number"),
        pytest.param({"representativeName": "   "}, ("representativeName", "STRING_TOO_SHORT"), id="blank name"),
        pytest.param({"representativeName": "가" * 101}, ("representativeName", "STRING_TOO_LONG"), id="long name"),
        pytest.param({"contactPhone": None}, ("contactPhone", "STRING_TYPE"), id="null phone"),
        pytest.param({"applicantNote": "가" * 501}, ("applicantNote", "STRING_TOO_LONG"), id="long note"),
        pytest.param({"barId": "x"}, ("barId", "EXTRA_FORBIDDEN"), id="barId on new_bar"),
        pytest.param(
            {"proposedBar": {"name": "", "address": "a"}}, ("proposedBar.name", "STRING_TOO_SHORT"), id="blank bar name"
        ),
        pytest.param({"applicationType": "owner"}, ("", "UNION_TAG_INVALID"), id="unknown type"),
    ],
)
def test_field_rules(client, auth, verifier, limiter, change, expected):
    response = apply(client, auth, new_bar_body(**change))

    assert field_errors(response) == [expected]
    assert verifier.calls == []


def test_missing_fields_are_listed_together(client, auth, verifier, limiter):
    body = new_bar_body()
    del body["contactPhone"], body["representativeName"]

    assert sorted(field_errors(apply(client, auth, body))) == [
        ("contactPhone", "MISSING"),
        ("representativeName", "MISSING"),
    ]


def test_an_existing_bar_application_cannot_propose_a_bar(client, db_session, auth, verifier, limiter):
    body = existing_bar_body(make_bar(db_session), proposedBar={"name": "a", "address": "b"})

    assert field_errors(apply(client, auth, body)) == [("proposedBar", "EXTRA_FORBIDDEN")]


@pytest.mark.parametrize(("opened", "allowed"), [("2026-10-30", True), ("2026-10-31", False)])
def test_the_opening_date_may_be_today_in_korea(client, auth, verifier, limiter, opened, allowed):
    response = apply(client, auth, new_bar_body(openingDate=opened))

    if allowed:
        assert response.status_code == 201
    else:
        assert field_errors(response) == [("openingDate", "DATE_IN_FUTURE")]


def test_needs_a_users_row(client, supabase, verifier, limiter):
    response = apply(client, bearer(supabase), new_bar_body())

    assert error_of(response) == (404, "USER_NOT_FOUND")
    assert verifier.calls == []


def test_needs_a_token(client, verifier, limiter):
    assert error_of(apply(client, {}, new_bar_body())) == (401, "UNAUTHENTICATED")


@pytest.mark.parametrize("bar_id", ["not-a-uuid", MISSING_ID, "inactive"])
def test_the_claimed_bar_must_be_active(client, db_session, auth, verifier, limiter, bar_id):
    if bar_id == "inactive":
        bar_id = str(make_bar(db_session, status=BarStatus.INACTIVE).id)
    body = existing_bar_body(make_bar(db_session)) | {"barId": bar_id}

    assert error_of(apply(client, auth, body)) == (404, "BAR_NOT_FOUND")
    assert verifier.calls == []


@pytest.mark.parametrize("owner", ["someone else", "the applicant"])
def test_a_bar_with_an_owner_cannot_be_claimed(client, db_session, auth, applicant, verifier, limiter, owner):
    bar, operator = make_bar(db_session), make_user(db_session, "operator-subject", user_type=UserType.OPERATOR)
    current = applicant if owner == "the applicant" else make_user(db_session, OTHER_SUBJECT)
    make_owner(db_session, current, bar, operator)

    assert error_of(apply(client, auth, existing_bar_body(bar))) == (409, "BAR_OWNER_EXISTS")
    assert verifier.calls == []


def test_one_pending_application_per_bar(client, db_session, auth, applicant, verifier, limiter):
    bar = make_bar(db_session)
    pending = make_application(db_session, applicant, bar)

    response = apply(client, auth, existing_bar_body(bar))

    assert error_of(response) == (409, "OWNER_APPLICATION_EXISTS")
    assert response.json()["error"]["details"] == {"applicationId": str(pending.id)}
    assert verifier.calls == []


def test_one_pending_new_bar_application_per_business_number(client, db_session, auth, applicant, verifier, limiter):
    pending = make_application(db_session, applicant)

    same = apply(client, auth, new_bar_body())
    other = apply(client, auth, new_bar_body(businessRegistrationNumber="1234567800"))

    assert error_of(same) == (409, "OWNER_APPLICATION_EXISTS")
    assert same.json()["error"]["details"] == {"applicationId": str(pending.id)}
    assert other.status_code == 201


def test_others_and_finished_applications_do_not_block(client, db_session, auth, applicant, verifier, limiter):
    bar = make_bar(db_session)
    make_application(db_session, make_user(db_session, OTHER_SUBJECT), bar)
    make_application(db_session, applicant, bar, status=OwnerApplicationStatus.CANCELED)

    assert apply(client, auth, existing_bar_body(bar)).status_code == 201


def test_a_concurrent_duplicate_is_caught_by_the_database(client, db_session, auth, applicant, verifier, limiter):
    bar = make_bar(db_session)
    created = []
    # Another request of the same user creates the same pending application while NTS answers.
    verifier.during_call = lambda: created.append(make_application(db_session, applicant, bar))

    response = apply(client, auth, existing_bar_body(bar))

    assert error_of(response) == (409, "OWNER_APPLICATION_EXISTS")
    assert response.json()["error"]["details"] == {"applicationId": str(created[0].id)}
    assert limiter.used(SUBJECT, BUSINESS_VERIFICATION, NOW) == 1
    assert application_count(db_session) == 1


# ---- my applications (3.11.3) ----


def test_lists_my_applications_newest_first(client, db_session, auth, applicant):
    older = make_application(db_session, applicant, make_bar(db_session))
    older.created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    newer = make_application(db_session, applicant)
    newer.business_verification_result = BusinessVerificationResult.MATCHED
    newer.business_status = BusinessStatus.SUSPENDED
    make_application(db_session, make_user(db_session, OTHER_SUBJECT))
    db_session.flush()

    response = client.get("/api/me/owner-applications", headers=auth)

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["applicationId"] for item in items] == [str(newer.id), str(older.id)]
    assert [item["businessVerification"] for item in items] == [None, None]
    assert items[0]["businessStatus"] == "suspended"
    assert items[0]["proposedBar"] == {"name": "New Bar", "address": "New Bar address", "phone": None}


def test_an_operator_lists_only_their_own(client, db_session, supabase):
    operator = make_user(db_session, SUBJECT, user_type=UserType.OPERATOR)
    make_application(db_session, make_user(db_session, OTHER_SUBJECT))
    mine = make_application(db_session, operator)

    response = client.get("/api/me/owner-applications", headers=bearer(supabase))

    assert [item["applicationId"] for item in response.json()["items"]] == [str(mine.id)]
    assert response.json()["items"][0]["businessVerification"] is None


def test_my_list_is_empty_without_a_users_row(client, supabase):
    response = client.get("/api/me/owner-applications", headers=bearer(supabase))

    assert response.json() == {"items": []}


# ---- one application (3.11.4) ----


def test_reads_my_application(client, db_session, auth, applicant):
    operator = make_user(db_session, "operator-subject", user_type=UserType.OPERATOR)
    bar = make_bar(db_session)
    rejected = make_application(db_session, applicant, bar, status=OwnerApplicationStatus.REJECTED, reviewer=operator)

    response = client.get(f"/api/owner-applications/{rejected.id}", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejectionReason"] == "확인할 수 없습니다."
    assert body["reviewedAt"] == "2026-10-14T05:00:00Z"
    assert body["businessVerification"] is None


@pytest.mark.parametrize("target", ["someone else's", "missing", "malformed"])
def test_other_applications_look_missing(client, db_session, auth, target):
    other = make_application(db_session, make_user(db_session, OTHER_SUBJECT))
    application_id = {"someone else's": str(other.id), "missing": MISSING_ID, "malformed": "x"}[target]

    response = client.get(f"/api/owner-applications/{application_id}", headers=auth)

    assert error_of(response) == (404, "OWNER_APPLICATION_NOT_FOUND")


def test_a_caller_without_a_users_row_sees_nothing(client, db_session, supabase):
    other = make_application(db_session, make_user(db_session, OTHER_SUBJECT))

    response = client.get(
        f"/api/owner-applications/{other.id}", headers=bearer(supabase)
    )

    assert error_of(response) == (404, "OWNER_APPLICATION_NOT_FOUND")


def test_an_operator_reads_any_application_with_the_check_result(client, db_session, supabase):
    make_user(db_session, SUBJECT, user_type=UserType.OPERATOR)
    other = make_application(db_session, make_user(db_session, OTHER_SUBJECT))

    response = client.get(
        f"/api/owner-applications/{other.id}", headers=bearer(supabase)
    )

    assert response.status_code == 200
    assert response.json()["businessVerification"] == {"result": "unavailable", "checkedAt": "2026-10-14T03:00:00Z"}


def test_a_temporary_operator_reads_any_application(client, db_session, token_for):
    other = make_application(db_session, make_user(db_session, OTHER_SUBJECT))

    response = client.get(
        f"/api/owner-applications/{other.id}", headers={"Authorization": f"Bearer {token_for('operator')}"}
    )

    assert response.status_code == 200


def test_other_integrity_errors_are_not_reported_as_duplicates(client, db_session, auth, verifier, limiter):
    bar = make_bar(db_session)
    # The bar disappears while NTS answers, so the insert breaks its foreign key, not a pending index.
    verifier.during_call = lambda: (db_session.delete(bar), db_session.flush())

    with pytest.raises(IntegrityError):
        apply(client, auth, existing_bar_body(bar))
