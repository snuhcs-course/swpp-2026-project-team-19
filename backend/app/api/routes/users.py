# AI-generated with ChatGPT (Haeul Yang, 2026-10-04, PR #3). Reviewed by Haeul Yang.
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import Principal, get_current_user, user_type_of

router = APIRouter(prefix="/api", tags=["users"])


class CurrentUserResponse(BaseModel):
    userId: str
    email: str | None = None
    displayName: str | None = None
    userType: Literal["customer", "operator"] = "customer"


@router.get("/me", response_model=CurrentUserResponse)
def read_current_user(principal: Principal = Depends(get_current_user)) -> CurrentUserResponse:
    """Return the signed-in identity from the verified access token."""
    claims = principal.claims
    metadata = claims.get("user_metadata")
    name = metadata.get("name") if isinstance(metadata, dict) else claims.get("name")
    return CurrentUserResponse(
        userId=principal.subject,
        email=claims.get("email") or None,
        displayName=name if isinstance(name, str) else None,
        userType=user_type_of(principal),
    )
