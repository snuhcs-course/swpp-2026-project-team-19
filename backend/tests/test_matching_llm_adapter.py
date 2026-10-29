"""GeminiMatchingLLM and the MATCHING_LLM_* settings. The Gemini client is always a fake."""

import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.adapters.gemini_matching_llm import MAX_ATTEMPTS, REQUEST_TIMEOUT_S, GeminiMatchingLLM
from app.adapters.matching_llm import MatchingLLMError, MatchingLLMSettings, load_matching_llm_settings
from app.api import deps
from app.extraction import gemini
from app.matching.llm_layer import Pick, Translation

MATCHING_ENV = ("GEMINI_API_KEY", "MATCHING_LLM_ENABLED", "MATCHING_LLM_MAX_CALLS", "MATCHING_LLM_M3B_ENABLED")


class FakeClient:
    """Stands in for genai.Client; each create() returns or raises the next scripted response."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.interactions = self

    def create(self, **request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class StatusError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


def answer(text):
    return SimpleNamespace(status="completed", output_text=text, usage=None)


@pytest.fixture(autouse=True)
def no_real_api(monkeypatch):
    def refuse(settings):
        raise AssertionError("tests must not create a real Gemini client")

    monkeypatch.setattr(gemini, "make_client", refuse)
    monkeypatch.setattr(gemini, "sleep", lambda seconds: None)


@pytest.fixture
def env(monkeypatch):
    for name in MATCHING_ENV:
        monkeypatch.delenv(name, raising=False)
    deps.get_matching_llm_layer.cache_clear()
    yield monkeypatch
    deps.get_matching_llm_layer.cache_clear()


# ---- GeminiMatchingLLM ----


def test_request_matches_the_m3_experiment():
    """Same request as ai/match_llm/llm.py: model, thinking low, system prompt, payload as JSON text."""
    client = FakeClient(answer('{"choice": "1", "reason": "r"}'))
    payload = {"menu_line": "글렌피딕 12년", "options": [{"no": "1"}]}

    text = GeminiMatchingLLM("secret-test-key", client=client).generate_json("PROMPT", payload, Pick.model_json_schema())

    assert text == '{"choice": "1", "reason": "r"}'
    [request] = client.requests
    assert request == {
        "model": "gemini-3.1-flash-lite",
        "system_instruction": "PROMPT",
        "input": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "response_format": {"type": "text", "mime_type": "application/json", "schema": Pick.model_json_schema()},
        "generation_config": {"thinking_level": "low"},
        "store": False,
        "timeout": REQUEST_TIMEOUT_S,
    }
    assert "글렌피딕" in request["input"][0]["text"]  # not \\u-escaped


def test_missing_text_is_empty():
    client = FakeClient(SimpleNamespace(status="failed", output_text=None))

    assert GeminiMatchingLLM("k", client=client).generate_json("P", {}, Translation.model_json_schema()) == ""


def test_transient_error_is_retried_once():
    client = FakeClient(StatusError(503), answer("{}"))

    assert GeminiMatchingLLM("k", client=client).generate_json("P", {}, {}) == "{}"
    assert len(client.requests) == 2


def test_errors_become_matching_llm_errors_without_the_key():
    client = FakeClient(*[StatusError(500)] * MAX_ATTEMPTS)

    with pytest.raises(MatchingLLMError, match=f"after {MAX_ATTEMPTS} attempts") as caught:
        GeminiMatchingLLM("secret-test-key", client=client).generate_json("P", {}, {})

    assert "secret-test-key" not in str(caught.value)
    with pytest.raises(MatchingLLMError):
        GeminiMatchingLLM("k", client=FakeClient(StatusError(400))).generate_json("P", {}, {})


def test_client_that_hit_the_hard_timeout_is_not_reused(monkeypatch):
    """call_with_retries drops a client whose request hung (it may still be in use by the abandoned
    thread); the next request must not get that client back from the adapter."""
    clients = iter(["client-1", "client-2", "client-3"])
    used = []

    def create(client, request, settings):
        used.append(client)
        if len(used) == 1:
            raise gemini.HardTimeout("no response within 75s")
        return answer("{}")

    monkeypatch.setattr(gemini, "make_client", lambda settings: next(clients))
    monkeypatch.setattr(gemini, "_create_with_deadline", create)
    llm = GeminiMatchingLLM("secret-test-key")

    assert llm.generate_json("P", {}, {}) == "{}"  # hangs on client-1, succeeds on a new client-2
    assert llm.generate_json("P", {}, {}) == "{}"

    assert used == ["client-1", "client-2", "client-3"]


def test_each_request_gets_a_new_client_from_the_key(monkeypatch):
    made = []

    def make(settings):
        made.append(settings)
        return FakeClient(answer(f"answer {len(made)}"))

    monkeypatch.setattr(gemini, "make_client", make)
    llm = GeminiMatchingLLM("secret-test-key")

    assert [llm.generate_json("P", {}, {}), llm.generate_json("P", {}, {})] == ["answer 1", "answer 2"]
    assert len(made) == 2
    settings = made[0]
    assert (settings.api_key, settings.model, settings.thinking_level, settings.max_attempts) == (
        "secret-test-key", "gemini-3.1-flash-lite", "low", MAX_ATTEMPTS)
    assert "secret-test-key" not in repr(settings)


# ---- settings and deps ----


def test_off_by_default(env):
    assert load_matching_llm_settings() == MatchingLLMSettings(enabled=False, max_calls=30, m3b_enabled=False)
    env.setenv("GEMINI_API_KEY", "secret-test-key")
    assert deps.get_matching_llm_layer() is None


@pytest.mark.parametrize("value", ["false", "0", "yes", ""])
def test_only_true_turns_it_on(env, value):
    env.setenv("GEMINI_API_KEY", "secret-test-key")
    env.setenv("MATCHING_LLM_ENABLED", value)
    assert deps.get_matching_llm_layer() is None


def test_enabled_with_a_key(env):
    env.setenv("GEMINI_API_KEY", "secret-test-key")
    env.setenv("MATCHING_LLM_ENABLED", "TRUE")
    env.setenv("MATCHING_LLM_MAX_CALLS", "7")
    env.setenv("MATCHING_LLM_M3B_ENABLED", "true")

    layer = deps.get_matching_llm_layer()

    assert isinstance(layer.llm, GeminiMatchingLLM)
    assert (layer.max_calls, layer.use_m3b) == (7, True)


def test_enabled_without_a_key_stays_off_with_a_warning(env, caplog):
    env.setenv("MATCHING_LLM_ENABLED", "true")

    with caplog.at_level(logging.WARNING, logger="app.api.deps"):
        assert deps.get_matching_llm_layer() is None

    assert "GEMINI_API_KEY is not set" in caplog.text


@pytest.mark.parametrize("value", ["0", "-1", "ten", "1.5"])
def test_invalid_cap_is_rejected(env, value):
    env.setenv("MATCHING_LLM_MAX_CALLS", value)

    with pytest.raises(RuntimeError, match="MATCHING_LLM_MAX_CALLS must be a positive int"):
        deps.get_matching_llm_layer()


def test_server_start_fails_with_an_invalid_cap(env):
    from app.main import app

    env.setenv("MATCHING_LLM_MAX_CALLS", "none")

    with pytest.raises(RuntimeError, match="MATCHING_LLM_MAX_CALLS"):
        with TestClient(app):
            pass


def test_server_starts_with_the_layer_on_but_no_key(env, caplog):
    from app.main import app

    env.setenv("MATCHING_LLM_ENABLED", "true")

    with caplog.at_level(logging.WARNING, logger="app.api.deps"), TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200

    assert "the LLM matching layer is off" in caplog.text
