"""MENU_EXTRACTOR=openrouter (I5-P19): the OpenRouter call, the route ladder, the circuit breaker
and the adapter. OpenRouter is a fake HTTP client, Gemini a fake SDK client, CLOVA a fake call;
no test calls a real API."""

import hashlib
import json
import logging
import threading
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app import extraction
from app.adapters import openrouter_extraction
from app.adapters.extraction import ExtractionError
from app.adapters.gemini_extraction import GeminiMenuExtractor
from app.adapters.hybrid_extraction import HybridMenuExtractor
from app.adapters.openrouter_extraction import OpenRouterMenuExtractor
from app.api import deps
from app.extraction import gemini, hybrid, openrouter, routed
from app.extraction.clova import ClovaOCRError
from app.extraction.hybrid_v2 import HybridExtractionV2
from app.extraction.openrouter import OpenRouterCreditError, OpenRouterSettings
from app.extraction.routed import AllRoutesFailedError, CircuitBreaker, RouteSettings, extract_menu_routed
from app.models import ExtractionApproach
from app.services.paid_photo_budget import DailyPaidBudget
from tests.test_hybrid_extraction_adapter import CLOVA, OCR_RESPONSE, SETTINGS, jpeg
from tests.test_hybrid_v2_extraction import V2_OUTPUT

PRIMARY, FALLBACK, DIRECT = "google/gemini-3.8-flash", "anthropic/claude-sonnet-5.5", "gemini-3.8-flash"
OPENROUTER = OpenRouterSettings(api_key="or-secret-test-key", model=PRIMARY, fallback_models=(FALLBACK,), max_attempts=3)
ROUTE = RouteSettings(openrouter=OPENROUTER, direct=replace(SETTINGS, model=DIRECT, max_attempts=2),
                      lite=replace(SETTINGS, max_attempts=2))
ANSWER = json.dumps(V2_OUTPUT)
ENV = ("MENU_EXTRACTOR", "EXTRACTION_MODE", "EXTRACTION_HYBRID_PROMPT", "GEMINI_API_KEY", "EXTRACTION_MODEL",
       "EXTRACTION_THINKING_LEVEL", "EXTRACTION_MAX_ATTEMPTS", "EXTRACTION_REQUEST_TIMEOUT_S",
       "EXTRACTION_WALL_TIMEOUT_S", "EXTRACTION_DIRECT_MODEL", "EXTRACTION_DIRECT_MAX_ATTEMPTS",
       "CLOVA_OCR_INVOKE_URL", "CLOVA_OCR_SECRET", "OPENROUTER_API_KEY", "OPENROUTER_EXTRACTION_MODEL",
       "OPENROUTER_FALLBACK_MODELS", "OPENROUTER_REASONING_EFFORT", "OPENROUTER_MAX_TOKENS",
       "OPENROUTER_EXTRACTION_PROMPT", "OPENROUTER_BREAKER_FAILURES", "OPENROUTER_BREAKER_COOLDOWN_S")


class Response:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not JSON")
        return self._body


