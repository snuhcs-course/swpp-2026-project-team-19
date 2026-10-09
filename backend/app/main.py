# AI-generated with ChatGPT (Haeul Yang, 2026-10-04, PR #3, #9, #16, #19); Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-06, PR #14). Reviewed by Haeul Yang and Jinwoo Park.
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deps import get_image_storage, get_menu_extractor
from app.api.router import api_router
from app.core.errors import register_error_handlers
from app.core.version import get_version


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Check the extractor and storage settings at start-up (e.g. MENU_EXTRACTOR=gemini
    # without GEMINI_API_KEY, IMAGE_STORAGE=s3 without S3_BUCKET) instead of failing on
    # the first upload. The local defaults need nothing.
    get_menu_extractor()
    get_image_storage()
    # Pin the reported version to the code this process loaded.
    get_version()
    yield


app = FastAPI(title="BottleMap API", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(api_router)
