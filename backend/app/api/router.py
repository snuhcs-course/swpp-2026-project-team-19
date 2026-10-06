from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.bars import router as bars_router
from app.api.routes.health import router as health_router
from app.api.routes.search import router as search_router
from app.api.routes.users import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/api")
api_router.include_router(users_router)
api_router.include_router(bars_router)
api_router.include_router(search_router)
api_router.include_router(health_router)
