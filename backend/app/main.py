from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deps import get_menu_extractor
from app.api.router import api_router
from app.core.errors import register_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Check the extractor settings at start-up (e.g. MENU_EXTRACTOR=gemini without
    # GEMINI_API_KEY) instead of failing on the first upload. The mock needs nothing.
    get_menu_extractor()
    yield


app = FastAPI(title="BottleMap API", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(api_router)
