"""Signing keys and a JWKS endpoint for auth tests. Nothing here touches the network."""

import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt import PyJWKClient
from jwt.algorithms import ECAlgorithm
from jwt.exceptions import PyJWKClientConnectionError


@dataclass(frozen=True)
class SigningKey:
    kid: str
    private_key: ec.EllipticCurvePrivateKey

    @property
    def jwk(self) -> dict[str, Any]:
        """The public key as Supabase publishes it in the JWKS."""
        public = ECAlgorithm.to_jwk(self.private_key.public_key(), as_dict=True)
        return {**public, "kid": self.kid, "alg": "ES256", "use": "sig"}


def new_signing_key(kid: str) -> SigningKey:
    return SigningKey(kid, ec.generate_private_key(ec.SECP256R1()))


class FakeJwksClient(PyJWKClient):
    """A PyJWKClient whose endpoint is a list in memory. Set `keys`, `payload` or `error` to change it."""

    def __init__(self, *keys: SigningKey) -> None:
        super().__init__("https://test.supabase.co/auth/v1/.well-known/jwks.json", cache_jwk_set=True, lifespan=600)
        self.keys = list(keys)
        self.payload: Any = None
        self.error: Exception | None = None
        self.fetches = 0

    def fetch_data(self) -> Any:
        self.fetches += 1
        if self.error is not None:
            raise self.error
        return self.payload if self.payload is not None else {"keys": [key.jwk for key in self.keys]}


def connection_error() -> PyJWKClientConnectionError:
    return PyJWKClientConnectionError('Fail to fetch data from the url, err: "timed out"')


SUPABASE_TEST_URL = "https://test.supabase.co"


class SupabaseTokens:
    """Issues Supabase-style access tokens signed by a key that a fake JWKS publishes."""

    def __init__(self) -> None:
        self.key = new_signing_key("supabase-key-1")
        self.jwks = FakeJwksClient(self.key)
        self.requested_jwks_urls: list[str] = []

    def token(self, *, key: SigningKey | None = None, headers: dict[str, Any] | None = None, **changes: Any) -> str:
        """A valid token unless `changes` say otherwise; a None value leaves the claim out."""
        now = int(time.time())
        claims = {
            "iss": f"{SUPABASE_TEST_URL}/auth/v1",
            "aud": "authenticated",
            "sub": str(uuid4()),
            "iat": now,
            "exp": now + 3600,
            "role": "authenticated",
            "email": "user@example.com",
            "user_metadata": {"name": "홍길동"},
            "is_anonymous": False,
            **changes,
        }
        claims = {name: value for name, value in claims.items() if value is not None}
        signer = key or self.key
        return jwt.encode(claims, signer.private_key, algorithm="ES256", headers={"kid": signer.kid, **(headers or {})})
