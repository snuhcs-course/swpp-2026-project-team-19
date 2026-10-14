# AI-generated with ChatGPT (Haeul Yang, 2026-10-07, PR #17); Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-14). Reviewed by Haeul Yang.
"""Temporary login and temporary-token checks (API spec, section 3.1.3).

The role of a temporary token comes from TEMP_AUTH_USER_TYPE at request time, not from the token.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.tokens import TOKEN_ALGORITHM, TOKEN_AUDIENCE, TOKEN_ISSUER
from app.main import app

SECRET = "test-secret-for-temporary-auth-0123456789"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("TEMP_AUTH_ENABLED", "true")
    monkeypatch.setenv("TEMP_AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("TEMP_AUTH_USER_TYPE", "operator")
    return TestClient(app)


def token(secret=SECRET, **changes):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "user-1",
        "user_type": "customer",  # still issued for older clients, but ignored
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(hours=1),
        **changes,
    }
    claims = {name: value for name, value in claims.items() if value is not None}
    return jwt.encode(claims, secret, algorithm=TOKEN_ALGORITHM)


def me(api, access_token):
    return api.get("/api/me", headers={"Authorization": f"Bearer {access_token}"})


def error_of(response):
    return response.status_code, response.json()["error"]["code"]


# ---- POST /api/auth/temp-login ----


def test_temp_login_token_identifies_the_configured_user_type(api):
    login = api.post("/api/auth/temp-login")

    assert login.status_code == 200
    body = login.json()
    assert (body["tokenType"], body["expiresIn"]) == ("bearer", 3 * 60 * 60)
    assert me(api, body["accessToken"]).json() == {
        "userId": "local-dev-user",
        "email": "local-dev@example.invalid",
        "displayName": "Local development user",
        "userType": "operator",
    }


def test_temp_login_is_hidden_when_disabled(api, monkeypatch):
    monkeypatch.setenv("TEMP_AUTH_ENABLED", "false")

    assert error_of(api.post("/api/auth/temp-login")) == (404, "NOT_FOUND")


@pytest.mark.parametrize(
    ("name", "value"),
    [("TEMP_AUTH_JWT_SECRET", "too-short"), ("TEMP_AUTH_USER_TYPE", "admin")],
)
def test_temp_login_refuses_a_bad_configuration(api, monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    assert error_of(api.post("/api/auth/temp-login")) == (503, "SERVICE_UNAVAILABLE")


# ---- token checks (GET /api/me) ----


def test_role_comes_from_the_setting_not_the_token(api):
    # token() says customer; the server is set to operator.
    assert me(api, token()).json()["userType"] == "operator"


@pytest.mark.parametrize(
    "changes",
    [
        {"sub": "  "},
        {"aud": "another-api"},
        {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        {"iat": None},
        {"secret": "another-secret-for-temporary-auth-0123456789"},
    ],
    ids=["blank-sub", "wrong-aud", "expired", "no-iat", "other-secret"],
)
def test_invalid_tokens_are_rejected(api, changes):
    response = me(api, token(**changes))

    assert error_of(response) == (401, "UNAUTHENTICATED")
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("authorization", [None, "Basic dXNlcjpwYXNz", "Bearer"])
def test_a_missing_bearer_token_is_rejected(api, authorization):
    headers = {"Authorization": authorization} if authorization else {}

    response = api.get("/api/me", headers=headers)

    assert error_of(response) == (401, "UNAUTHENTICATED")
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_tokens_are_rejected_when_auth_is_disabled(api, monkeypatch):
    monkeypatch.setenv("TEMP_AUTH_ENABLED", "false")

    assert error_of(me(api, token())) == (401, "UNAUTHENTICATED")


def test_tokens_cannot_be_checked_without_a_secret(api, monkeypatch):
    monkeypatch.setenv("TEMP_AUTH_JWT_SECRET", "")

    assert error_of(me(api, token())) == (503, "SERVICE_UNAVAILABLE")


def test_tokens_are_not_accepted_with_a_bad_user_type_setting(api, monkeypatch):
    monkeypatch.setenv("TEMP_AUTH_USER_TYPE", "admin")

    response = me(api, token())

    assert error_of(response) == (503, "SERVICE_UNAVAILABLE")
    assert "WWW-Authenticate" not in response.headers


# ---- the role on operator routes (needs the test database) ----


def test_temporary_role_follows_the_setting(client, token_for, monkeypatch):
    customer_token = token_for("customer")
    headers = {"Authorization": f"Bearer {customer_token}"}

    before = client.get("/api/catalog/brands", params={"query": "x"}, headers=headers)
    monkeypatch.setenv("TEMP_AUTH_USER_TYPE", "operator")
    after = client.get("/api/catalog/brands", params={"query": "x"}, headers=headers)

    assert error_of(before) == (403, "FORBIDDEN")
    assert after.status_code == 200


def test_temporary_operator_needs_no_user_row(client, token_for):
    # The Android app calls operator APIs right after temp-login, without GET /api/me.
    operator_token = token_for("operator")

    response = client.get(
        "/api/catalog/brands", params={"query": "x"}, headers={"Authorization": f"Bearer {operator_token}"}
    )

    assert response.status_code == 200
