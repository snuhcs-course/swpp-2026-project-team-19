"""Supabase access-token checks (API spec, sections 3.1.2 and 3.1.5).

Tokens are signed in the test and verified against a JWKS served from memory (`supabase` fixture);
nothing calls Supabase.
"""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.auth_config import AuthConfigError
from tests.auth_support import SUPABASE_TEST_URL, connection_error, new_signing_key


def me(client, token):
    return client.get("/api/me", headers={"Authorization": f"Bearer {token}"})


def error_of(response):
    return response.status_code, response.json()["error"]["code"]


def assert_unauthenticated(response):
    assert error_of(response) == (401, "UNAUTHENTICATED")
    assert response.headers["WWW-Authenticate"] == "Bearer"


def assert_unavailable(response):
    assert error_of(response) == (503, "SERVICE_UNAVAILABLE")
    # Not a login problem: the app keeps the session and retries later.
    assert "WWW-Authenticate" not in response.headers


def test_valid_token_is_accepted(client, supabase):
    token = supabase.token(sub="0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10")

    response = me(client, token)

    assert response.status_code == 200
    assert response.json()["userType"] == "customer"
    assert supabase.requested_jwks_urls == [f"{SUPABASE_TEST_URL}/auth/v1/.well-known/jwks.json"]


def test_expired_token_is_rejected(client, supabase):
    now = int(time.time())

    assert_unauthenticated(me(client, supabase.token(iat=now - 3600, exp=now - 31)))


def test_bad_signature_is_rejected(client, supabase):
    # Same kid as the published key, signed by another private key.
    impostor = new_signing_key(supabase.key.kid)

    assert_unauthenticated(me(client, supabase.token(key=impostor)))


def test_unknown_key_id_is_rejected(client, supabase):
    assert_unauthenticated(me(client, supabase.token(key=new_signing_key("not-published"))))
    # One refetch looked for a rotated key before giving up.
    assert supabase.jwks.fetches == 2


def test_token_without_a_key_id_is_rejected(client, supabase):
    token = jwt.encode(
        jwt.decode(supabase.token(), options={"verify_signature": False}), supabase.key.private_key, algorithm="ES256"
    )

    assert_unauthenticated(me(client, token))


def test_wrong_issuer_is_rejected(client, supabase):
    assert_unauthenticated(me(client, supabase.token(iss="https://another.supabase.co/auth/v1")))


def test_wrong_audience_is_rejected(client, supabase):
    assert_unauthenticated(me(client, supabase.token(aud="anon")))


@pytest.mark.parametrize("claim", ["exp", "iat", "sub", "iss", "aud"])
def test_missing_claim_is_rejected(client, supabase, claim):
    assert_unauthenticated(me(client, supabase.token(**{claim: None})))


@pytest.mark.parametrize("subject", ["", "   ", 123])
def test_blank_subject_is_rejected(client, supabase, subject):
    assert_unauthenticated(me(client, supabase.token(sub=subject)))


def test_anonymous_session_is_rejected(client, supabase):
    assert_unauthenticated(me(client, supabase.token(is_anonymous=True)))


def test_hs256_token_is_rejected(client, supabase):
    claims = jwt.decode(supabase.token(), options={"verify_signature": False})
    token = jwt.encode(claims, "a-guessed-shared-secret-0123456789abcdef", algorithm="HS256", headers={"kid": "x"})

    assert_unauthenticated(me(client, token))
    assert supabase.jwks.fetches == 0


@pytest.mark.parametrize("token", ["not-a-jwt", "a.b.c"])
def test_malformed_token_is_rejected(client, supabase, token):
    assert_unauthenticated(me(client, token))


def test_clock_skew_within_leeway_is_accepted(client, supabase):
    now = int(time.time())

    issued_ahead = me(client, supabase.token(iat=now + 20))
    just_expired = me(client, supabase.token(iat=now - 3600, exp=now - 20))

    assert (issued_ahead.status_code, just_expired.status_code) == (200, 200)


def test_missing_supabase_url_is_a_server_error(client, supabase, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL")

    assert_unavailable(me(client, supabase.token()))


def test_invalid_supabase_settings_are_a_server_error(client, supabase, monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_ALGORITHMS", "HS256")

    assert_unavailable(me(client, supabase.token()))


def test_unreachable_jwks_is_a_server_error(client, supabase):
    supabase.jwks.error = connection_error()

    assert_unavailable(me(client, supabase.token()))


def test_supabase_token_is_checked_on_a_public_route(client, supabase):
    # GET /api/bars/{barId}/menu is public, but a token that is sent must be valid.
    now = int(time.time())
    expired = supabase.token(iat=now - 3600, exp=now - 60)

    response = client.get(
        "/api/bars/22222222-2222-4222-8222-222222222222/menu", headers={"Authorization": f"Bearer {expired}"}
    )

    assert_unauthenticated(response)


def test_server_start_fails_with_invalid_supabase_settings(monkeypatch):
    from app.main import app

    monkeypatch.setenv("SUPABASE_URL", SUPABASE_TEST_URL)
    monkeypatch.setenv("SUPABASE_JWT_ALGORITHMS", "ES256,HS256")

    with pytest.raises(AuthConfigError, match="SUPABASE_JWT_ALGORITHMS"):
        with TestClient(app):
            pass
