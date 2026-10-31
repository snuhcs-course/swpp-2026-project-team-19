"""Operators reviewing owner applications (API spec, sections 3.11.6 to 3.11.8): list, approve, reject."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from app.api import deps
from app.main import app
from app.models import (
    Bar,
    BarOwner,
    BarOwnerApplication,
    BarStatus,
    BusinessVerificationResult,
    ImportMode,
    ImportStatus,
    MenuImport,
    OwnerApplicationStatus,
    UserType,
)
from app.services import owner_application_review
from tests.factories import (
    make_application,
    make_application_menu_image,
    make_bar,
    make_owner,
    make_user,
    publish_menu,
)

OPERATOR_SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"
APPLICANT_SUBJECT = "5d1c2b3a-0000-4000-8000-000000000002"
MISSING_ID = "99999999-9999-4999-8999-999999999999"
NOW = datetime(2026, 10, 31, 9, tzinfo=timezone.utc)
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"
NEW_BAR = {
    "name": "신림 몰트 하우스",
    "address": "서울특별시 관악구 신림로 2 3층",
    "latitude": 37.4841023,
    "longitude": 126.929815,
    "phone": "02-1234-5678",
}


@pytest.fixture(autouse=True)
def fixed_clock():
    app.dependency_overrides[deps.get_clock] = lambda: lambda: NOW
    yield
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


def error_of(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def field_errors(response) -> list[tuple[str, str]]:
    assert response.status_code == 422, response.text
    return [(error["path"], error["code"]) for error in response.json()["error"]["fieldErrors"]]


def created(db_session, application, minutes: int):
    """Give `application` its own creation time; rows made in one test transaction share now()."""
    application.created_at = NOW - timedelta(days=1) + timedelta(minutes=minutes)
    db_session.flush()
    return application


def with_stored_photos(db_session, storage, application, count: int = 2):
    for order in range(1, count + 1):
        image = make_application_menu_image(db_session, application, image_order=order)
        storage.save(image.storage_key, JPEG, "image/jpeg")


def approve(client, headers, application_id, body=None):
    url = f"/api/owner-applications/{application_id}/approve"
    return client.post(url, headers=headers) if body is None else client.post(url, headers=headers, json=body)


def reject(client, headers, application_id, body=None):
    body = {"reason": "사업자등록번호를 확인할 수 없습니다."} if body is None else body
    return client.post(f"/api/owner-applications/{application_id}/reject", headers=headers, json=body)


def imports_of(db_session, bar_id) -> list[MenuImport]:
    return list(db_session.scalars(select(MenuImport).where(MenuImport.bar_id == bar_id)))


def current_owner(db_session, bar_id) -> BarOwner | None:
    return db_session.scalar(select(BarOwner).where(BarOwner.bar_id == bar_id, BarOwner.revoked_at.is_(None)))


# ---- list (3.11.6) ----


def listed_ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["applicationId"] for item in response.json()["items"]]


def test_pending_applications_come_oldest_first(client, db_session, auth, applicant, operator):
    newer = created(db_session, make_application(db_session, applicant), 2)
    older = created(db_session, make_application(db_session, applicant, make_bar(db_session)), 1)
    created(
        db_session,
        make_application(
            db_session, applicant, make_bar(db_session), status=OwnerApplicationStatus.REJECTED, reviewer=operator
        ),
        3,
    )

    response = client.get("/api/owner-applications", headers=auth)

    assert listed_ids(response) == [str(older.id), str(newer.id)]
    item = response.json()["items"][0]
    assert item["businessVerification"]["result"] == "unavailable"
    assert item["menuPhotos"] == []
    assert response.json()["nextCursor"] is None


def test_other_statuses_come_newest_first(client, db_session, auth, applicant, operator):
    pending = created(db_session, make_application(db_session, applicant), 1)
    canceled = created(
        db_session, make_application(db_session, applicant, status=OwnerApplicationStatus.CANCELED), 2
    )

    assert listed_ids(client.get("/api/owner-applications?status=all", headers=auth)) == [
        str(canceled.id),
        str(pending.id),
    ]
    assert listed_ids(client.get("/api/owner-applications?status=canceled", headers=auth)) == [str(canceled.id)]


def test_filters_by_type_and_check_result(client, db_session, auth, applicant):
    new_bar = created(db_session, make_application(db_session, applicant), 1)
    existing = created(db_session, make_application(db_session, applicant, make_bar(db_session)), 2)
    existing.business_verification_result = BusinessVerificationResult.MATCHED
    db_session.flush()

    assert listed_ids(client.get("/api/owner-applications?applicationType=new_bar", headers=auth)) == [str(new_bar.id)]
    assert listed_ids(client.get("/api/owner-applications?verificationResult=matched", headers=auth)) == [
        str(existing.id)
    ]
    assert listed_ids(
        client.get("/api/owner-applications?applicationType=new_bar&verificationResult=matched", headers=auth)
    ) == []


@pytest.mark.parametrize("status", ["pending", "all"])
def test_pages_follow_the_cursor(client, db_session, auth, applicant, status):
    applications = [
        created(db_session, make_application(db_session, applicant, business_registration_number=number), minutes)
        for minutes, number in enumerate(["1234567891", "1234567800", "1234567819"])
    ]
    expected = [str(a.id) for a in (applications if status == "pending" else reversed(applications))]

    first = client.get(f"/api/owner-applications?status={status}&limit=2", headers=auth)
    second = client.get(
        f"/api/owner-applications?status={status}&limit=2&cursor={first.json()['nextCursor']}", headers=auth
    )

    assert listed_ids(first) + listed_ids(second) == expected
    assert second.json()["nextCursor"] is None


def test_a_cursor_works_only_with_its_filters(client, db_session, auth, applicant):
    for minutes in range(2):
        created(db_session, make_application(db_session, applicant, make_bar(db_session)), minutes)
    cursor = client.get("/api/owner-applications?limit=1", headers=auth).json()["nextCursor"]

    response = client.get(f"/api/owner-applications?status=all&limit=1&cursor={cursor}", headers=auth)

    assert field_errors(response) == [("cursor", "INVALID_CURSOR")]
    assert field_errors(client.get("/api/owner-applications?cursor=not-a-cursor", headers=auth)) == [
        ("cursor", "INVALID_CURSOR")
    ]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("status=open", ("status", "LITERAL_ERROR")),
        ("applicationType=bar", ("applicationType", "LITERAL_ERROR")),
        ("verificationResult=maybe", ("verificationResult", "LITERAL_ERROR")),
        ("limit=0", ("limit", "GREATER_THAN_EQUAL")),
        ("limit=101", ("limit", "LESS_THAN_EQUAL")),
    ],
)
def test_list_query_rules(client, auth, query, expected):
    assert field_errors(client.get(f"/api/owner-applications?{query}", headers=auth)) == [expected]


# ---- approve an existing_bar application (3.11.7) ----


def test_approves_an_existing_bar_application(client, db_session, supabase, auth, applicant, operator):
    bar = make_bar(db_session, "관악 위스키 바")
    application = make_application(db_session, applicant, bar)

    response = approve(client, auth, application.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["reviewedAt"]) == ("approved", "2026-10-31T09:00:00Z")
    assert body["bar"] == {"barId": str(bar.id), "name": "관악 위스키 바", "address": "관악 위스키 바 address"}
    assert body["businessVerification"] is not None
    db_session.refresh(application)
    assert application.reviewed_by_user_id == operator.id
    owner = current_owner(db_session, bar.id)
    assert (owner.user_id, owner.application_id) == (applicant.id, application.id)
    assert imports_of(db_session, bar.id) == []
    # The applicant manages the bar from their next request.
    applicant_auth = {"Authorization": f"Bearer {supabase.token(sub=APPLICANT_SUBJECT)}"}
    my_bars = client.get("/api/me/bars", headers=applicant_auth).json()["items"]
    assert [item["barId"] for item in my_bars] == [str(bar.id)]


def test_an_empty_body_is_accepted_for_an_existing_bar(client, db_session, auth, applicant):
    application = make_application(db_session, applicant, make_bar(db_session))

    assert approve(client, auth, application.id, {}).status_code == 200


def test_a_bar_deactivated_after_applying_can_still_be_approved(client, db_session, auth, applicant):
    bar = make_bar(db_session, status=BarStatus.INACTIVE)
    application = make_application(db_session, applicant, bar)

    assert approve(client, auth, application.id).status_code == 200
    assert current_owner(db_session, bar.id) is not None


def test_an_existing_bar_application_takes_no_bar(client, db_session, auth, applicant):
    application = make_application(db_session, applicant, make_bar(db_session))

    assert field_errors(approve(client, auth, application.id, {"bar": NEW_BAR})) == [("bar", "EXTRA_FORBIDDEN")]
    db_session.refresh(application)
    assert application.status == OwnerApplicationStatus.PENDING


def test_a_bar_with_an_owner_cannot_be_approved_again(client, db_session, auth, applicant, operator):
    bar = make_bar(db_session)
    make_owner(db_session, make_user(db_session, "first-owner"), bar, operator)
    application = make_application(db_session, applicant, bar)

    assert error_of(approve(client, auth, application.id)) == (409, "BAR_OWNER_EXISTS")
    db_session.refresh(application)
    assert application.status == OwnerApplicationStatus.PENDING


def test_an_owner_approved_concurrently_is_caught_by_the_database(
    client, db_session, auth, applicant, operator, monkeypatch
):
    bar = make_bar(db_session)
    application = make_application(db_session, applicant, bar)
    rival = make_application(db_session, make_user(db_session, "rival"), bar)
    # The service rolls back on the conflict; commit the setup so that rollback keeps it.
    db_session.commit()
    initial_import = owner_application_review._initial_import

    def rival_wins(session, *args):
        # Another approval commits an owner for the bar after this one checked for owners.
        rival.status, rival.reviewed_by_user_id, rival.reviewed_at = OwnerApplicationStatus.APPROVED, operator.id, NOW
        session.add(BarOwner(bar_id=bar.id, user_id=rival.applicant_user_id, application_id=rival.id))
        return initial_import(session, *args)

    monkeypatch.setattr(owner_application_review, "_initial_import", rival_wins)

    assert error_of(approve(client, auth, application.id)) == (409, "BAR_OWNER_EXISTS")
    db_session.refresh(application)
    assert application.status == OwnerApplicationStatus.PENDING


def test_other_integrity_errors_are_not_reported_as_an_owner(client, db_session, image_storage, auth, applicant):
    application = make_application(db_session, applicant, make_bar(db_session))
    with_stored_photos(db_session, image_storage, application, count=1)
    # A finished import elsewhere already took the key the approval would use.
    db_session.add(
        MenuImport(
            idempotency_key=f"owner-application:{application.id}",
            request_fingerprint="0" * 64,
            bar_id=make_bar(db_session, "Other").id,
            mode=ImportMode.FULL_REPLACE,
            status=ImportStatus.APPLIED,
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError):
        approve(client, auth, application.id)


def test_approval_locks_the_application_and_the_bar(client, db_session, auth, applicant):
    application = make_application(db_session, applicant, make_bar(db_session))
    statements = []

    def listen(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(db_session.get_bind(), "before_cursor_execute", listen)
    try:
        assert approve(client, auth, application.id).status_code == 200
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", listen)

    locked = [s for s in statements if "FOR UPDATE" in s]
    assert any("FROM bar_owner_applications" in s for s in locked)
    assert any("FROM bars" in s for s in locked)


# ---- approve a new_bar application (3.11.7) ----


def test_approves_a_new_bar_application_and_creates_the_bar(client, db_session, auth, applicant):
    application = make_application(db_session, applicant)

    response = approve(client, auth, application.id, {"bar": NEW_BAR | {"name": "  신림 몰트 하우스 ", "phone": " "}})

    assert response.status_code == 200, response.text
    db_session.refresh(application)
    bar = db_session.get(Bar, application.bar_id)
    assert (bar.name, bar.address, bar.phone, bar.status) == (
        "신림 몰트 하우스",
        "서울특별시 관악구 신림로 2 3층",
        None,
        BarStatus.ACTIVE,
    )
    assert (bar.latitude, bar.longitude) == (Decimal("37.484102"), Decimal("126.929815"))
    assert response.json()["bar"] == {"barId": str(bar.id), "name": bar.name, "address": bar.address}
    assert current_owner(db_session, bar.id).user_id == applicant.id


def test_a_new_bar_application_needs_the_bar(client, db_session, auth, applicant):
    application = make_application(db_session, applicant)

    assert field_errors(approve(client, auth, application.id)) == [("bar", "MISSING")]
    assert field_errors(approve(client, auth, application.id, {})) == [("bar", "MISSING")]
    db_session.refresh(application)
    assert (application.status, application.bar_id) == (OwnerApplicationStatus.PENDING, None)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"name": " "}, ("bar.name", "STRING_TOO_SHORT")),
        ({"address": "x" * 501}, ("bar.address", "STRING_TOO_LONG")),
        ({"latitude": 91}, ("bar.latitude", "LESS_THAN_EQUAL")),
        ({"longitude": -181}, ("bar.longitude", "GREATER_THAN_EQUAL")),
        ({"phone": "0" * 31}, ("bar.phone", "STRING_TOO_LONG")),
        ({"floor": 2}, ("bar.floor", "EXTRA_FORBIDDEN")),
    ],
)
def test_bar_field_rules(client, auth, change, expected):
    # Field rules are checked before the application, so a missing one still answers 422.
    assert field_errors(approve(client, auth, MISSING_ID, {"bar": NEW_BAR | change})) == [expected]


def test_missing_bar_fields_are_listed(client, auth):
    assert field_errors(approve(client, auth, MISSING_ID, {"bar": {"name": "Bar"}})) == [
        ("bar.address", "MISSING"),
        ("bar.latitude", "MISSING"),
        ("bar.longitude", "MISSING"),
    ]


# ---- the first menu import on approval ----


def test_photos_become_the_first_menu_import(client, db_session, image_storage, auth, applicant):
    application = make_application(db_session, applicant)
    with_stored_photos(db_session, image_storage, application)
    keys = [photo.storage_key for photo in owner_application_review_photos(db_session, application)]

    response = approve(client, auth, application.id, {"bar": NEW_BAR})

    assert response.status_code == 200, response.text
    db_session.refresh(application)
    [menu_import] = imports_of(db_session, application.bar_id)
    assert menu_import.mode == ImportMode.FULL_REPLACE
    assert menu_import.idempotency_key == f"owner-application:{application.id}"
    assert menu_import.owner_note is None
    assert [image.storage_key for image in menu_import.images] == keys
    assert all(image.extraction_run is not None for image in menu_import.images)
    # TestClient runs the scheduled processing right after the response.
    db_session.refresh(menu_import)
    assert menu_import.status == ImportStatus.READY_FOR_REVIEW
    # The photos stay with the approved application and in storage.
    assert len(response.json()["menuPhotos"]) == 2
    assert all(image_storage.read(key) == JPEG for key in keys)


def test_the_owner_finds_the_import_as_the_active_one(client, db_session, supabase, image_storage, auth, applicant):
    application = make_application(db_session, applicant, make_bar(db_session))
    with_stored_photos(db_session, image_storage, application, count=1)
    approve(client, auth, application.id)
    [menu_import] = imports_of(db_session, application.bar_id)

    applicant_auth = {"Authorization": f"Bearer {supabase.token(sub=APPLICANT_SUBJECT)}"}
    [bar] = client.get("/api/me/bars", headers=applicant_auth).json()["items"]

    assert bar["activeMenuImport"] == {"menuImportId": str(menu_import.id), "status": "ready_for_review"}


def test_a_bar_with_a_menu_gets_a_partial_update(client, db_session, image_storage, auth, applicant):
    bar = make_bar(db_session)
    publish_menu(db_session, bar, [])
    application = make_application(db_session, applicant, bar)
    with_stored_photos(db_session, image_storage, application, count=1)

    approve(client, auth, application.id)

    [menu_import] = imports_of(db_session, bar.id)
    assert menu_import.mode == ImportMode.PARTIAL_UPDATE


def test_an_unfinished_import_is_left_alone(client, db_session, image_storage, auth, applicant):
    bar = make_bar(db_session)
    existing = MenuImport(
        idempotency_key="operator-upload",
        request_fingerprint="0" * 64,
        bar_id=bar.id,
        mode=ImportMode.FULL_REPLACE,
        status=ImportStatus.READY_FOR_REVIEW,
    )
    db_session.add(existing)
    application = make_application(db_session, applicant, bar)
    with_stored_photos(db_session, image_storage, application, count=1)

    response = approve(client, auth, application.id)

    assert response.status_code == 200
    assert [menu_import.id for menu_import in imports_of(db_session, bar.id)] == [existing.id]


def owner_application_review_photos(db_session, application):
    from app.models import BarOwnerApplicationMenuImage

    return list(
        db_session.scalars(
            select(BarOwnerApplicationMenuImage)
            .where(BarOwnerApplicationMenuImage.application_id == application.id)
            .order_by(BarOwnerApplicationMenuImage.image_order)
        )
    )


# ---- reject (3.11.8) ----


def test_rejects_with_a_reason_and_deletes_the_photos(client, db_session, image_storage, auth, applicant, operator):
    application = make_application(db_session, applicant, make_bar(db_session))
    with_stored_photos(db_session, image_storage, application)
    keys = [photo.storage_key for photo in owner_application_review_photos(db_session, application)]

    response = reject(client, auth, application.id, {"reason": "  매장을 확인할 수 없습니다. "})

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["rejectionReason"], body["reviewedAt"]) == (
        "rejected",
        "매장을 확인할 수 없습니다.",
        "2026-10-31T09:00:00Z",
    )
    assert body["menuPhotos"] == []
    db_session.refresh(application)
    assert application.reviewed_by_user_id == operator.id
    assert owner_application_review_photos(db_session, application) == []
    assert not any((image_storage.root / key).exists() for key in keys)
    assert current_owner(db_session, application.bar_id) is None


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, ("reason", "MISSING")),
        ({"reason": "   "}, ("reason", "BLANK")),
        ({"reason": "x" * 501}, ("reason", "STRING_TOO_LONG")),
    ],
)
def test_reason_rules(client, db_session, auth, applicant, body, expected):
    application = make_application(db_session, applicant)

    assert field_errors(reject(client, auth, application.id, body)) == [expected]


# ---- both decisions ----


@pytest.mark.parametrize("decide", [approve, reject])
@pytest.mark.parametrize(
    "status", [OwnerApplicationStatus.APPROVED, OwnerApplicationStatus.REJECTED, OwnerApplicationStatus.CANCELED]
)
def test_only_pending_applications_are_decided(client, db_session, auth, applicant, operator, decide, status):
    application = make_application(db_session, applicant, make_bar(db_session), status=status, reviewer=operator)

    response = decide(client, auth, application.id)

    assert error_of(response) == (409, "INVALID_APPLICATION_STATE")
    assert response.json()["error"]["details"] == {"status": status.value}


@pytest.mark.parametrize("decide", [approve, reject])
@pytest.mark.parametrize("application_id", [MISSING_ID, "not-a-uuid"])
def test_missing_applications(client, auth, decide, application_id):
    assert error_of(decide(client, auth, application_id)) == (404, "OWNER_APPLICATION_NOT_FOUND")


@pytest.mark.parametrize("decide", [approve, reject])
def test_a_temporary_operator_needs_a_users_row(client, db_session, token_for, applicant, decide):
    application = make_application(db_session, applicant, make_bar(db_session))
    headers = {"Authorization": f"Bearer {token_for('operator')}"}

    assert error_of(decide(client, headers, application.id)) == (404, "USER_NOT_FOUND")

    client.get("/api/me", headers=headers)
    assert decide(client, headers, application.id).status_code == 200
    db_session.refresh(application)
    assert application.reviewed_by_user_id is not None


def test_the_applicant_sees_the_decision(client, db_session, supabase, auth, applicant):
    application = make_application(db_session, applicant)
    reject(client, auth, application.id)

    applicant_auth = {"Authorization": f"Bearer {supabase.token(sub=APPLICANT_SUBJECT)}"}
    [mine] = client.get("/api/me/owner-applications", headers=applicant_auth).json()["items"]

    assert (mine["status"], mine["rejectionReason"]) == ("rejected", "사업자등록번호를 확인할 수 없습니다.")
    assert mine["businessVerification"] is None
    assert db_session.get(BarOwnerApplication, application.id).status == OwnerApplicationStatus.REJECTED
