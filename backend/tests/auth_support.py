# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-14). Reviewed by Haeul Yang.
"""Signing keys and a JWKS endpoint for auth tests. Nothing here touches the network."""

from dataclasses import dataclass
from typing import Any

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
