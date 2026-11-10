"""Warnings for operators about owner applications that share a business registration number (spec 3.11.1).

Other pending and approved applications with the same number, of any user and either type, are listed;
only the application itself is left out. Applicants never see warnings (`null`), so they cannot learn
whether someone else gave a number.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.api import deps
from app.main import app
from app.models import OwnerApplicationStatus, OwnerApplicationType, UserType
from tests.factories import BUSINESS_NUMBER, make_application, make_bar, make_owner, make_user
from tests.test_owner_applications_api import FakeVerifier

OPERATOR_SUBJECT = "warnings-operator"
APPLICANT_SUBJECT = "warnings-applicant"
OTHER_SUBJECT = "warnings-other"
OTHER_NUMBER = "1234567800"
NOW = datetime(2026, 11, 10, 3, tzinfo=timezone.utc)
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"


@pytest.fixture
def operator(db_session):
    return make_user(db_session, OPERATOR_SUBJECT, user_type=UserType.OPERATOR)


@pytest.fixture
def applicant(db_session):
    return make_user(db_session, APPLICANT_SUBJECT)


@pytest.fixture
def other(db_session):
    return make_user(db_session, OTHER_SUBJECT)


def headers(supabase, subject: str) -> dict:
    return {"Authorization": f"Bearer {supabase.token(sub=subject)}"}


def created(db_session, application, minutes: int):
    """Give `application` its own creation time; rows made in one test transaction share now()."""
    application.created_at = NOW + timedelta(minutes=minutes)
    db_session.flush()
    return application


def detail(client, supabase, application_id, subject: str = OPERATOR_SUBJECT) -> dict:
    response = client.get(f"/api/owner-applications/{application_id}", headers=headers(supabase, subject))
    assert response.status_code == 200, response.text
    return response.json()


def shared(body: dict) -> list[dict]:
    """The applications of the BUSINESS_NUMBER_SHARED warning, or [] without one."""
    warnings = [warning for warning in body["warnings"] if warning["code"] == "BUSINESS_NUMBER_SHARED"]
    assert len(warnings) <= 1
    return warnings[0]["details"]["applications"] if warnings else []


def test_other_users_pending_and_approved_applications_are_listed(
    client, db_session, supabase, operator, applicant, other
):
    target = created(db_session, make_application(db_session, applicant), 0)
    pending_claim = created(db_session, make_application(db_session, other, make_bar(db_session, "Claimed Bar")), 1)
    approved_claim = created(
        db_session,
        make_application(
            db_session,
            other,
            make_bar(db_session, "Owned Bar"),
            status=OwnerApplicationStatus.APPROVED,
            reviewer=operator,
        ),
        2,
    )
    pending_new_bar = created(db_session, make_application(db_session, make_user(db_session, "third")), 3)
    for status in (OwnerApplicationStatus.REJECTED, OwnerApplicationStatus.CANCELED):
        make_application(db_session, other, status=status, reviewer=operator)
    make_application(db_session, other, business_registration_number=OTHER_NUMBER)

    body = detail(client, supabase, target.id)

    [warning] = body["warnings"]
    assert warning["code"] == "BUSINESS_NUMBER_SHARED"
    assert warning["message"] == (
        "같은 사업자등록번호로 낸 다른 신청이 3건 있습니다. 같은 사업자의 다른 매장인지 확인해 주세요."
    )
    # Newest first; rejected, canceled and other numbers are left out.
    assert warning["details"]["applications"] == [
        {
            "applicationId": str(pending_new_bar.id),
            "status": "pending",
            "applicationType": "new_bar",
            "barName": "New Bar",
            "sameApplicant": False,
        },
        {
            "applicationId": str(approved_claim.id),
            "status": "approved",
            "applicationType": "existing_bar",
            "barName": "Owned Bar",
            "sameApplicant": False,
        },
        {
            "applicationId": str(pending_claim.id),
            "status": "pending",
            "applicationType": "existing_bar",
            "barName": "Claimed Bar",
            "sameApplicant": False,
        },
    ]


def test_the_applicants_other_applications_are_listed_but_not_the_application_itself(
    client, db_session, supabase, operator, applicant
):
    target = created(db_session, make_application(db_session, applicant), 0)
    own_bar = make_bar(db_session, "Applicant's Bar")
    approved_new_bar = created(
        db_session,
        make_application(
            db_session,
            applicant,
            own_bar,
            application_type=OwnerApplicationType.NEW_BAR,
            status=OwnerApplicationStatus.APPROVED,
            reviewer=operator,
        ),
        1,
    )
    second_shop = make_bar(db_session, "Second Shop")
    pending_claim = created(db_session, make_application(db_session, applicant, second_shop), 2)

    applications = shared(detail(client, supabase, target.id))

    assert [(a["applicationId"], a["barName"], a["sameApplicant"]) for a in applications] == [
        (str(pending_claim.id), "Second Shop", True),
        (str(approved_new_bar.id), "Applicant's Bar", True),
    ]
    assert str(target.id) not in [a["applicationId"] for a in applications]


def test_an_approved_application_counts_after_its_owner_was_removed(
    client, db_session, supabase, operator, applicant, other
):
    ownership = make_owner(db_session, other, make_bar(db_session, "Former Owner's Bar"), operator)
    ownership.revoked_at, ownership.revoked_by_user_id = NOW, operator.id
    db_session.flush()
    target = make_application(db_session, applicant)

    assert [(a["applicationId"], a["status"]) for a in shared(detail(client, supabase, target.id))] == [
        (str(ownership.application_id), "approved")
    ]


def test_an_application_with_its_own_number_has_no_warnings(
    client, db_session, supabase, operator, applicant, other
):
    target = make_application(db_session, applicant)
    make_application(db_session, other, business_registration_number=OTHER_NUMBER)

    assert detail(client, supabase, target.id)["warnings"] == []


def test_each_application_in_the_operator_list_gets_its_own_warnings(
    client, db_session, supabase, operator, applicant, other
):
    first = created(db_session, make_application(db_session, applicant), 0)
    second = created(db_session, make_application(db_session, other, make_bar(db_session, "Claimed Bar")), 1)
    alone = created(db_session, make_application(db_session, other, business_registration_number=OTHER_NUMBER), 2)

    response = client.get("/api/owner-applications", headers=headers(supabase, OPERATOR_SUBJECT))

    assert response.status_code == 200
    items = response.json()["items"]
    by_id = {item["applicationId"]: [a["applicationId"] for a in shared(item)] for item in items}
    assert by_id == {str(first.id): [str(second.id)], str(second.id): [str(first.id)], str(alone.id): []}


def test_warnings_take_one_query_per_page(client, db_session, supabase, operator, applicant, other):
    def count_queries() -> int:
        statements = []

        def listen(conn, cursor, statement, *args):
            statements.append(statement)

        event.listen(db_session.get_bind(), "before_cursor_execute", listen)
        try:
            response = client.get("/api/owner-applications", headers=headers(supabase, OPERATOR_SUBJECT))
            assert response.status_code == 200
        finally:
            event.remove(db_session.get_bind(), "before_cursor_execute", listen)
        return len(statements)

    make_application(db_session, applicant)
    make_application(db_session, other, make_bar(db_session))
    few = count_queries()
    for n in range(6):
        user = make_user(db_session, f"more-{n}")
        make_application(db_session, user, make_bar(db_session, f"More {n}"))
        make_application(db_session, user, business_registration_number=OTHER_NUMBER)

    assert count_queries() == few


def test_applicants_never_see_warnings(client, db_session, supabase, operator, applicant, other, image_storage):
    verifier = FakeVerifier()
    app.dependency_overrides[deps.get_business_verifier] = lambda: verifier
    try:
        # Someone else's applications give the same number.
        make_application(db_session, other, make_bar(db_session, "Claimed Bar"))
        make_owner(db_session, make_user(db_session, "owner"), make_bar(db_session, "Owned Bar"), operator)
        auth = headers(supabase, APPLICANT_SUBJECT)
        body = {
            "applicationType": "new_bar",
            "proposedBar": {"name": "신림 몰트 하우스", "address": "서울특별시 관악구 신림로 2"},
            "businessRegistrationNumber": BUSINESS_NUMBER,
            "representativeName": "김사장",
            "openingDate": "2020-03-02",
            "contactPhone": "010-1234-5678",
        }

        created_response = client.post("/api/owner-applications", json=body, headers=auth)
        application_id = created_response.json()["applicationId"]
        url = f"/api/owner-applications/{application_id}"
        responses = {
            "create": created_response,
            "detail": client.get(url, headers=auth),
            "menu photos": client.put(
                f"{url}/menu-photos", headers=auth, files=[("images", ("menu.jpg", JPEG, "image/jpeg"))]
            ),
            "cover photo": client.delete(f"{url}/cover-photo", headers=auth),
            "cancel": client.post(f"{url}/cancel", headers=auth),
        }
        mine = client.get("/api/me/owner-applications", headers=auth)
    finally:
        app.dependency_overrides.pop(deps.get_business_verifier, None)

    for name, response in responses.items():
        assert response.status_code in (200, 201), (name, response.text)
        assert response.json()["warnings"] is None, name
    assert [item["warnings"] for item in mine.json()["items"]] == [None]
    # The operator sees the same application with the warning.
    assert len(shared(detail(client, supabase, application_id))) == 2


def test_review_responses_carry_the_warnings(client, db_session, supabase, operator, applicant, other):
    make_application(db_session, other)
    target = make_application(db_session, applicant, make_bar(db_session, "Claimed Bar"))
    auth = headers(supabase, OPERATOR_SUBJECT)

    approved = client.post(f"/api/owner-applications/{target.id}/approve", headers=auth)

    assert approved.status_code == 200, approved.text
    assert len(shared(approved.json())) == 1