def ok(text=ANSWER, model=PRIMARY, finish="stop", cost=0.03, provider="Google"):
    return Response(200, {
        "id": "gen-1", "model": model, "provider": provider,
        "choices": [{"message": {"content": text}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 8000, "completion_tokens": 9000, "total_tokens": 17000, "cost": cost,
                  "completion_tokens_details": {"reasoning_tokens": 4000}}})


def failed(status, message="upstream said no"):
    return Response(status, {"error": {"code": status, "message": message}})


class FakeHttp:
    """Answers `post` from a list (the last answer repeats); an exception in the list is raised."""

    def __init__(self, *answers):
        self.answers, self.posts = list(answers), []

    def post(self, url, **kwargs):
        self.posts.append({"url": url, **kwargs})
        reply = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


class ApiError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


class FakeGemini:
    """interactions.create answers per model: a text, or an exception to raise."""

    def __init__(self, **by_model):
        self.by_model, self.requests = by_model, []
        self.interactions = self

    def create(self, **request):
        self.requests.append(request)
        reply = self.by_model[request["model"].replace("-", "_").replace(".", "_")]
        if isinstance(reply, Exception):
            raise reply
        usage = SimpleNamespace(total_input_tokens=5000, total_output_tokens=300, total_thought_tokens=700,
                                total_tokens=6000)
        return SimpleNamespace(output_text=reply, status="completed", usage=usage)


def gemini_fake(direct=ANSWER, lite=ANSWER):
    return FakeGemini(gemini_3_8_flash=direct, gemini_3_5_flash_lite=lite)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    waits = []
    monkeypatch.setattr(openrouter, "sleep", waits.append)
    monkeypatch.setattr(gemini, "sleep", waits.append)
    return waits


@pytest.fixture(autouse=True)
def fake_ocr(monkeypatch):
    class Fake:
        error = None
        calls = 0

        def __call__(self, settings, image, mime_type, client=None):
            self.calls += 1
            if self.error is not None:
                raise self.error
            return {"response": OCR_RESPONSE, "sentSize": [1000, 2000], "latencyMs": 900, "attempts": 1}

    fake = Fake()
    monkeypatch.setattr(hybrid, "call_ocr", fake)
    return fake


def run(http, gem=None, route=ROUTE, breaker=None):
    return extract_menu_routed(jpeg(), "image/jpeg", CLOVA, route, breaker or CircuitBreaker(),
                               http_client=http, gemini_client=gem or gemini_fake())


def body():
    return openrouter.build_body(OPENROUTER, "PROMPT", "LINES", b"\xff\xd8image", "image/jpeg",
                                 HybridExtractionV2.model_json_schema())


# ---- the request ----


def test_the_request_is_the_one_the_evaluation_sent():
    sent = body()

    assert sent["model"] == PRIMARY and sent["models"] == [FALLBACK]
    assert sent["messages"][0] == {"role": "system", "content": "PROMPT"}
    text, image = sent["messages"][1]["content"]
    assert text == {"type": "text", "text": "LINES"}
    assert image["image_url"]["url"] == "data:image/jpeg;base64,/9hpbWFnZQ=="
    assert sent["provider"] == {"data_collection": "deny", "require_parameters": True}
    assert sent["reasoning"] == {"effort": "medium"} and sent["max_tokens"] == 48000
    schema = sent["response_format"]["json_schema"]
    assert sent["response_format"]["type"] == "json_schema" and schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert all(node["additionalProperties"] is False for node in schema["schema"]["$defs"].values()
               if node.get("type") == "object")


def test_without_fallback_models_no_models_array_is_sent():
    sent = openrouter.build_body(replace(OPENROUTER, fallback_models=()), "P", "L", b"x", "image/png", {"type": "object"})

    assert "models" not in sent and sent["model"] == PRIMARY


def test_the_key_goes_in_the_header_only_and_stays_out_of_repr():
    http = FakeHttp(ok())

    openrouter.call_with_retries(OPENROUTER, body(), http)

    [post] = http.posts
    assert post["url"] == openrouter.URL and post["headers"]["Authorization"] == "Bearer or-secret-test-key"
    assert "or-secret-test-key" not in json.dumps(post["json"]) and post["timeout"] == 300
    assert "or-secret-test-key" not in repr(OPENROUTER) and PRIMARY in repr(OPENROUTER)


# ---- retries and errors of one call ----


def test_a_rate_limit_is_retried_with_backoff(no_waiting):
    http = FakeHttp(failed(429), failed(503), ok())

    result = openrouter.call_with_retries(OPENROUTER, body(), http)

    assert result.attempts == 3 and no_waiting == [5, 10]
    assert openrouter.answer(result.data)["costUsd"] == 0.03


def test_retries_run_out(no_waiting):
    http = FakeHttp(failed(502))

    with pytest.raises(extraction.ModelCallError, match="gave up after 3 attempts") as caught:
        openrouter.call_with_retries(OPENROUTER, body(), http)

    assert caught.value.attempts == 3 and len(http.posts) == 3 and no_waiting == [5, 10]
    assert not isinstance(caught.value, OpenRouterCreditError)


def test_out_of_credits_is_its_own_error_and_is_not_retried(no_waiting):
    http = FakeHttp(failed(402, "Insufficient credits"))

    with pytest.raises(OpenRouterCreditError, match="HTTP 402: Insufficient credits") as caught:
        openrouter.call_with_retries(OPENROUTER, body(), http)

    assert caught.value.attempts == 1 and len(http.posts) == 1 and no_waiting == []


def test_a_bad_request_is_not_retried(no_waiting):
    http = FakeHttp(failed(400, "bad schema"))

    with pytest.raises(extraction.ModelCallError, match="HTTP 400: bad schema") as caught:
        openrouter.call_with_retries(OPENROUTER, body(), http)

    assert caught.value.attempts == 1 and no_waiting == []


@pytest.mark.parametrize("error, retried", [
    ({"code": 502, "message": "provider disconnected"}, True),
    ({"message": "no code given"}, True),  # treated as 502
    ("a plain string", True),
    ({"code": 403, "message": "moderation"}, False),
])
def test_an_error_inside_an_http_200_body_is_read_by_its_code(error, retried):
    http = FakeHttp(Response(200, {"error": error}), ok())

    if retried:
        assert openrouter.call_with_retries(OPENROUTER, body(), http).attempts == 2
    else:
        with pytest.raises(extraction.ModelCallError, match="HTTP 200: moderation"):
            openrouter.call_with_retries(OPENROUTER, body(), http)


def test_out_of_credits_inside_an_http_200_body():
    http = FakeHttp(Response(200, {"error": {"code": 402, "message": "key limit reached"}}))

    with pytest.raises(OpenRouterCreditError, match="key limit reached"):
        openrouter.call_with_retries(OPENROUTER, body(), http)


def test_a_choice_that_ended_in_an_error_is_read_by_its_code():
    broken = Response(200, {"choices": [{"message": {"content": "partial"}, "finish_reason": "error",
                                         "error": {"code": 429, "message": "rate limited mid-answer"}}]})
    http = FakeHttp(broken, ok())

    assert openrouter.call_with_retries(OPENROUTER, body(), http).attempts == 2


@pytest.mark.parametrize("first", [Response(200, {"id": "gen-1"}), Response(200, "<html>gateway</html>"),
                                   Response(500, "oops"), Response(200, ["not", "an", "object"]),
                                   httpx.ConnectError("no route"), httpx.ReadTimeout("slow")])
def test_an_answer_without_choices_or_json_and_a_network_error_are_retried(first):
    http = FakeHttp(first, ok())

    assert openrouter.call_with_retries(OPENROUTER, body(), http).attempts == 2


def test_a_page_that_is_not_json_with_a_client_error_status_is_not_retried():
    http = FakeHttp(Response(404, "<html>not found</html>"))

    with pytest.raises(extraction.ModelCallError, match="HTTP 404, not a JSON object") as caught:
        openrouter.call_with_retries(OPENROUTER, body(), http)

    assert caught.value.attempts == 1


def test_a_call_that_hangs_is_given_up_at_the_wall_clock_cap():
    release = threading.Event()

    class Hung:
        def post(self, url, **kwargs):
            release.wait(5)

    settings = replace(OPENROUTER, max_attempts=1, wall_timeout_s=0.05)
    try:
        with pytest.raises(extraction.ModelCallError, match="HardTimeout: no response within 0.05s"):
            openrouter.call_with_retries(settings, body(), Hung())
    finally:
        release.set()


def test_the_default_client_is_httpx(monkeypatch):
    http = FakeHttp(ok())
    monkeypatch.setattr(httpx, "post", http.post)

    assert openrouter.call_with_retries(OPENROUTER, body()).attempts == 1 and len(http.posts) == 1


def test_answer_reads_a_body_without_usage():
    got = openrouter.answer({"choices": [{"message": None, "finish_reason": "stop"}]})

    assert got["text"] == "" and got["costUsd"] is None and got["thoughtTokens"] is None and got["model"] is None


# ---- settings ----


@pytest.fixture
def env(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    deps.get_menu_extractor.cache_clear()
    yield monkeypatch
    deps.get_menu_extractor.cache_clear()


def set_openrouter_env(env):
    for name, value in {
        "MENU_EXTRACTOR": "openrouter", "OPENROUTER_API_KEY": "or-secret-test-key",
        "OPENROUTER_EXTRACTION_MODEL": PRIMARY, "OPENROUTER_FALLBACK_MODELS": FALLBACK,
        "GEMINI_API_KEY": "secret-test-key", "EXTRACTION_MODEL": "gemini-3.5-flash-lite",
        "EXTRACTION_THINKING_LEVEL": "medium", "EXTRACTION_DIRECT_MODEL": DIRECT,
        "CLOVA_OCR_INVOKE_URL": "https://ocr.example.test/custom/v1/1/abc", "CLOVA_OCR_SECRET": "clova-secret",
    }.items():
        env.setenv(name, value)


def test_route_settings_defaults(env):
    set_openrouter_env(env)

    route = routed.load_route_settings()

    assert route.openrouter == OpenRouterSettings(api_key="or-secret-test-key", model=PRIMARY, fallback_models=(FALLBACK,))
    assert (route.openrouter.reasoning_effort, route.openrouter.max_tokens) == ("medium", 48000)
    assert (route.openrouter.max_attempts, route.openrouter.wall_timeout_s) == (6, 330)
    assert (route.direct.model, route.direct.max_attempts, route.direct.thinking_level) == (DIRECT, 2, "medium")
    assert (route.lite.model, route.lite.max_attempts) == ("gemini-3.5-flash-lite", 6)
    assert (route.prompt, route.breaker_failures, route.breaker_cooldown_s) == ("v2.1", 3, 600)


def test_route_settings_from_the_environment(env):
    set_openrouter_env(env)
    for name, value in {
        "OPENROUTER_FALLBACK_MODELS": " a/one , b/two ,", "OPENROUTER_REASONING_EFFORT": "high",
        "OPENROUTER_MAX_TOKENS": "32000", "EXTRACTION_MAX_ATTEMPTS": "4", "EXTRACTION_WALL_TIMEOUT_S": "400",
        "EXTRACTION_DIRECT_MAX_ATTEMPTS": "1", "OPENROUTER_EXTRACTION_PROMPT": "v2",
        "OPENROUTER_BREAKER_FAILURES": "5", "OPENROUTER_BREAKER_COOLDOWN_S": "120",
    }.items():
        env.setenv(name, value)

    route = routed.load_route_settings()

    assert route.openrouter.fallback_models == ("a/one", "b/two")
    assert (route.openrouter.reasoning_effort, route.openrouter.max_tokens) == ("high", 32000)
    assert (route.openrouter.max_attempts, route.openrouter.wall_timeout_s, route.lite.max_attempts) == (4, 400, 4)
    assert (route.direct.max_attempts, route.prompt) == (1, "v2")
    assert (route.breaker_failures, route.breaker_cooldown_s) == (5, 120)


def test_no_fallback_models_is_allowed(env):
    set_openrouter_env(env)
    env.delenv("OPENROUTER_FALLBACK_MODELS")

    assert routed.load_route_settings().openrouter.fallback_models == ()


@pytest.mark.parametrize("name, value, message", [
    ("OPENROUTER_REASONING_EFFORT", "extreme", "OPENROUTER_REASONING_EFFORT must be one of"),
    ("OPENROUTER_FALLBACK_MODELS", f"{FALLBACK},{PRIMARY}", "must not repeat OPENROUTER_EXTRACTION_MODEL"),
    ("OPENROUTER_EXTRACTION_PROMPT", "v1", "OPENROUTER_EXTRACTION_PROMPT must be one of v2, v2.1"),
    ("OPENROUTER_MAX_TOKENS", "0", "OPENROUTER_MAX_TOKENS must be a positive int"),
    ("OPENROUTER_BREAKER_COOLDOWN_S", "soon", "OPENROUTER_BREAKER_COOLDOWN_S must be a positive float"),
])
def test_an_invalid_setting_is_named_without_leaking_a_key(env, name, value, message):
    set_openrouter_env(env)
    env.setenv(name, value)

    with pytest.raises(RuntimeError, match=f"MENU_EXTRACTOR=openrouter is not configured: .*{message}") as caught:
        deps.get_menu_extractor()

    assert "secret-test-key" not in str(caught.value)


@pytest.mark.parametrize("missing", ["OPENROUTER_API_KEY", "OPENROUTER_EXTRACTION_MODEL", "GEMINI_API_KEY",
                                     "EXTRACTION_MODEL", "EXTRACTION_THINKING_LEVEL",
                                     "CLOVA_OCR_INVOKE_URL", "CLOVA_OCR_SECRET"])
def test_a_missing_setting_is_named_at_start_up(env, missing):
    set_openrouter_env(env)
    env.delenv(missing)

    with pytest.raises(RuntimeError, match=f"MENU_EXTRACTOR=openrouter is not configured: .*{missing}"):
        deps.get_menu_extractor()


def test_openrouter_is_selected(env):
    set_openrouter_env(env)

    extractor = deps.get_menu_extractor()

    assert isinstance(extractor, OpenRouterMenuExtractor)
    assert (extractor.approach, extractor.provider, extractor.model_name) == (
        ExtractionApproach.OCR_LLM, "naver-clova+openrouter", PRIMARY)
    assert extractor.pipeline_version == "bottlemap-menu-hybrid-prompthybrid-v2.1-reasoning-medium"
    assert (extractor.breaker.threshold, extractor.breaker.cooldown_s) == (3, 600)
    assert extractor.fallback.model_name == "gemini-3.5-flash-lite"


@pytest.mark.parametrize("mode, kind, prompt", [("gemini", GeminiMenuExtractor, None), ("hybrid", HybridMenuExtractor, "v2")])
def test_the_gemini_extractor_is_what_it_was_with_the_openrouter_settings_present(env, mode, kind, prompt):
    # The way back (P40's switch): MENU_EXTRACTOR=gemini ignores every OpenRouter setting, valid or not.
    set_openrouter_env(env)
    env.setenv("MENU_EXTRACTOR", "gemini")
    env.setenv("EXTRACTION_MODE", mode)
    env.setenv("OPENROUTER_EXTRACTION_PROMPT", "not-a-prompt")
    env.setenv("OPENROUTER_API_KEY", "")
    if prompt:
        env.setenv("EXTRACTION_HYBRID_PROMPT", prompt)

    extractor = deps.get_menu_extractor()

    assert type(extractor) is kind
    assert (extractor.model_name, extractor.provider) == (
        "gemini-3.5-flash-lite", "google" if mode == "gemini" else "naver-clova+google")
    assert extractor.pipeline_version == (
        "bottlemap-menu-gemini-promptv1-thinking-medium" if mode == "gemini"
        else "bottlemap-menu-hybrid-prompthybrid-v2-thinking-medium")


def test_an_unsupported_extractor_lists_openrouter(env):
    env.setenv("MENU_EXTRACTOR", "openai")

    with pytest.raises(RuntimeError, match=r"supported: mock, gemini, openrouter"):
        deps.get_menu_extractor()


# ---- the ladder ----


def test_stage_0_the_primary_model_reads_the_photo(caplog):
    http, gem = FakeHttp(ok()), gemini_fake()

    with caplog.at_level(logging.INFO, logger="app.extraction.routed"):
        result = run(http, gem)

    meta = result["meta"]
    assert [item["rawText"] for item in result["items"]] == ["페른홀로우 12년"]
    assert meta["route"] == {"stage": 0, "path": "openrouter", "model": PRIMARY, "provider": "Google", "skipped": []}
    assert (meta["model"], meta["requestedModel"], meta["fallbackModels"]) == (PRIMARY, PRIMARY, [FALLBACK])
    assert (meta["inputTokens"], meta["outputTokens"], meta["thoughtTokens"], meta["costUsd"]) == (8000, 9000, 4000, 0.03)
    assert (meta["attempts"], meta["truncatedAttempts"], meta["status"]) == (1, 0, "completed")
    assert meta["promptVersion"] == "hybrid-v2.1" and len(meta["otherItems"]) == 3
    assert meta["ocr"]["provider"] == "clova-general-v2" and len(meta["ocr"]["lines"]) == 3
    assert gem.requests == []
    [record] = [r for r in caplog.records if "extraction route stage=" in r.getMessage()]
    assert record.levelno == logging.INFO
    assert f"stage=0 path=openrouter model={PRIMARY} provider=Google input_tokens=8000" in record.getMessage()
    assert "cost_usd=0.03" in record.getMessage() and "skipped=-" in record.getMessage()


def test_the_prompt_sent_is_v2_1_and_v2_when_set():
    http = FakeHttp(ok())

    meta = run(http)["meta"]
    older = run(http, route=replace(ROUTE, prompt="v2"))["meta"]

    sent = http.posts[0]["json"]["messages"][0]["content"]
    assert "카덴헤드(Cadenhead's)" in sent  # the example v2.1 added
    assert meta["promptSha256"] == hashlib.sha256(sent.encode("utf-8")).hexdigest()
    assert meta["promptSha256"] == "b14b09b433057d6f6f4c0f6737c2cd9dac5269ee63ef566930510e8420c02e92"
    assert older["promptVersion"] == "hybrid-v2" and "카덴헤드" not in http.posts[1]["json"]["messages"][0]["content"]
    assert "<ocr_lines>" in http.posts[0]["json"]["messages"][1]["content"][0]["text"]


def test_stage_1_a_fallback_model_answered(caplog):
    http = FakeHttp(ok(model=FALLBACK, provider="Anthropic", cost=0.07))

    with caplog.at_level(logging.INFO, logger="app.extraction.routed"):
        meta = run(http)["meta"]

    assert meta["route"] == {"stage": 1, "path": "openrouter-fallback", "model": FALLBACK, "provider": "Anthropic",
                             "skipped": []}
    assert (meta["model"], meta["requestedModel"], meta["costUsd"]) == (FALLBACK, PRIMARY, 0.07)
    assert len(http.posts) == 1  # OpenRouter moved on by itself: one request
    [record] = [r for r in caplog.records if "extraction route stage=1" in r.getMessage()]
    assert record.levelno == logging.WARNING


@pytest.mark.parametrize("model, stage", [(f"{PRIMARY}-20261101", 0), (f"{FALLBACK}-20261015", 1), (None, 0),
                                          ("someone/else", 0)])
def test_the_stage_is_read_from_the_model_that_answered(model, stage):
    meta = run(FakeHttp(ok(model=model)))["meta"]

    assert meta["route"]["stage"] == stage and meta["model"] == (model or PRIMARY)


def test_stage_2_out_of_credits_goes_to_the_gemini_api(caplog):
    http, gem = FakeHttp(failed(402, "Insufficient credits")), gemini_fake()

    with caplog.at_level(logging.INFO, logger="app.extraction.routed"):
        result = run(http, gem)

    meta = result["meta"]
    assert [item["rawText"] for item in result["items"]] == ["페른홀로우 12년"]
    assert (meta["route"]["stage"], meta["route"]["path"], meta["route"]["model"]) == (2, "gemini-direct", DIRECT)
    assert meta["route"]["skipped"] == [{"stage": 0, "reason": "OpenRouterCreditError",
                                         "message": "HTTP 402: Insufficient credits", "attempts": 1}]
    assert (meta["model"], meta["costUsd"], meta["thinkingLevel"], meta["api"]) == (DIRECT, None, "medium", "interactions")
    assert (meta["inputTokens"], meta["outputTokens"], meta["thoughtTokens"]) == (5000, 300, 700)
    [request] = gem.requests
    assert request["model"] == DIRECT and "카덴헤드" in request["system_instruction"]
    assert "<ocr_lines>" in request["input"][0]["text"] and request["input"][1]["type"] == "image"
    assert len(http.posts) == 1
    assert any(r.levelno == logging.WARNING and "stage=2 path=gemini-direct" in r.getMessage()
               and "skipped=0:OpenRouterCreditError" in r.getMessage() for r in caplog.records)


def test_stage_3_the_lite_model_reads_the_photo_and_the_log_says_so(caplog, fake_ocr):
    http, gem = FakeHttp(failed(503)), gemini_fake(direct=ApiError(429))

    with caplog.at_level(logging.INFO, logger="app.extraction.routed"):
        meta = run(http, gem)["meta"]

    assert (meta["route"]["stage"], meta["route"]["path"]) == (3, "gemini-direct-lite")
    assert meta["model"] == meta["route"]["model"] == "gemini-3.5-flash-lite"
    assert [(s["stage"], s["reason"], s["attempts"]) for s in meta["route"]["skipped"]] == [
        (0, "ModelCallError", 3), (2, "ModelCallError", 2)]
    assert [r["model"] for r in gem.requests] == [DIRECT, DIRECT, "gemini-3.5-flash-lite"]
    assert len(http.posts) == 3 and fake_ocr.calls == 1  # OCR once, whatever the route
    lite = [r for r in caplog.records if "extraction route stage=3 path=gemini-direct-lite" in r.getMessage()]
    assert len(lite) == 1 and lite[0].levelno == logging.WARNING
    assert "skipped=0:ModelCallError,2:ModelCallError" in lite[0].getMessage()


def test_stage_4_every_route_failed(caplog):
    http, gem = FakeHttp(failed(500)), gemini_fake(direct=ApiError(429), lite=ApiError(503))

    with caplog.at_level(logging.ERROR, logger="app.extraction.routed"):
        with pytest.raises(AllRoutesFailedError, match="every extraction route failed: stage 0 ModelCallError") as caught:
            run(http, gem)

    error = caught.value
    assert isinstance(error, extraction.ModelCallError) and error.attempts == 3 + 2 + 2
    assert error.route["stage"] == 4 and [s["stage"] for s in error.route["skipped"]] == [0, 2, 3]
    assert "extraction route stage=4" in caplog.text
    assert "secret-test-key" not in str(error) and "secret-test-key" not in caplog.text


# ---- stage 2 off (EXTRACTION_DIRECT_MODEL empty) ----

NO_DIRECT = replace(ROUTE, direct=None)
DIRECT_OFF = {"stage": 2, "reason": "direct_disabled"}


@pytest.mark.parametrize("value", [None, "", "  "])
def test_without_a_direct_model_stage_2_is_off_and_the_server_starts(env, value):
    set_openrouter_env(env)
    env.delenv("EXTRACTION_DIRECT_MODEL")
    if value is not None:
        env.setenv("EXTRACTION_DIRECT_MODEL", value)
    env.setenv("EXTRACTION_DIRECT_MAX_ATTEMPTS", "1")

    extractor = deps.get_menu_extractor()

    assert isinstance(extractor, OpenRouterMenuExtractor) and extractor.route.direct is None
    assert extractor.route.lite.model == "gemini-3.5-flash-lite"


def test_with_a_direct_model_stage_2_is_on_as_before(env):
    set_openrouter_env(env)

    route = routed.load_route_settings()
    meta = run(FakeHttp(failed(402)), route=route)["meta"]

    assert (route.direct.model, route.direct.max_attempts) == (DIRECT, 2)
    assert (meta["route"]["stage"], meta["route"]["model"]) == (2, DIRECT)
    assert DIRECT_OFF not in meta["route"]["skipped"]


def test_an_invalid_direct_attempts_setting_still_stops_the_server_when_stage_2_is_off(env):
    set_openrouter_env(env)
    env.delenv("EXTRACTION_DIRECT_MODEL")
    env.setenv("EXTRACTION_DIRECT_MAX_ATTEMPTS", "0")

    with pytest.raises(RuntimeError, match="EXTRACTION_DIRECT_MAX_ATTEMPTS must be a positive int"):
        deps.get_menu_extractor()


def test_with_stage_2_off_a_failed_openrouter_call_goes_straight_to_stage_3(caplog):
    http, gem = FakeHttp(failed(402, "Insufficient credits")), gemini_fake()

    with caplog.at_level(logging.INFO, logger="app.extraction.routed"):
        meta = run(http, gem, route=NO_DIRECT)["meta"]

    assert (meta["route"]["stage"], meta["route"]["path"], meta["model"]) == (3, "gemini-direct-lite", "gemini-3.5-flash-lite")
    assert meta["route"]["skipped"] == [
        {"stage": 0, "reason": "OpenRouterCreditError", "message": "HTTP 402: Insufficient credits", "attempts": 1},
        DIRECT_OFF]
    assert [r["model"] for r in gem.requests] == ["gemini-3.5-flash-lite"]  # no stage 2 call
    assert "stage=3 path=gemini-direct-lite" in caplog.text
    assert "skipped=0:OpenRouterCreditError,2:direct_disabled" in caplog.text


def test_with_stage_2_off_over_the_daily_limit_the_photo_goes_straight_to_stage_3():
    http, gem = FakeHttp(ok()), gemini_fake()
    budget = DailyPaidBudget(2, lambda since: 2, lambda: datetime(2026, 11, 26, 3, tzinfo=UTC))

    meta = extract_menu_routed(jpeg(), "image/jpeg", CLOVA, NO_DIRECT, CircuitBreaker(), budget=budget,
                               http_client=http, gemini_client=gem)["meta"]

    assert http.posts == [] and [r["model"] for r in gem.requests] == ["gemini-3.5-flash-lite"]
    assert meta["route"]["stage"] == 3
    assert meta["route"]["skipped"] == [{"stage": 0, "reason": "daily_paid_limit", "limit": 2}, DIRECT_OFF]


def test_with_stage_2_off_and_openrouter_paused_the_photo_goes_straight_to_stage_3():
    breaker = CircuitBreaker(1, 600)
    breaker.record_failure()

    meta = run(FakeHttp(ok()), route=NO_DIRECT, breaker=breaker)["meta"]

    assert meta["route"]["stage"] == 3
    assert meta["route"]["skipped"] == [{"stage": 0, "reason": "circuit_open"}, DIRECT_OFF]


def test_with_stage_2_off_a_photo_read_at_stage_0_records_nothing_about_stage_2():
    meta = run(FakeHttp(ok()), route=NO_DIRECT)["meta"]

    assert meta["route"]["stage"] == 0 and meta["route"]["skipped"] == []


def test_with_stage_2_off_a_failed_lite_call_fails_the_photo_and_says_stage_2_was_off():
    http, gem = FakeHttp(failed(402)), gemini_fake(lite=ApiError(503))

    with pytest.raises(AllRoutesFailedError, match="stage 2 direct_disabled; stage 3 ModelCallError") as caught:
        run(http, gem, route=NO_DIRECT)

    assert caught.value.attempts == 1 + 2  # OpenRouter's one 402, the lite model's two tries
    assert [s["stage"] for s in caught.value.route["skipped"]] == [0, 2, 3]
    assert caught.value.route["skipped"][1] == DIRECT_OFF
    assert [r["model"] for r in gem.requests] == ["gemini-3.5-flash-lite"] * 2


# ---- the circuit breaker ----


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


def test_the_breaker_opens_after_three_failures_and_lets_one_call_through_after_the_cooldown():
    clock = Clock()
    breaker = CircuitBreaker(3, 600, clock)

    assert breaker.allows() and breaker.record_failure() is False and breaker.record_failure() is False
    assert breaker.allows()
    assert breaker.record_failure() is True and not breaker.allows()
    clock.now += 599
    assert not breaker.allows()
    clock.now += 1
    assert breaker.allows()
    assert not breaker.allows()  # only one call is let through after the cooldown, the others wait for it
    assert breaker.record_failure() is True and not breaker.allows()  # the call let through failed: paused again
    clock.now += 600
    breaker.record_success()
    assert breaker.allows() and breaker.record_failure() is False  # the count starts over


def test_a_paused_openrouter_is_skipped_without_a_call_then_tried_again(caplog):
    clock = Clock()
    breaker = CircuitBreaker(3, 600, clock)
    down = FakeHttp(failed(402))

    with caplog.at_level(logging.WARNING, logger="app.extraction.routed"):
        for _ in range(3):
            assert run(down, breaker=breaker)["meta"]["route"]["stage"] == 2
    assert len(down.posts) == 3 and "OpenRouter is paused for 600s" in caplog.text

    meta = run(down, breaker=breaker)["meta"]
    assert len(down.posts) == 3  # no call while paused
    assert meta["route"]["stage"] == 2 and meta["route"]["skipped"] == [{"stage": 0, "reason": "circuit_open"}]

    clock.now += 600
    back = FakeHttp(ok())
    assert run(back, breaker=breaker)["meta"]["route"]["stage"] == 0
    assert run(back, breaker=breaker)["meta"]["route"]["stage"] == 0 and len(back.posts) == 2


def test_the_probe_after_the_cooldown_closes_the_breaker_when_it_succeeds():
    clock = Clock()
    breaker = CircuitBreaker(1, 600, clock)
    breaker.record_failure()
    clock.now += 600

    assert breaker.allows() and not breaker.allows()  # the probe, then a photo that arrives during it
    breaker.record_success()
    assert breaker.allows() and breaker.allows()


def test_photos_that_arrive_during_the_probe_take_the_gemini_api_without_calling_openrouter():
    clock = Clock()
    breaker = CircuitBreaker(1, 600, clock)
    breaker.record_failure()
    clock.now += 600
    assert breaker.allows()  # the probe is under way in another import

    http = FakeHttp(ok())
    meta = run(http, breaker=breaker)["meta"]

    assert http.posts == [] and meta["route"]["skipped"] == [{"stage": 0, "reason": "circuit_open"}]


def test_a_success_between_failures_keeps_the_breaker_closed():
    breaker = CircuitBreaker(3, 600, Clock())

    for http in (FakeHttp(failed(402)), FakeHttp(failed(402)), FakeHttp(ok()), FakeHttp(failed(402)), FakeHttp(failed(402))):
        run(http, breaker=breaker)

    assert breaker.allows()


# ---- answers that arrived but are not valid output ----


def test_a_cut_answer_is_asked_for_once_more_and_both_calls_are_counted():
    http = FakeHttp(ok(text='{"items": [', finish="length", cost=0.2), ok(cost=0.05))

    meta = run(http)["meta"]

    assert len(http.posts) == 2 and meta["route"]["stage"] == 0
    assert (meta["truncatedAttempts"], meta["attempts"], meta["costUsd"], meta["status"]) == (1, 2, 0.25, "completed")


def test_an_answer_cut_twice_fails_the_photo_without_trying_another_route():
    http, gem, breaker = FakeHttp(ok(text='{"items": [', finish="length", cost=0.2)), gemini_fake(), CircuitBreaker(1, 600)

    with pytest.raises(extraction.InvalidModelOutputError, match="ended with status 'length'") as caught:
        run(http, gem, breaker=breaker)

    assert len(http.posts) == 2 and gem.requests == [] and breaker.allows()
    assert caught.value.raw_text == '{"items": [' and caught.value.meta["route"]["stage"] == 0
    assert (caught.value.meta["costUsd"], caught.value.meta["truncatedAttempts"]) == (0.4, 1)


@pytest.mark.parametrize("text", ["{}", "not json", json.dumps({"items": [{"raw_name": "x"}]})])
def test_an_answer_that_is_not_the_schema_fails_the_photo_without_trying_another_route(text):
    http, gem, breaker = FakeHttp(ok(text=text)), gemini_fake(), CircuitBreaker(1, 600)

    with pytest.raises(extraction.InvalidModelOutputError, match="not valid hybrid v2 output") as caught:
        run(http, gem, breaker=breaker)

    assert len(http.posts) == 1 and gem.requests == [] and breaker.allows()
    assert caught.value.raw_text == text and caught.value.meta["rawOutput"] is None


def test_an_answer_without_a_cost_records_none():
    assert run(FakeHttp(ok(cost=None)))["meta"]["costUsd"] is None


# ---- the adapter ----


@pytest.fixture
def extractor(monkeypatch):
    """An extractor whose OpenRouter and Gemini calls go to fakes; set `.http.answers` and `.gemini.by_model`."""
    made = OpenRouterMenuExtractor(ROUTE, CLOVA)
    made.http, made.gemini = FakeHttp(ok()), gemini_fake()
    monkeypatch.setattr(httpx, "post", lambda url, **kwargs: made.http.post(url, **kwargs))
    monkeypatch.setattr(gemini, "make_client", lambda settings: made.gemini)
    return made


def test_the_adapter_returns_every_menu_line_in_order_and_records_the_route(extractor):
    result = extractor.extract(jpeg(), "image/jpeg", "menu.jpg")

    assert [(item.item_order, item.raw_text, item.kind.value) for item in result.items] == [
        (1, "페른홀로우 12년", "whisky"), (2, "페른홀로우 하이볼", "other"), (3, "치즈 플래터", "other"),
        (4, "하우스 와인", "other")]
    assert result.raw_output["route"]["stage"] == 0 and result.raw_output["costUsd"] == 0.03
    assert [source["itemOrder"] for source in result.raw_output["itemSources"]] == [1, 2, 3, 4]


def test_the_adapter_keeps_one_breaker_for_all_photos(extractor):
    extractor.http.answers = [failed(402)]

    stages = [extractor.extract(jpeg(), "image/jpeg", None).raw_output["route"] for _ in range(4)]

    assert [route["stage"] for route in stages] == [2, 2, 2, 2] and len(extractor.http.posts) == 3
    assert stages[3]["skipped"] == [{"stage": 0, "reason": "circuit_open"}]


def test_when_ocr_fails_the_photo_goes_through_the_gemini_only_extractor(extractor, fake_ocr, monkeypatch, caplog):
    fake_ocr.error = ClovaOCRError("CLOVA is down")
    calls = []

    def photo_only(image, mime_type, *, settings=None, client=None):
        calls.append(settings.model)
        return {"items": [], "meta": {"model": settings.model}}

    monkeypatch.setattr(extraction, "extract_menu", photo_only)

    with caplog.at_level(logging.WARNING, logger="app.adapters.openrouter_extraction"):
        result = extractor.extract(jpeg(), "image/jpeg", None)

    assert calls == ["gemini-3.5-flash-lite"] and extractor.http.posts == []
    assert result.raw_output == {"model": "gemini-3.5-flash-lite", "hybridFallback": {"reason": "CLOVA is down"}}
    assert "CLOVA OCR failed, falling back to Gemini only" in caplog.text


def test_an_invalid_answer_fails_the_run_with_the_text_and_the_route(extractor):
    extractor.http.answers = [ok(text="{}")]

    with pytest.raises(ExtractionError, match="InvalidModelOutputError") as caught:
        extractor.extract(jpeg(), "image/jpeg", None)

    assert caught.value.raw_output["rawText"] == "{}" and caught.value.raw_output["route"]["stage"] == 0


def test_when_every_route_fails_the_run_records_what_each_stage_did(extractor):
    extractor.http.answers = [failed(402)]
    extractor.gemini.by_model = {"gemini_3_8_flash": ApiError(429), "gemini_3_5_flash_lite": ApiError(429)}

    with pytest.raises(ExtractionError, match="AllRoutesFailedError: every extraction route failed") as caught:
        extractor.extract(jpeg(), "image/jpeg", None)

    assert caught.value.raw_output["attempts"] == 5
    assert [s["stage"] for s in caught.value.raw_output["route"]["skipped"]] == [0, 2, 3]


def test_a_file_that_is_not_an_image_fails_before_any_call(extractor, fake_ocr):
    with pytest.raises(ExtractionError, match="UnsupportedImageError") as caught:
        extractor.extract(b"not an image", "image/jpeg", None)

    assert caught.value.raw_output is None and fake_ocr.calls == 0 and extractor.http.posts == []


def test_items_the_import_cannot_store_fail_the_run_with_the_meta(extractor, monkeypatch):
    def refuse(payload):
        raise ExtractionError("items[0]: too long")

    monkeypatch.setattr(openrouter_extraction, "parse_extraction_response", refuse)

    with pytest.raises(ExtractionError, match="too long") as caught:
        extractor.extract(jpeg(), "image/jpeg", None)

    assert caught.value.raw_output["route"]["stage"] == 0
