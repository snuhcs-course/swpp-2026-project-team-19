from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.bars import router as bars_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.health import router as health_router
from app.api.routes.media import router as media_router
from app.api.routes.menu_imports import router as menu_imports_router
from app.api.routes.search import router as search_router
from app.api.routes.users import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/api")
api_router.include_router(users_router)
api_router.include_router(bars_router)
api_router.include_router(search_router)
api_router.include_router(menu_imports_router)
api_router.include_router(catalog_router)
api_router.include_router(health_router)
api_router.include_router(media_router)
