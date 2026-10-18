# AI-generated with ChatGPT (Haeul Yang, 2026-10-04, PR #3, #9, #16, #19); Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-06, PR #14); Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-19). Reviewed by Haeul Yang and Jinwoo Park.
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deps import get_image_storage, get_menu_extractor
from app.api.router import api_router
from app.core.access_log import strip_query_strings_from_access_log
from app.core.auth_config import load_supabase_auth_settings
from app.core.errors import register_error_handlers
from app.core.security import warn_if_temporary_login_is_on
from app.core.version import get_version


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Check the extractor and storage settings at start-up (e.g. MENU_EXTRACTOR=gemini
    # without GEMINI_API_KEY, IMAGE_STORAGE=s3 without S3_BUCKET) instead of failing on
    # the first upload. The local defaults need nothing.
    get_menu_extractor()
    get_image_storage()
    # Invalid Supabase auth settings (e.g. HS256 allowed) stop the server; an unset SUPABASE_URL does not.
    load_supabase_auth_settings()
    # Leave a trace in the server log while anyone can get a token from POST /api/auth/temp-login.
    warn_if_temporary_login_is_on()
    # Pin the reported version to the code this process loaded.
    get_version()
    yield


# The customer's location arrives in query strings; keep it out of the access log.
strip_query_strings_from_access_log()

app = FastAPI(title="BottleMap API", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(api_router)
