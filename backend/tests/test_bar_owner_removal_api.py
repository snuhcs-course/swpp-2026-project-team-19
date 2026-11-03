"""DELETE /api/bars/{barId}/owner: an operator removes a bar's owner (API spec 3.11.10).

Who may call it is also covered by test_route_permissions.py. That a request of the former owner which
takes the bar lock after the removal gets 403 is covered by each such API's own tests ("an owner revoked
before the lock is forbidden"); here the removal is shown to take that lock.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import event, func, select

from app.api import deps
from app.main import app
from app.models import (
    BarOwner,
    BarOwnerApplication,
    BarStatus,
    ImportMode,
    ImportStatus,
    MenuImport,
    OwnerApplicationStatus,
    UserType,
)
from tests.factories import make_application, make_bar, make_owner, make_user

OPERATOR_SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"
OWNER_SUBJECT = "5d1c2b3a-0000-4000-8000-000000000002"
MISSING_ID = "99999999-9999-4999-8999-999999999999"
NOW = datetime(2026, 11, 3, 9, tzinfo=timezone.utc)


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
def owner_user(db_session):
    return make_user(db_session, OWNER_SUBJECT)


@pytest.fixture
def owner_auth(supabase, owner_user):
    return {"Authorization": f"Bearer {supabase.token(sub=OWNER_SUBJECT)}"}


@pytest.fixture
def bar(db_session):
    return make_bar(db_session, "관악 위스키 바")


@pytest.fixture
def ownership(db_session, bar, owner_user, operator):
    return make_owner(db_session, owner_user, bar, operator)


def remove(client, headers, bar_id):
    return client.delete(f"/api/bars/{bar_id}/owner", headers=headers)


def error_of(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def current_owner(db_session, bar_id) -> BarOwner | None:
    return db_session.scalar(select(BarOwner).where(BarOwner.bar_id == bar_id, BarOwner.revoked_at.is_(None)))


def ownerships_of(db_session, bar_id) -> int:
    return db_session.scalar(select(func.count()).select_from(BarOwner).where(BarOwner.bar_id == bar_id))


# ---- removing the owner ----


def test_removes_the_current_owner_and_keeps_the_record(client, db_session, auth, bar, ownership, operator):
    response = remove(client, auth, bar.id)

    assert response.status_code == 204
    assert response.content == b""
    db_session.refresh(ownership)
    assert (ownership.revoked_at, ownership.revoked_by_user_id) == (NOW, operator.id)
    assert current_owner(db_session, bar.id) is None
    assert ownerships_of(db_session, bar.id) == 1
    application = db_session.get(BarOwnerApplication, ownership.application_id)
    db_session.refresh(application)
    assert application.status == OwnerApplicationStatus.APPROVED


def test_the_former_owner_no_longer_manages_the_bar(client, auth, owner_auth, bar, ownership):
    assert client.get(f"/api/bars/{bar.id}", headers=owner_auth).status_code == 200

    remove(client, auth, bar.id)

    assert error_of(client.get(f"/api/bars/{bar.id}", headers=owner_auth)) == (403, "FORBIDDEN")
    assert client.get("/api/me/bars", headers=owner_auth).json() == {"items": []}
    assert client.get(f"/api/bars/{bar.id}", headers=auth).json()["owner"] is None
    [found] = client.get("/api/search/bar-names", params={"query": "관악"}).json()["items"]
    assert found["hasOwner"] is False


def test_the_bar_can_get_an_owner_again(client, db_session, auth, bar, ownership, owner_user, operator):
    remove(client, auth, bar.id)
    # The former owner applies again; another person's application would be approved the same way.
    application = make_application(db_session, owner_user, bar)

    response = client.post(f"/api/owner-applications/{application.id}/approve", headers=auth)

    assert response.status_code == 200, response.text
    assert current_owner(db_session, bar.id).application_id == application.id
    assert ownerships_of(db_session, bar.id) == 2


def test_only_that_bar_loses_its_owner(client, db_session, auth, bar, ownership, owner_user, operator):
    other_bar = make_bar(db_session, "Other Bar")
    other_ownership = make_owner(db_session, owner_user, other_bar, operator)

    remove(client, auth, bar.id)

    assert current_owner(db_session, other_bar.id).id == other_ownership.id


def test_an_inactive_bar_can_lose_its_owner(client, db_session, auth, bar, ownership):
    bar.status = BarStatus.INACTIVE
    db_session.flush()

    assert remove(client, auth, bar.id).status_code == 204
    assert current_owner(db_session, bar.id) is None


def test_an_unfinished_menu_import_stays(client, db_session, auth, bar, ownership):
    menu_import = MenuImport(
        idempotency_key="owner-import",
        request_fingerprint="0" * 64,
        bar_id=bar.id,
        mode=ImportMode.FULL_REPLACE,
        status=ImportStatus.READY_FOR_REVIEW,
    )
    db_session.add(menu_import)
    db_session.flush()

    remove(client, auth, bar.id)

    db_session.refresh(menu_import)
    assert menu_import.status == ImportStatus.READY_FOR_REVIEW
    assert client.get(f"/api/bars/{bar.id}", headers=auth).json()["activeMenuImport"]["menuImportId"] == str(
        menu_import.id
    )


def test_removal_locks_the_bar(client, db_session, auth, bar, ownership):
    statements = []

    def listen(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(db_session.get_bind(), "before_cursor_execute", listen)
    try:
        assert remove(client, auth, bar.id).status_code == 204
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", listen)

    locked = [s for s in statements if "FOR UPDATE" in s]
    assert any("FROM bars" in s for s in locked)


# ---- errors, in the order they are checked ----


def test_sending_it_again_finds_no_owner(client, db_session, auth, bar, ownership):
    assert remove(client, auth, bar.id).status_code == 204

    assert error_of(remove(client, auth, bar.id)) == (404, "BAR_OWNER_NOT_FOUND")
    db_session.refresh(ownership)
    assert ownership.revoked_at == NOW


def test_a_bar_without_an_owner(client, auth, bar):
    assert error_of(remove(client, auth, bar.id)) == (404, "BAR_OWNER_NOT_FOUND")


@pytest.mark.parametrize("bar_id", [MISSING_ID, "not-a-uuid"], ids=["missing", "malformed"])
def test_a_missing_bar_is_not_found(client, auth, bar_id):
    response = remove(client, auth, bar_id)

    assert error_of(response) == (404, "BAR_NOT_FOUND")
    assert response.json()["error"]["details"] == {"barId": bar_id}


@pytest.mark.parametrize("bar_id", ["target", MISSING_ID], ids=["the owned bar", "a missing bar"])
def test_an_operator_without_a_users_row_is_not_found(client, db_session, token_for, bar, ownership, bar_id):
    # A temporary-login operator has no users row until GET /api/me, and the revoker must be recorded.
    headers = {"Authorization": f"Bearer {token_for('operator')}"}

    response = remove(client, headers, bar.id if bar_id == "target" else bar_id)

    assert error_of(response) == (404, "USER_NOT_FOUND")
    assert current_owner(db_session, bar.id).id == ownership.id


def test_the_owner_cannot_remove_themselves(client, db_session, owner_auth, bar, ownership):
    assert error_of(remove(client, owner_auth, bar.id)) == (403, "FORBIDDEN")
    assert current_owner(db_session, bar.id).id == ownership.id
