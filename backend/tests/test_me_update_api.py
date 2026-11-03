"""PATCH /api/me: changing the display name (API spec, section 3.3)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import User, UserType
from tests.test_users_api import me, users_with_subject

SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"

# Not UTC and with microseconds, so the comparison also covers the string format.
EARLIER = datetime(2026, 10, 4, 18, 15, 30, 123456, tzinfo=timezone(timedelta(hours=9)))
EARLIER_TEXT = "2026-10-04T09:15:30.123456Z"


def patch_me(client, token, body):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.patch("/api/me", headers=headers, json=body)


def stored_user(db_session, subject=SUBJECT) -> User:
    return db_session.scalars(select(User).where(User.auth_subject == subject)).one()


def stored_user_changed_at(db_session, when, subject=SUBJECT):
    stored_user(db_session, subject).updated_at = when
    db_session.flush()


def error(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def field_errors(response) -> list[tuple[str, str]]:
    assert error(response) == (422, "VALIDATION_FAILED"), response.text
    return [(e["path"], e["code"]) for e in response.json()["error"]["fieldErrors"]]


# ---- changing the name ----


def test_the_name_is_trimmed_and_saved(client, supabase, db_session):
    token = supabase.token(sub=SUBJECT)
    before = me(client, token)
    stored_user_changed_at(db_session, EARLIER)

    response = patch_me(client, token, {"displayName": "  메뉴 검수 담당자  "})

    assert response.status_code == 200
    body = response.json()
    # The same format as GET /api/me; only the name and the change time differ.
    assert body == {**before, "displayName": "메뉴 검수 담당자", "updatedAt": body["updatedAt"]}
    assert datetime.fromisoformat(body["updatedAt"]) > EARLIER
    assert stored_user(db_session).display_name == "메뉴 검수 담당자"


def test_a_later_get_me_keeps_the_new_name(client, supabase):
    me(client, supabase.token(sub=SUBJECT))
    patch_me(client, supabase.token(sub=SUBJECT), {"displayName": "새 이름"})

    body = me(client, supabase.token(sub=SUBJECT, user_metadata={"name": "Google 이름"}))

    assert body["displayName"] == "새 이름"


@pytest.mark.parametrize(
    ("sent", "saved"),
    [
        ("가", "가"),
        ("가" * 20, "가" * 20),
        (" " + "a" * 20 + " ", "a" * 20),
        # 20 code points, but 40 UTF-16 units (Kotlin's String.length).
        ("🥃" * 20, "🥃" * 20),
    ],
    ids=["one character", "20 Hangul", "20 after trimming", "20 emoji"],
)
def test_names_up_to_20_characters_are_accepted(client, supabase, db_session, sent, saved):
    me(client, supabase.token(sub=SUBJECT))

    response = patch_me(client, supabase.token(sub=SUBJECT), {"displayName": sent})

    assert response.status_code == 200, response.text
    assert response.json()["displayName"] == saved
    assert stored_user(db_session).display_name == saved


def test_the_same_name_keeps_updated_at(client, supabase, db_session):
    token = supabase.token(sub=SUBJECT)
    me(client, token)
    stored_user_changed_at(db_session, EARLIER)

    response = patch_me(client, token, {"displayName": " 홍길동 "})

    assert response.status_code == 200
    assert response.json()["displayName"] == "홍길동"
    assert response.json()["updatedAt"] == EARLIER_TEXT


def test_the_email_is_not_synced(client, supabase, db_session):
    me(client, supabase.token(sub=SUBJECT, email="old@example.com"))

    response = patch_me(client, supabase.token(sub=SUBJECT, email="new@example.com"), {"displayName": "새 이름"})

    assert response.json()["email"] == "old@example.com"
    assert stored_user(db_session).email == "old@example.com"


def test_only_the_callers_name_changes(client, supabase, db_session):
    me(client, supabase.token(sub=SUBJECT))
    me(client, supabase.token(sub="someone-else", email="other@example.com"))

    patch_me(client, supabase.token(sub=SUBJECT), {"displayName": "새 이름"})

    assert stored_user(db_session, "someone-else").display_name == "홍길동"


def test_an_operator_stays_an_operator(client, supabase, db_session):
    me(client, supabase.token(sub=SUBJECT))
    stored_user(db_session).user_type = UserType.OPERATOR
    db_session.flush()

    response = patch_me(client, supabase.token(sub=SUBJECT), {"displayName": "운영자"})

    assert response.json()["userType"] == "operator"


def test_a_temporary_user_with_a_row_can_change_the_name(client, token_for):
    token = token_for("operator")
    me(client, token)

    response = patch_me(client, token, {"displayName": "로컬 운영자"})

    assert response.status_code == 200
    assert response.json()["displayName"] == "로컬 운영자"
    assert response.json()["userType"] == "operator"


# ---- validation ----


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, [("displayName", "MISSING")]),
        ({"displayName": ""}, [("displayName", "BLANK")]),
        ({"displayName": "   "}, [("displayName", "BLANK")]),
        ({"displayName": "가" * 21}, [("displayName", "STRING_TOO_LONG")]),
        ({"displayName": " " + "a" * 21 + " "}, [("displayName", "STRING_TOO_LONG")]),
        ({"displayName": "🥃" * 21}, [("displayName", "STRING_TOO_LONG")]),
        ({"displayName": None}, [("displayName", "STRING_TYPE")]),
        ({"displayName": 12}, [("displayName", "STRING_TYPE")]),
        ({"displayName": "홍\n길동"}, [("displayName", "INVALID_CHARACTER")]),
        ({"displayName": "홍\t길동"}, [("displayName", "INVALID_CHARACTER")]),
        ({"displayName": "\n홍길동"}, [("displayName", "INVALID_CHARACTER")]),
        ({"displayName": "홍길동\n"}, [("displayName", "INVALID_CHARACTER")]),
        ({"displayName": "\t홍길동 "}, [("displayName", "INVALID_CHARACTER")]),
        ({"displayName": "새 이름", "email": "new@example.com"}, [("email", "EXTRA_FORBIDDEN")]),
        ({"displayName": "새 이름", "userType": "operator"}, [("userType", "EXTRA_FORBIDDEN")]),
    ],
    ids=[
        "missing",
        "empty",
        "only spaces",
        "21 characters",
        "21 after trimming",
        "21 emoji",
        "null",
        "a number",
        "a line break",
        "a tab",
        "a leading line break",
        "a trailing line break",
        "a leading tab",
        "email",
        "userType",
    ],
)
def test_invalid_requests_change_nothing(client, supabase, db_session, body, expected):
    token = supabase.token(sub=SUBJECT)
    me(client, token)
    stored_user_changed_at(db_session, EARLIER)

    response = patch_me(client, token, body)

    assert field_errors(response) == expected
    user = stored_user(db_session)
    assert (user.display_name, user.email, user.user_type) == ("홍길동", "user@example.com", UserType.CUSTOMER)
    assert user.updated_at == EARLIER


# ---- the caller ----


def test_a_user_without_a_row_is_not_found(client, supabase, db_session):
    response = patch_me(client, supabase.token(sub=SUBJECT), {"displayName": "새 이름"})

    assert error(response) == (404, "USER_NOT_FOUND")
    assert users_with_subject(db_session, SUBJECT) == 0


def test_a_temporary_operator_without_a_row_is_not_found(client, token_for, db_session):
    response = patch_me(client, token_for("operator"), {"displayName": "로컬 운영자"})

    assert error(response) == (404, "USER_NOT_FOUND")
    assert users_with_subject(db_session, "local-dev-user") == 0


def test_validation_comes_before_the_users_row(client, supabase):
    response = patch_me(client, supabase.token(sub=SUBJECT), {"displayName": ""})

    assert field_errors(response) == [("displayName", "BLANK")]


@pytest.mark.parametrize("body", [{"displayName": "새 이름"}, {"displayName": ""}], ids=["valid", "invalid"])
def test_a_guest_is_unauthenticated(client, body):
    response = patch_me(client, None, body)

    assert error(response) == (401, "UNAUTHENTICATED")
    assert response.headers["WWW-Authenticate"] == "Bearer"
