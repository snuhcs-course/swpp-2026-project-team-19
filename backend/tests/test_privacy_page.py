"""The privacy policy page at /privacy (task P26): public, static, and under a strict policy of its own."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

PRIVACY_POLICY = "default-src 'none'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("path", ["/privacy", "/privacy/"])
def test_the_page_is_public_and_shows_its_effective_date_and_history(client, path):
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<html lang="ko">' in response.text
    assert '시행일: <time datetime="2026-11-28">' in response.text
    assert '<h3 id="history">변경 이력</h3>' in response.text
    assert '<link rel="stylesheet" href="/privacy/style.css">' in response.text
    # Nothing on the page runs: the policy below would block it anyway.
    assert "<script" not in response.text


def test_the_stylesheet_is_served(client):
    response = client.get("/privacy/style.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


@pytest.mark.parametrize("path", ["/privacy", "/privacy/style.css"])
def test_head_requests_are_answered(client, path):
    assert client.head(path).status_code == 200


@pytest.mark.parametrize("path", ["/privacy", "/privacy/style.css"])
def test_the_page_allows_only_its_own_stylesheet_and_is_not_cached(client, monkeypatch, path):
    # The Supabase project of the signed-in pages must not widen this page's policy.
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")

    headers = client.get(path).headers

    assert headers["content-security-policy"] == PRIVACY_POLICY
    assert headers["cache-control"] == "no-cache"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-content-type-options"] == "nosniff"


def test_other_paths_under_privacy_are_not_found(client):
    assert client.get("/privacy/index.html").status_code == 404


def test_the_page_is_not_in_the_api_document(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert not [path for path in paths if path.startswith("/privacy")]
