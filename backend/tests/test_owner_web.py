"""The owner web at /owner (task A9): the build's files, the page's headers, and what happens without a build.

Each test serves a small fake build from a temporary directory (`OWNER_WEB_DIR`), so the tests do not
depend on `owner-web/dist` being built in this checkout.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.owner_web import DEFAULT_BUILD_DIR, build_dir

SUPABASE_URL = "https://project-ref.supabase.co"
INDEX = '<!doctype html><title>BottleMap 사장님</title><script type="module" src="/owner/assets/index-abc123.js"></script>'
SCRIPT = "console.log('owner');"


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    (tmp_path / "assets" / "index-abc123.js").write_text(SCRIPT, encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    monkeypatch.setenv("OWNER_WEB_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("KAKAO_JAVASCRIPT_KEY", raising=False)
    return TestClient(app)


def read_config(client: TestClient) -> dict:
    response = client.get("/owner/config.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    prefix, suffix = "window.BOTTLEMAP_OWNER_CONFIG = ", ";\n"
    assert response.text.startswith(prefix) and response.text.endswith(suffix)
    return json.loads(response.text[len(prefix) : -len(suffix)])


def test_the_page_and_its_files_are_served(client, build):
    page = client.get("/owner/")
    script = client.get("/owner/assets/index-abc123.js")

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert page.text == INDEX
    assert script.status_code == 200
    assert script.text == SCRIPT
    assert "javascript" in script.headers["content-type"]
    assert client.get("/owner/favicon.svg").headers["content-type"].startswith("image/svg+xml")


def test_head_is_answered_like_get(client, build):
    response = client.head("/owner/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_owner_without_a_slash_redirects_so_relative_paths_resolve(client, build):
    response = client.get("/owner", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/owner/"


@pytest.mark.parametrize("path", ["/owner/menu", "/owner/bars/123/review", "/owner/menu/"])
def test_a_page_of_the_app_gets_the_index_so_the_browser_can_route(client, build, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.text == INDEX
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/owner/missing.js", "/owner/assets/index-old.js", "/owner/assets/missing.css"])
def test_a_missing_file_is_404(client, build, path):
    response = client.get(path)

    assert response.status_code == 404
    assert "content-security-policy" in response.headers


@pytest.mark.parametrize("path", ["/owner/..%2F..%2Fsecret.txt", "/owner/assets/..%2F..%2Fsecret.txt", "/owner//etc/hostname"])
def test_a_path_outside_the_build_is_never_served(client, build, path):
    (build.parent / "secret.txt").write_text("secret", encoding="utf-8")

    response = client.get(path)

    assert "secret" not in response.text
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        assert response.text == INDEX


def test_hashed_assets_are_cached_and_the_rest_is_revalidated(client, build):
    assert client.get("/owner/assets/index-abc123.js").headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/owner/").headers["cache-control"] == "no-cache"
    assert client.get("/owner/favicon.svg").headers["cache-control"] == "no-cache"
    assert client.get("/owner/config.js").headers["cache-control"] == "no-cache"


def test_the_page_allows_only_known_sources(client, build, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)

    for path in ("/owner/", "/owner/assets/index-abc123.js", "/owner/config.js", "/owner/menu"):
        headers = client.get(path).headers
        policy = headers["content-security-policy"]
        assert "default-src 'self'" in policy
        assert "script-src 'self' https://cdn.jsdelivr.net dapi.kakao.com *.kakaocdn.net *.daumcdn.net" in policy
        assert f"connect-src 'self' {SUPABASE_URL} dapi.kakao.com" in policy
        # Previews of the photos an owner picks are blob: URLs (owner-web/src/application/photos.ts).
        assert "img-src 'self' https: data: blob: " in policy
        assert "frame-ancestors 'none'" in policy
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("state", ["no directory", "no index"])
def test_without_a_build_the_page_says_it_is_not_ready_and_the_api_still_works(client, tmp_path, monkeypatch, state):
    if state == "no directory":
        monkeypatch.setenv("OWNER_WEB_DIR", str(tmp_path / "missing"))
    else:
        (tmp_path / "assets").mkdir()
        monkeypatch.setenv("OWNER_WEB_DIR", str(tmp_path))

    for path in ("/owner/", "/owner/menu", "/owner/assets/index-abc123.js"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["cache-control"] == "no-store"
        assert "content-security-policy" in response.headers
    assert read_config(client)["supabaseUrl"] is None
    assert client.get("/health").status_code == 200


def test_a_new_build_takes_effect_without_a_restart(client, build, tmp_path_factory, monkeypatch):
    assert client.get("/owner/").text == INDEX
    newer = tmp_path_factory.mktemp("newer")
    (newer / "index.html").write_text("<!doctype html><title>newer</title>", encoding="utf-8")
    monkeypatch.setenv("OWNER_WEB_DIR", str(newer))

    assert "newer" in client.get("/owner/").text


def test_the_build_directory_defaults_to_owner_web_dist(monkeypatch):
    monkeypatch.setenv("OWNER_WEB_DIR", "  ")

    assert build_dir() == DEFAULT_BUILD_DIR
    assert DEFAULT_BUILD_DIR.parts[-2:] == ("owner-web", "dist")
    assert (DEFAULT_BUILD_DIR.parent / "package.json").is_file()


def test_config_hands_out_the_public_settings(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL + "/")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", " sb_publishable_example ")
    monkeypatch.setenv("KAKAO_JAVASCRIPT_KEY", " kakao-js-key ")

    assert read_config(client) == {
        "supabaseUrl": SUPABASE_URL,
        "supabasePublishableKey": "sb_publishable_example",
        "kakaoJavascriptKey": "kakao-js-key",
    }


def test_owner_web_is_not_in_the_api_document():
    assert not [path for path in app.openapi()["paths"] if path.startswith("/owner")]
