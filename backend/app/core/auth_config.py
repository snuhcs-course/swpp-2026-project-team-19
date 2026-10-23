"""Supabase access-token settings from environment variables (API spec, sections 3.1.2 and 3.1.6).

Supabase signs access tokens with an asymmetric key and publishes the public keys at
`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`. No secret is needed to verify them, so this
module reads only public settings. Without `SUPABASE_URL` the backend accepts no Supabase
token (the API answers `503`); temporary login keeps working.
"""

import os
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

from jwt.algorithms import get_default_algorithms

DEFAULT_AUDIENCE = "authenticated"
DEFAULT_ALGORITHMS = ("ES256",)
# Tolerates a small clock difference between Supabase and this server for `exp` and `iat`.
TOKEN_LEEWAY = timedelta(seconds=30)
# Shared secrets (HS*) are not published in the JWKS, and "none" is not a signature.
_REJECTED_ALGORITHMS = {"none", "HS256", "HS384", "HS512"}


class AuthConfigError(Exception):
    """A Supabase auth environment variable is invalid."""


@dataclass(frozen=True)
class SupabaseAuthSettings:
    url: str
    audience: str
    algorithms: tuple[str, ...]

    @property
    def issuer(self) -> str:
        return f"{self.url}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"


def load_supabase_auth_settings() -> SupabaseAuthSettings | None:
    """Read the settings; None when SUPABASE_URL is unset. Raise AuthConfigError if a value is invalid."""
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path or parts.query or parts.fragment:
        raise AuthConfigError(f"SUPABASE_URL must be the project URL like https://<ref>.supabase.co, got {url!r}")

    audience = os.getenv("SUPABASE_JWT_AUDIENCE", "").strip() or DEFAULT_AUDIENCE
    return SupabaseAuthSettings(url=url, audience=audience, algorithms=_algorithms())


def _algorithms() -> tuple[str, ...]:
    raw = os.getenv("SUPABASE_JWT_ALGORITHMS", "")
    names = tuple(name.strip() for name in raw.split(",") if name.strip())
    if not names:
        return DEFAULT_ALGORITHMS
    supported = get_default_algorithms().keys() - _REJECTED_ALGORITHMS
    invalid = [name for name in names if name not in supported]
    if invalid:
        raise AuthConfigError(
            f"SUPABASE_JWT_ALGORITHMS allows only asymmetric algorithms such as ES256, got {', '.join(invalid)}"
        )
    return names
