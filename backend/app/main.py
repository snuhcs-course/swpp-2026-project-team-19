import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deps import get_image_storage, get_matching_llm_layer, get_menu_extractor
from app.api.router import api_router
from app.core.access_log import strip_location_from_access_log
from app.core.auth_config import load_supabase_auth_settings
from app.core.errors import register_error_handlers
from app.core.security import warn_if_temporary_login_is_on
from app.core.version import get_version
from app.db.session import get_session_factory
from app.services.menu_import_processing import find_unfinished_imports, recover_imports

logger = logging.getLogger(__name__)


def recover_unfinished_imports() -> threading.Thread | None:
    """Resume the menu imports a restart interrupted, in a background thread (see
    app.services.menu_import_processing). The imports are looked up before the server takes
    requests; a database that cannot be reached is logged and does not stop the server."""
    session_factory = get_session_factory()
    try:
        import_ids = find_unfinished_imports(session_factory)
    except Exception:
        logger.exception("Could not look for menu imports to recover")
        return None
    if not import_ids:
        return None
    # A warning so it reaches the service log, which shows no INFO records from the app.
    logger.warning(
        "Recovering %d menu imports interrupted by a restart: %s", len(import_ids), ", ".join(map(str, import_ids))
    )
    thread = threading.Thread(
        target=recover_imports,
        args=(import_ids, session_factory, get_image_storage(), get_menu_extractor()),
        kwargs={"llm_layer": get_matching_llm_layer()},
        name="menu-import-recovery",
        # A restart during recovery leaves the imports unfinished, and the next start resumes them.
        daemon=True,
    )
    thread.start()
    return thread


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Check the extractor and storage settings at start-up (e.g. MENU_EXTRACTOR=gemini
    # without GEMINI_API_KEY, IMAGE_STORAGE=s3 without S3_BUCKET) instead of failing on
    # the first upload. The local defaults need nothing.
    get_menu_extractor()
    get_image_storage()
    # An invalid MATCHING_LLM_MAX_CALLS stops the server; a missing key only logs a warning.
    get_matching_llm_layer()
    # Invalid Supabase auth settings (e.g. HS256 allowed) stop the server; an unset SUPABASE_URL does not.
    load_supabase_auth_settings()
    # Leave a trace in the server log while anyone can get a token from POST /api/auth/temp-login.
    warn_if_temporary_login_is_on()
    # Pin the reported version to the code this process loaded.
    get_version()
    recover_unfinished_imports()
    yield


# The location (lat/lng) and the map area (south/west/north/east) arrive as query parameters;
# keep them out of the access log.
strip_location_from_access_log()

app = FastAPI(title="BottleMap API", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(api_router)
