"""The operator web dashboard (task P45), served as static files at /admin on the API's domain.

The page signs in with Supabase Google login in the browser and calls the owner application APIs
of spec 3.11 with the access token, like the Android app. It adds no API: `/admin/config.js` only
hands the page the public Supabase settings, and the operator check is the API's own (2.2).
"""

import json
import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.core.auth_config import load_supabase_auth_settings
from app.core.security import temporary_login_enabled

ADMIN_PATH = "/admin"
STATIC_DIR = Path(__file__).resolve().parent / "static"
# The supabase-js build index.html loads, pinned with Subresource Integrity.
SUPABASE_JS_ORIGIN = "https://cdn.jsdelivr.net"

router = APIRouter(prefix=ADMIN_PATH, include_in_schema=False)


def content_security_policy() -> str:
    settings = load_supabase_auth_settings()
    supabase = f" {settings.url}" if settings else ""
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' {SUPABASE_JS_ORIGIN}",
            "style-src 'self'",
            # Menu photos are signed object-storage URLs (S3) or /media paths on this server (local).
            "img-src 'self' https: data:",
            f"connect-src 'self'{supabase}",
            "frame-ancestors 'none'",
            "base-uri 'none'",
            "form-action 'self'",
        ]
    )


def add_admin_headers(response: Response) -> Response:
    response.headers["Content-Security-Policy"] = content_security_policy()
    # Signed photo URLs and the OAuth callback must not leak through the Referer header.
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    # A new deploy takes effect on the next load.
    response.headers["Cache-Control"] = "no-cache"
    return response


class AdminStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        return add_admin_headers(await super().get_response(path, scope))


@router.get("/config.js")
def admin_config() -> Response:
    """The public settings the page needs: the Supabase project URL and publishable (anon) key."""
    settings = load_supabase_auth_settings()
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
    config = {
        "supabaseUrl": settings.url if settings and key else None,
        "supabasePublishableKey": key if settings and key else None,
        "tempLoginEnabled": temporary_login_enabled(),
    }
    body = f"window.BOTTLEMAP_ADMIN_CONFIG = {json.dumps(config)};\n"
    return add_admin_headers(Response(body, media_type="text/javascript"))


def mount_admin(app: FastAPI) -> None:
    # The route goes first so /admin/config.js is not looked up among the static files.
    app.include_router(router)
    app.mount(ADMIN_PATH, AdminStaticFiles(directory=STATIC_DIR, html=True), name="admin")
