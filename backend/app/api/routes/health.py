# AI-generated with ChatGPT (Haeul Yang, 2026-10-04, PR #3, #19). Reviewed by Haeul Yang.
from fastapi import APIRouter

from app.core.version import get_version

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str | None]:
    # version: the commit the server started from, or null outside a git checkout.
    return {"status": "ok", "version": get_version()}
