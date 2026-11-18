"""The owner web (task A9): the bar management pages of the Android app for owners without an Android
device, served at /owner on the API's domain. Separate from the operator dashboard at /admin.

The pages are a React build (`owner-web/` in the repository). Deployment builds them in GitHub Actions
and puts the build on the server; `OWNER_WEB_DIR` names that directory, which defaults to
`owner-web/dist` in this checkout. The directory is looked up on every request, so the API starts and
serves everything else when no build is there, and a new build takes effect without a restart.

Like /admin it adds no API: `/owner/config.js` only hands the page the public settings, and every
permission check is the API's own (spec 2.2).
"""

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.responses import Response

from app.web_pages import NO_CACHE, add_page_headers, config_script

OWNER_WEB_PATH = "/owner"
DEFAULT_BUILD_DIR = Path(__file__).resolve().parents[3] / "owner-web" / "dist"
# Vite names these files after their content hash, so a changed file gets a new URL.
HASHED_ASSETS_DIR = "assets"
IMMUTABLE = "public, max-age=31536000, immutable"

NOT_BUILT_PAGE = """<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>BottleMap 사장님</title></head>
<body><p>사장님 페이지를 준비하고 있어요. 잠시 후 다시 열어 주세요.</p></body>
</html>
"""

router = APIRouter(prefix=OWNER_WEB_PATH, include_in_schema=False)


def build_dir() -> Path:
    configured = os.getenv("OWNER_WEB_DIR", "").strip()
    return Path(configured) if configured else DEFAULT_BUILD_DIR


@router.get("", include_in_schema=False)
def owner_web_without_slash() -> Response:
    # The page's files are relative to /owner/.
    return RedirectResponse(f"{OWNER_WEB_PATH}/", status_code=307)


@router.get("/config.js")
def owner_web_config() -> Response:
    return config_script("BOTTLEMAP_OWNER_CONFIG")


@router.api_route("/{path:path}", methods=["GET", "HEAD"])
def owner_web_page(path: str) -> Response:
    root = build_dir().resolve()
    index = root / "index.html"
    if not index.is_file():
        # Deployed before its first build: the page says so, and the API is not affected.
        return add_page_headers(HTMLResponse(NOT_BUILT_PAGE, status_code=503), cache_control="no-store")

    if path:
        target = (root / path).resolve()
        if target.is_relative_to(root) and target.is_file():
            hashed = target.parent == root / HASHED_ASSETS_DIR
            return add_page_headers(FileResponse(target), cache_control=IMMUTABLE if hashed else NO_CACHE)
        if "." in Path(path).name:
            # A missing file, not a page of the app.
            return add_page_headers(Response("Not Found", status_code=404, media_type="text/plain"))

    # Every other path is a page of the app, which routes in the browser.
    return add_page_headers(FileResponse(index), cache_control=NO_CACHE)


def mount_owner_web(app: FastAPI) -> None:
    app.include_router(router)
