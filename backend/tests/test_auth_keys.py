import pytest

from app.adapters.auth_keys import (
    FETCH_TIMEOUT_SECONDS,
    JWKS_CACHE_SECONDS,
    REFETCH_COOLDOWN_SECONDS,
    JwksSigningKeyProvider,
    SigningKeysUnavailable,
    UnknownSigningKey,
    jwks_signing_key_provider,
)
from tests.auth_support import FakeJwksClient, connection_error, new_signing_key


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def key_a():
    return new_signing_key("key-a")


@pytest.fixture
def clock():
    return Clock()


def provider_for(client: FakeJwksClient, clock: Clock) -> JwksSigningKeyProvider:
    return JwksSigningKeyProvider(client, clock=clock)


def test_known_key_id_returns_the_public_key(key_a, clock):
    provider = provider_for(FakeJwksClient(key_a), clock)

    key = provider.get_signing_key("key-a")

    assert key.key_id == "key-a"
    assert key.algorithm_name == "ES256"


def test_jwks_is_cached(key_a, clock):
    client = FakeJwksClient(key_a)
    provider = provider_for(client, clock)

    provider.get_signing_key("key-a")
    provider.get_signing_key("key-a")

    assert client.fetches == 1


def test_unknown_key_id_refetches_the_jwks(key_a, clock):
    client = FakeJwksClient(key_a)
    provider = provider_for(client, clock)
    provider.get_signing_key("key-a")
    # Supabase rotated to a new key after the set was cached.
    client.keys.append(new_signing_key("key-b"))

    key = provider.get_signing_key("key-b")

    assert key.key_id == "key-b"
    assert client.fetches == 2


def test_key_id_missing_after_a_refetch_is_unknown(key_a, clock):
    client = FakeJwksClient(key_a)
    provider = provider_for(client, clock)

    with pytest.raises(UnknownSigningKey):
        provider.get_signing_key("made-up")

    assert client.fetches == 2


def test_refetches_wait_for_the_cooldown(key_a, clock):
    client = FakeJwksClient(key_a)
    provider = provider_for(client, clock)
    with pytest.raises(UnknownSigningKey):
        provider.get_signing_key("made-up-1")

    clock.now += REFETCH_COOLDOWN_SECONDS - 1
    with pytest.raises(UnknownSigningKey):
        provider.get_signing_key("made-up-2")
    assert client.fetches == 2

    clock.now += 1
    with pytest.raises(UnknownSigningKey):
        provider.get_signing_key("made-up-3")
    assert client.fetches == 3


def test_unreachable_jwks_means_keys_unavailable(key_a, clock):
    client = FakeJwksClient(key_a)
    client.error = connection_error()

    with pytest.raises(SigningKeysUnavailable):
        provider_for(client, clock).get_signing_key("key-a")


def test_failed_refetch_means_keys_unavailable(key_a, clock):
    client = FakeJwksClient(key_a)
    provider = provider_for(client, clock)
    provider.get_signing_key("key-a")
    client.error = connection_error()

    with pytest.raises(SigningKeysUnavailable):
        provider.get_signing_key("key-b")


@pytest.mark.parametrize(
    "payload",
    [
        {"keys": []},  # the project still signs with the legacy HS256 secret
        {"keys": [{"kty": "EC", "use": "sig"}]},  # no usable key
        {"keys": [{**new_signing_key("x").jwk, "kid": None}]},  # no kid, so not a signing key
        ["not", "a", "jwks"],
    ],
)
def test_empty_jwks_means_keys_unavailable(key_a, clock, payload):
    client = FakeJwksClient(key_a)
    client.payload = payload

    with pytest.raises(SigningKeysUnavailable):
        provider_for(client, clock).get_signing_key("key-a")


def test_provider_is_shared_per_jwks_url():
    jwks_signing_key_provider.cache_clear()
    url = "https://abc.supabase.co/auth/v1/.well-known/jwks.json"

    provider = jwks_signing_key_provider(url)

    assert jwks_signing_key_provider(url) is provider
    assert jwks_signing_key_provider(url.replace("abc", "xyz")) is not provider
    client = provider._client
    assert (client.uri, client.timeout) == (url, FETCH_TIMEOUT_SECONDS)
    assert client.jwk_set_cache.lifespan == JWKS_CACHE_SECONDS
    jwks_signing_key_provider.cache_clear()
