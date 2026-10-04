from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import get_current_user

router = APIRouter(prefix="/api", tags=["users"])


class CurrentUserResponse(BaseModel):
    userId: str
    email: str | None = None
    displayName: str | None = None
    userType: Literal["customer", "operator"] = "customer"


@router.get("/me", response_model=CurrentUserResponse)
def read_current_user(claims: dict = Depends(get_current_user)) -> CurrentUserResponse:
    """Return the signed-in identity from the verified access token."""
    return CurrentUserResponse(
        userId=claims["sub"],
        email=claims.get("email"),
        displayName=claims.get("name"),
        userType=claims["user_type"],
    )
