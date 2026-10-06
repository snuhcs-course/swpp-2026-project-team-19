from fastapi import FastAPI

from app.api.router import api_router
from app.core.errors import register_error_handlers

app = FastAPI(title="BottleMap API", version="0.1.0")
register_error_handlers(app)
app.include_router(api_router)
