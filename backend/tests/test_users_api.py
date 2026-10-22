# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-15, 2026-10-23). Reviewed by Haeul Yang.
"""GET /api/me: creating and syncing the BottleMap user (API spec, section 3.2)."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.security import Principal
from app.models import User, UserType
from app.services.users import sync_current_user

SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"


def me(client, token):
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    return response.json()


def users_with_subject(db_session, subject):
    return db_session.scalar(select(func.count()).select_from(User).where(User.auth_subject == subject))


def add_user(db_session, subject, email=None, display_name=None):
    user = User(auth_subject=subject, email=email, display_name=display_name)
    db_session.add(user)
    db_session.flush()
    return user


def test_first_call_creates_a_customer(client, supabase, db_session):
    body = me(client, supabase.token(sub=SUBJECT))

    user = db_session.scalars(select(User).where(User.auth_subject == SUBJECT)).one()
    assert UUID(body["userId"]) == user.id
    assert body["userId"] != SUBJECT
    assert body == {
        "userId": str(user.id),
        "email": "user@example.com",
        "displayName": "홍길동",
        "userType": "customer",
        "updatedAt": body["updatedAt"],
    }
    assert body["updatedAt"].endswith("Z")


def test_later_calls_return_the_same_user(client, supabase, db_session):
    first = me(client, supabase.token(sub=SUBJECT))
    second = me(client, supabase.token(sub=SUBJECT))

    assert first["userId"] == second["userId"]
    assert users_with_subject(db_session, SUBJECT) == 1


def test_creating_an_existing_user_keeps_one_row(db_session):
    existing = add_user(db_session, SUBJECT, email="user@example.com", display_name="기존 이름")
    principal = Principal("supabase", SUBJECT, {"sub": SUBJECT, "email": "user@example.com"})

    user = sync_current_user(db_session, principal)

    assert user.id == existing.id
    assert users_with_subject(db_session, SUBJECT) == 1


def test_email_follows_the_token(client, supabase):
    me(client, supabase.token(sub=SUBJECT, email="old@example.com"))

    body = me(client, supabase.token(sub=SUBJECT, email=" new@example.com "))

    assert body["email"] == "new@example.com"


@pytest.mark.parametrize("email", [None, "", "   ", 42, "a" * 250 + "@x.com"])
def test_missing_email_is_null(client, supabase, email):
    body = me(client, supabase.token(sub=SUBJECT, email=email))

    assert body["email"] is None


def test_taken_email_is_null(client, supabase, db_session):
    add_user(db_session, "someone-else", email="user@example.com")

    body = me(client, supabase.token(sub=SUBJECT, email="user@example.com"))

    assert body["email"] is None


def test_email_taken_later_clears_the_old_email(client, supabase, db_session):
    me(client, supabase.token(sub=SUBJECT, email="mine@example.com"))
    add_user(db_session, "someone-else", email="theirs@example.com")

    body = me(client, supabase.token(sub=SUBJECT, email="theirs@example.com"))

    assert body["email"] is None


def test_long_name_is_cut_to_20_characters(client, supabase):
    name = "  " + "가나다라마바사아자차카타파하" * 2 + "  "

    body = me(client, supabase.token(sub=SUBJECT, user_metadata={"name": name}))

    assert body["displayName"] == name.strip()[:20]
    assert len(body["displayName"]) == 20


@pytest.mark.parametrize("metadata", [None, {}, {"name": "   "}, {"name": 7}, "not-an-object"])
def test_missing_name_is_null(client, supabase, metadata):
    body = me(client, supabase.token(sub=SUBJECT, user_metadata=metadata))

    assert body["displayName"] is None


def test_display_name_is_not_overwritten(client, supabase, db_session):
    me(client, supabase.token(sub=SUBJECT))
    user = db_session.scalars(select(User).where(User.auth_subject == SUBJECT)).one()
    user.display_name = "바꾼 이름"
    db_session.flush()

    body = me(client, supabase.token(sub=SUBJECT, user_metadata={"name": "Google 이름"}))

    assert body["displayName"] == "바꾼 이름"


def test_operator_set_in_the_database_is_reported(client, supabase, db_session):
    me(client, supabase.token(sub=SUBJECT))
    db_session.scalars(select(User).where(User.auth_subject == SUBJECT)).one().user_type = UserType.OPERATOR
    db_session.flush()

    assert me(client, supabase.token(sub=SUBJECT))["userType"] == "operator"


def test_temporary_user_gets_a_row(client, token_for, db_session):
    body = me(client, token_for("operator"))

    user = db_session.scalars(select(User).where(User.auth_subject == "local-dev-user")).one()
    assert (body["userId"], body["userType"], user.user_type) == (str(user.id), "operator", UserType.OPERATOR)


def test_temporary_user_row_follows_the_setting(client, token_for, db_session, monkeypatch):
    token = token_for("operator")
    me(client, token)

    monkeypatch.setenv("TEMP_AUTH_USER_TYPE", "customer")
    body = me(client, token)

    user = db_session.scalars(select(User).where(User.auth_subject == "local-dev-user")).one()
    assert (body["userType"], user.user_type) == ("customer", UserType.CUSTOMER)


# ---- updatedAt is when the stored user last changed (spec 3.2) ----

# Not UTC and with microseconds, so the comparison also covers the string format.
EARLIER = datetime(2026, 10, 4, 18, 15, 30, 123456, tzinfo=timezone(timedelta(hours=9)))
EARLIER_TEXT = "2026-10-04T09:15:30.123456Z"


def stored_user_changed_at(db_session, subject, when):
    user = db_session.scalars(select(User).where(User.auth_subject == subject)).one()
    user.updated_at = when
    db_session.flush()


@pytest.mark.parametrize(
    "claims",
    [{}, {"email": " user@example.com "}, {"user_metadata": {"name": "Google 이름"}}],
    ids=["same token", "same email with spaces", "another Google name"],
)
def test_a_call_that_changes_nothing_keeps_updated_at(client, supabase, db_session, claims):
    # The app calls GET /api/me on every start; that alone is not a change.
    me(client, supabase.token(sub=SUBJECT))
    stored_user_changed_at(db_session, SUBJECT, EARLIER)

    body = me(client, supabase.token(sub=SUBJECT, **claims))

    assert body["updatedAt"] == EARLIER_TEXT


@pytest.mark.parametrize(
    "email",
    ["new@example.com", None],
    ids=["another email", "email removed from the token"],
)
def test_an_email_change_moves_updated_at(client, supabase, db_session, email):
    me(client, supabase.token(sub=SUBJECT, email="old@example.com"))
    stored_user_changed_at(db_session, SUBJECT, EARLIER)

    body = me(client, supabase.token(sub=SUBJECT, email=email))

    assert body["email"] == email
    assert datetime.fromisoformat(body["updatedAt"]) > EARLIER


def test_an_email_cleared_because_another_user_took_it_moves_updated_at(client, supabase, db_session):
    me(client, supabase.token(sub=SUBJECT, email="mine@example.com"))
    stored_user_changed_at(db_session, SUBJECT, EARLIER)
    add_user(db_session, "someone-else", email="theirs@example.com")

    body = me(client, supabase.token(sub=SUBJECT, email="theirs@example.com"))

    assert body["email"] is None
    assert datetime.fromisoformat(body["updatedAt"]) > EARLIER


def test_a_temporary_role_change_moves_updated_at(client, token_for, db_session, monkeypatch):
    token = token_for("operator")
    me(client, token)
    stored_user_changed_at(db_session, "local-dev-user", EARLIER)
    assert me(client, token)["updatedAt"] == EARLIER_TEXT

    monkeypatch.setenv("TEMP_AUTH_USER_TYPE", "customer")
    body = me(client, token)

    assert body["userType"] == "customer"
    assert datetime.fromisoformat(body["updatedAt"]) > EARLIER
