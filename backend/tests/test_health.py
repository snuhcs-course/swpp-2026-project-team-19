# AI-generated with ChatGPT (Haeul Yang, 2026-10-07, PR #19). Reviewed by Haeul Yang.
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.core import version
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_health_reports_the_checked_out_commit():
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=BACKEND_DIR, capture_output=True, text=True, check=True
    ).stdout.strip()

    body = TestClient(app).get("/health").json()

    assert body["status"] == "ok"
    assert len(body["version"]) >= 7 and head.startswith(body["version"])


def test_version_is_null_without_a_git_checkout(tmp_path, monkeypatch):
    assert version.read_commit(tmp_path) is None

    monkeypatch.setattr(version, "BACKEND_DIR", tmp_path)
    version.get_version.cache_clear()
    try:
        assert TestClient(app).get("/health").json() == {"status": "ok", "version": None}
    finally:
        version.get_version.cache_clear()


def test_version_is_null_when_git_is_missing(monkeypatch):
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)

    assert version.read_commit(BACKEND_DIR) is None
