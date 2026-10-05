import os
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from app.core.tokens import TOKEN_ALGORITHM, TOKEN_AUDIENCE, TOKEN_ISSUER

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """Validate a local development JWT from the Authorization header."""
    if os.getenv("TEMP_AUTH_ENABLED", "false").lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Local development authentication is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    secret = os.getenv("TEMP_AUTH_JWT_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local token verification is not configured",
        )

    try:
        claims = jwt.decode(
            credentials.credentials,
            secret,
            algorithms=[TOKEN_ALGORITHM],
            audience=TOKEN_AUDIENCE,
            issuer=TOKEN_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss", "aud", "user_type"]},
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not isinstance(claims.get("sub"), str) or not claims["sub"].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if claims.get("user_type") not in {"customer", "operator"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token user type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any] | None:
    """For public routes: None without an Authorization header; a token that is sent must be valid."""
    if credentials is None:
        return None
    return get_current_user(credentials)


def require_operator(claims: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Require an authenticated operator for operator-only API routes."""
    if claims.get("user_type") != "operator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator access required",
        )
    return claims
