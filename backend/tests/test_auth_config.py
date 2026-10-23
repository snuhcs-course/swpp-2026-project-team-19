import pytest

from app.core.auth_config import AuthConfigError, load_supabase_auth_settings


@pytest.fixture
def auth_env(monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_JWT_AUDIENCE", "SUPABASE_JWT_ALGORITHMS"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize("value", [None, "", "   "])
def test_supabase_is_off_without_a_url(auth_env, value):
    if value is not None:
        auth_env.setenv("SUPABASE_URL", value)

    assert load_supabase_auth_settings() is None


@pytest.mark.parametrize("url", ["https://abc.supabase.co", "https://abc.supabase.co/", " https://abc.supabase.co// "])
def test_urls_are_derived_from_supabase_url(auth_env, url):
    auth_env.setenv("SUPABASE_URL", url)

    settings = load_supabase_auth_settings()

    assert settings.url == "https://abc.supabase.co"
    assert settings.issuer == "https://abc.supabase.co/auth/v1"
    assert settings.jwks_url == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"


def test_defaults_are_the_supabase_values(auth_env):
    auth_env.setenv("SUPABASE_URL", "https://abc.supabase.co")
    auth_env.setenv("SUPABASE_JWT_AUDIENCE", " ")
    auth_env.setenv("SUPABASE_JWT_ALGORITHMS", "")

    settings = load_supabase_auth_settings()

    assert (settings.audience, settings.algorithms) == ("authenticated", ("ES256",))


def test_audience_and_algorithms_can_be_set(auth_env):
    auth_env.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
    auth_env.setenv("SUPABASE_JWT_AUDIENCE", "bottlemap")
    auth_env.setenv("SUPABASE_JWT_ALGORITHMS", " ES256, RS256 ,")

    settings = load_supabase_auth_settings()

    assert (settings.audience, settings.algorithms) == ("bottlemap", ("ES256", "RS256"))


@pytest.mark.parametrize(
    "url",
    ["abc.supabase.co", "ftp://abc.supabase.co", "https://", "https://abc.supabase.co/auth/v1", "https://abc.supabase.co?x=1"],
)
def test_a_url_that_is_not_a_project_url_is_rejected(auth_env, url):
    auth_env.setenv("SUPABASE_URL", url)

    with pytest.raises(AuthConfigError, match="SUPABASE_URL"):
        load_supabase_auth_settings()


@pytest.mark.parametrize("algorithms", ["ES256,HS256", "HS512", "none"])
def test_hs256_is_not_allowed(auth_env, algorithms):
    auth_env.setenv("SUPABASE_URL", "https://abc.supabase.co")
    auth_env.setenv("SUPABASE_JWT_ALGORITHMS", algorithms)

    with pytest.raises(AuthConfigError, match="SUPABASE_JWT_ALGORITHMS"):
        load_supabase_auth_settings()


@pytest.mark.parametrize("algorithms", ["es256", "XS999"])
def test_unknown_algorithms_are_rejected(auth_env, algorithms):
    auth_env.setenv("SUPABASE_URL", "https://abc.supabase.co")
    auth_env.setenv("SUPABASE_JWT_ALGORITHMS", algorithms)

    with pytest.raises(AuthConfigError, match="SUPABASE_JWT_ALGORITHMS"):
        load_supabase_auth_settings()
