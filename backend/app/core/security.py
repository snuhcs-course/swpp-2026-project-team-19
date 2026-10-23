"""Bearer-token checks for the API (API spec, sections 3.1.2 to 3.1.5).

Two kinds of token are accepted:
- Supabase access tokens from Google login, verified with the project's public signing keys.
- Temporary tokens from `POST /api/auth/temp-login` (issuer `bottlemap-local`), verified with the
  local secret, only while TEMP_AUTH_ENABLED is true.

The issuer read from the unverified token only chooses which check to run; every claim is then
verified. A bad or expired token is `401`; a server that cannot check tokens (missing settings,
signing keys out of reach) answers `503` so the app does not send the user back to login.
"""

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.auth_keys import (
    SigningKeyProvider,
    SigningKeysUnavailable,
    UnknownSigningKey,
    jwks_signing_key_provider,
)
from app.core.auth_config import TOKEN_LEEWAY, AuthConfigError, load_supabase_auth_settings
from app.core.tokens import TOKEN_ALGORITHM, TOKEN_AUDIENCE, TOKEN_ISSUER
from app.db.session import get_session
from app.models import User

UserType = Literal["customer", "operator"]
USER_TYPES = ("customer", "operator")
REQUIRED_CLAIMS = ["exp", "iat", "sub", "iss", "aud"]

bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    """A verified caller. `user_type` is set for temporary tokens, which take it from the server setting."""

    kind: Literal["supabase", "temporary"]
    subject: str
    claims: dict[str, Any]
    user_type: UserType | None = None


def get_signing_key_provider_factory() -> Callable[[str], SigningKeyProvider]:
    """The signing keys for a JWKS URL. Tests override this to serve keys from memory."""
    return jwks_signing_key_provider


def _unauthenticated(message: str = "로그인 정보가 만료되었거나 올바르지 않습니다. 다시 로그인해 주세요.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="지금은 로그인을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.",
    )


def authenticate(token: str, key_provider_for: Callable[[str], SigningKeyProvider]) -> Principal:
    """Verify a bearer token. Raises HTTPException 401 or 503."""
    try:
        header = jwt.get_unverified_header(token)
        unverified = jwt.decode(token, options={"verify_signature": False})
    except InvalidTokenError as exc:
        raise _unauthenticated() from exc

    if unverified.get("iss") == TOKEN_ISSUER:
        return _verify_temporary(token)
    return _verify_supabase(token, header, key_provider_for)


def temporary_login_enabled() -> bool:
    return os.getenv("TEMP_AUTH_ENABLED", "false").lower() == "true"


def warn_if_temporary_login_is_on() -> None:
    """At start-up, say in the server log that anyone who reaches the server can get a token."""
    if temporary_login_enabled():
        logger.warning(
            "Temporary login is on: anyone who can reach this server can get a token with user type %s "
            "from POST /api/auth/temp-login. Turn it off (TEMP_AUTH_ENABLED=false) once Google login works.",
            os.getenv("TEMP_AUTH_USER_TYPE", "customer"),
        )


def _verify_temporary(token: str) -> Principal:
    if not temporary_login_enabled():
        raise _unauthenticated()
    secret = os.getenv("TEMP_AUTH_JWT_SECRET", "")
    user_type = os.getenv("TEMP_AUTH_USER_TYPE", "customer").lower()
    if len(secret) < 32 or user_type not in USER_TYPES:
        raise _unavailable()

    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[TOKEN_ALGORITHM],
            audience=TOKEN_AUDIENCE,
            issuer=TOKEN_ISSUER,
            options={"require": REQUIRED_CLAIMS},
        )
    except InvalidTokenError as exc:
        raise _unauthenticated() from exc
    # The role comes from the server setting at request time, not from the token, so changing
    # TEMP_AUTH_USER_TYPE applies to tokens already issued (API spec, section 3.1.3).
    return Principal("temporary", _subject(claims), claims, user_type=user_type)


def _verify_supabase(
    token: str, header: dict[str, Any], key_provider_for: Callable[[str], SigningKeyProvider]
) -> Principal:
    try:
        settings = load_supabase_auth_settings()
    except AuthConfigError as exc:
        raise _unavailable() from exc
    if settings is None:
        raise _unavailable()

    kid = header.get("kid")
    # Checked before looking up keys, so an HS256 token never causes a JWKS request.
    if header.get("alg") not in settings.algorithms or not isinstance(kid, str):
        raise _unauthenticated()
    try:
        key = key_provider_for(settings.jwks_url).get_signing_key(kid)
    except SigningKeysUnavailable as exc:
        raise _unavailable() from exc
    except UnknownSigningKey as exc:
        raise _unauthenticated() from exc

    try:
        claims = jwt.decode(
            token,
            key.key,
            algorithms=list(settings.algorithms),
            audience=settings.audience,
            issuer=settings.issuer,
            leeway=TOKEN_LEEWAY,
            options={"require": REQUIRED_CLAIMS},
        )
    except InvalidTokenError as exc:
        raise _unauthenticated() from exc
    if claims.get("is_anonymous") is True:
        raise _unauthenticated()
    return Principal("supabase", _subject(claims), claims)


def _subject(claims: dict[str, Any]) -> str:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise _unauthenticated()
    return subject


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    key_provider_for: Callable[[str], SigningKeyProvider] = Depends(get_signing_key_provider_factory),
) -> Principal:
    """The verified caller; 401 without a bearer token."""
    if credentials is None:
        raise _unauthenticated("로그인이 필요합니다.")
    return authenticate(credentials.credentials, key_provider_for)


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    key_provider_for: Callable[[str], SigningKeyProvider] = Depends(get_signing_key_provider_factory),
) -> Principal | None:
    """For public routes: None without an Authorization header; a token that is sent must be valid.

    A token the server cannot check right now (no SUPABASE_URL, signing keys out of reach, invalid
    temporary-login settings) counts as no token instead of `503`: public data stays readable for
    signed-in users during a Supabase outage, and they only lose what a guest cannot see either
    (API spec, section 3.1.5). An invalid or expired token is still `401`.
    """
    if credentials is None:
        return None
    try:
        return authenticate(credentials.credentials, key_provider_for)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            return None
        raise


def user_type_of(principal: Principal, session: Session) -> UserType:
    """The caller's user type (API spec, section 3.1.4).

    A temporary token takes it from TEMP_AUTH_USER_TYPE. A Supabase user takes it from
    `users.user_type`, read on every request so a role change applies to the next one; a user
    without a row (GET /api/me not called yet) is a customer. Token claims never grant a role.
    """
    if principal.kind == "temporary":
        return principal.user_type or "customer"
    stored = session.scalar(select(User.user_type).where(User.auth_subject == principal.subject))
    return stored.value if stored is not None else "customer"


def require_operator(
    # Declared before the session so a request without a valid token never opens a database session.
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Principal:
    """Require an authenticated operator for operator-only API routes."""
    if user_type_of(principal, session) != "operator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="이 작업을 할 권한이 없습니다.")
    return principal
