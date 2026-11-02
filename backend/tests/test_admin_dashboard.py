"""The operator dashboard's static files at /admin (task P45). The page itself calls only spec APIs."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

SUPABASE_URL = "https://project-ref.supabase.co"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    return TestClient(app)


def read_config(client: TestClient) -> dict:
    response = client.get("/admin/config.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    prefix, suffix = "window.BOTTLEMAP_ADMIN_CONFIG = ", ";\n"
    assert response.text.startswith(prefix) and response.text.endswith(suffix)
    return json.loads(response.text[len(prefix) : -len(suffix)])


def test_the_page_and_its_files_are_served(client):
    page = client.get("/admin/")

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert '<script src="app.js" defer></script>' in page.text
    assert client.get("/admin/app.js").status_code == 200
    assert client.get("/admin/style.css").status_code == 200


def test_admin_without_a_slash_redirects_so_relative_paths_resolve(client):
    response = client.get("/admin", follow_redirects=False)

    assert response.status_code in (301, 307)
    assert response.headers["location"].endswith("/admin/")


def test_the_page_is_not_cached_and_allows_only_known_sources(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)

    for path in ("/admin/", "/admin/app.js", "/admin/config.js"):
        headers = client.get(path).headers
        policy = headers["content-security-policy"]
        assert "script-src 'self' https://cdn.jsdelivr.net" in policy
        assert f"connect-src 'self' {SUPABASE_URL}" in policy
        assert "frame-ancestors 'none'" in policy
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["cache-control"] == "no-cache"


def test_the_policy_allows_no_supabase_origin_without_supabase_url(client):
    assert "connect-src 'self';" in client.get("/admin/").headers["content-security-policy"]


def test_a_missing_file_is_404(client):
    assert client.get("/admin/missing.js").status_code == 404


def test_config_hands_out_the_public_supabase_settings(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL + "/")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", " sb_publishable_example ")

    assert read_config(client) == {
        "supabaseUrl": SUPABASE_URL,
        "supabasePublishableKey": "sb_publishable_example",
    }


@pytest.mark.parametrize(
    "env",
    [{"SUPABASE_URL": SUPABASE_URL}, {"SUPABASE_PUBLISHABLE_KEY": "sb_publishable_example"}, {}],
    ids=["no key", "no url", "neither"],
)
def test_config_turns_google_login_off_without_both_settings(client, monkeypatch, env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    config = read_config(client)

    assert config["supabaseUrl"] is None and config["supabasePublishableKey"] is None


def test_admin_is_not_in_the_api_document():
    assert not [path for path in app.openapi()["paths"] if path.startswith("/admin")]
