# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-14). Reviewed by Haeul Yang.
"""Public keys that verify Supabase access tokens (API spec, section 3.1.2).

Supabase publishes its signing keys as a JWKS. The set is cached for ten minutes, under the
twenty-minute limit Supabase recommends so that a revoked key stops working soon. A token
whose `kid` is not in the cached set triggers one refetch, which picks up a rotated key;
refetches are spaced at least thirty seconds apart so made-up `kid`s cannot flood Supabase.

The two failures mean different things to the API:
- `SigningKeysUnavailable`: the keys cannot be read (network error, or an empty set because
  the project still signs with the legacy HS256 secret). A server problem: `503`.
- `UnknownSigningKey`: the keys were read but none has the token's `kid`. A bad token: `401`.
"""

import logging
import threading
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol

from jwt import PyJWK, PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWKSetError

JWKS_CACHE_SECONDS = 600
FETCH_TIMEOUT_SECONDS = 5
REFETCH_COOLDOWN_SECONDS = 30

logger = logging.getLogger(__name__)


class SigningKeyError(Exception):
    """Base class for signing-key lookup failures."""


class SigningKeysUnavailable(SigningKeyError):
    """The signing keys could not be read."""


class UnknownSigningKey(SigningKeyError):
    """No signing key has the requested `kid`."""


class SigningKeyProvider(Protocol):
    def get_signing_key(self, kid: str) -> PyJWK:
        """Raises SigningKeysUnavailable or UnknownSigningKey."""
        ...


class JwksSigningKeyProvider:
    def __init__(self, client: PyJWKClient, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._client = client
        self._clock = clock
        self._lock = threading.Lock()
        self._last_refetch: float | None = None

    def get_signing_key(self, kid: str) -> PyJWK:
        with self._lock:
            key = _match(self._signing_keys(refresh=False), kid)
            if key is None and self._may_refetch():
                self._last_refetch = self._clock()
                key = _match(self._signing_keys(refresh=True), kid)
        if key is None:
            raise UnknownSigningKey(f"No signing key with kid {kid!r}")
        return key

    def _may_refetch(self) -> bool:
        return self._last_refetch is None or self._clock() - self._last_refetch >= REFETCH_COOLDOWN_SECONDS

    def _signing_keys(self, *, refresh: bool) -> list[PyJWK]:
        try:
            return self._client.get_signing_keys(refresh=refresh)
        except (PyJWKClientError, PyJWKSetError) as error:
            # Connection errors, a payload that is not a JWKS, and an empty set all end here.
            logger.warning("Supabase signing keys are unavailable from %s: %s", self._client.uri, error)
            raise SigningKeysUnavailable(str(error)) from error


def _match(keys: list[PyJWK], kid: str) -> PyJWK | None:
    return next((key for key in keys if key.key_id == kid), None)


@lru_cache(maxsize=4)
def jwks_signing_key_provider(jwks_url: str) -> JwksSigningKeyProvider:
    """One provider, and so one cache, per JWKS URL."""
    client = PyJWKClient(
        jwks_url, cache_jwk_set=True, lifespan=JWKS_CACHE_SECONDS, timeout=FETCH_TIMEOUT_SECONDS
    )
    return JwksSigningKeyProvider(client)
