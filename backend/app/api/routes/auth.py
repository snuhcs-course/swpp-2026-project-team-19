# AI-generated with ChatGPT (Haeul Yang, 2026-10-04, PR #3). Reviewed by Haeul Yang.
import os
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.tokens import TOKEN_ALGORITHM, TOKEN_AUDIENCE, TOKEN_ISSUER, TOKEN_LIFETIME

router = APIRouter(prefix="/auth", tags=["auth"])


class TemporaryLoginResponse(BaseModel):
    accessToken: str
    tokenType: str = "bearer"
    expiresIn: int


@router.post(
    "/temp-login",
    response_model=TemporaryLoginResponse,
    summary="Issue a local development token",
    description="Development only. Enable with TEMP_AUTH_ENABLED=true and set a local signing secret.",
)
def temporary_login() -> TemporaryLoginResponse:
    if os.getenv("TEMP_AUTH_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    secret = os.getenv("TEMP_AUTH_JWT_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Temporary auth requires TEMP_AUTH_JWT_SECRET with at least 32 characters",
        )

    user_type = os.getenv("TEMP_AUTH_USER_TYPE", "customer").lower()
    if user_type not in {"customer", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TEMP_AUTH_USER_TYPE must be customer or operator",
        )

    now = datetime.now(timezone.utc)
    expires_at = now + TOKEN_LIFETIME
    token = jwt.encode(
        {
            "sub": "local-dev-user",
            "email": "local-dev@example.invalid",
            "name": "Local development user",
            "user_type": user_type,
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
            "iat": now,
            "exp": expires_at,
        },
        secret,
        algorithm=TOKEN_ALGORITHM,
    )
    return TemporaryLoginResponse(
        accessToken=token,
        expiresIn=int(TOKEN_LIFETIME.total_seconds()),
    )
