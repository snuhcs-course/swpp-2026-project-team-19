"""The operator web dashboard (task P45), served as static files at /admin on the API's domain.

The page signs in with Supabase Google login in the browser and calls the owner application APIs
of spec 3.11 with the access token, like the Android app. It adds no API: `/admin/config.js` only
hands the page the public Supabase settings, and the operator check is the API's own (2.2).
The headers and the config are shared with the owner web (`app.web_pages`).
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.web_pages import add_page_headers, config_script

ADMIN_PATH = "/admin"
STATIC_DIR = Path(__file__).resolve().parent / "static"

router = APIRouter(prefix=ADMIN_PATH, include_in_schema=False)


class AdminStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        return add_page_headers(await super().get_response(path, scope))


@router.get("/config.js")
def admin_config() -> Response:
    return config_script("BOTTLEMAP_ADMIN_CONFIG")


def mount_admin(app: FastAPI) -> None:
    # The route goes first so /admin/config.js is not looked up among the static files.
    app.include_router(router)
    app.mount(ADMIN_PATH, AdminStaticFiles(directory=STATIC_DIR, html=True), name="admin")
