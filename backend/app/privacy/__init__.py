"""The privacy policy (task P26), a public static page at /privacy on the API's domain.

The Android app, the owner web and the store listing link here. The page is plain HTML and CSS kept in this
repository, so its history is the file's history; the effective date and the change history are in the page.
It needs no sign-in and runs no script, so it gets its own, stricter policy (`privacy_content_security_policy`).
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse
from starlette.responses import Response

from app.web_pages import add_page_headers, privacy_content_security_policy

PRIVACY_PATH = "/privacy"
STATIC_DIR = Path(__file__).resolve().parent / "static"

router = APIRouter(prefix=PRIVACY_PATH, include_in_schema=False)


def _file(name: str) -> Response:
    return add_page_headers(FileResponse(STATIC_DIR / name), policy=privacy_content_security_policy())


@router.api_route("", methods=["GET", "HEAD"])
@router.api_route("/", methods=["GET", "HEAD"])
def privacy_page() -> Response:
    return _file("index.html")


@router.api_route("/style.css", methods=["GET", "HEAD"])
def privacy_style() -> Response:
    return _file("style.css")


def mount_privacy(app: FastAPI) -> None:
    app.include_router(router)
