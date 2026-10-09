# AI-generated with ChatGPT (Haeul Yang, 2026-10-07, PR #17). Reviewed by Haeul Yang.
"""Temporary login and token checks. No database: /api/me only reads the token."""

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


def token(**changes):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "user-1",
        "user_type": "customer",
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(hours=1),
        **changes,
    }
    return jwt.encode(claims, SECRET, algorithm=TOKEN_ALGORITHM)


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


def test_valid_token(api):
    assert me(api, token()).json()["userType"] == "customer"


@pytest.mark.parametrize(
    "changes",
    [
        {"sub": "  "},
        {"user_type": "admin"},
        {"aud": "another-api"},
        {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    ],
)
def test_invalid_tokens_are_rejected(api, changes):
    response = me(api, token(**changes))

    assert error_of(response) == (401, "UNAUTHENTICATED")
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_tokens_are_rejected_when_auth_is_disabled(api, monkeypatch):
    monkeypatch.setenv("TEMP_AUTH_ENABLED", "false")

    assert error_of(me(api, token())) == (401, "UNAUTHENTICATED")


def test_tokens_cannot_be_checked_without_a_secret(api, monkeypatch):
    monkeypatch.setenv("TEMP_AUTH_JWT_SECRET", "")

    assert error_of(me(api, token())) == (503, "SERVICE_UNAVAILABLE")
