"""Unit tests for the retry, timeout and response handling of extract.py.

A fake client stands in for Gemini, so no network call or API key is needed,
and time.sleep is replaced so retries do not wait.
"""

import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import extract  # noqa: E402
from google.genai._gaos.lib.compat_errors import APIConnectionError  # noqa: E402

VALID_OUTPUT = {"items": [{"raw_name": "Glenfiddich 12", "price_krw": 15000, "pour_ml": 30, "unit": "glass"}]}


class HttpError(Exception):
    """An SDK-style error that carries an HTTP status code."""

    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


def interaction(text):
    dump = {
        "status": "completed",
        "input": ["image bytes"],
        "system_instruction": "prompt",
        "steps": [{"type": "user_input"}, {"type": "model_output"}],
    }
    return SimpleNamespace(
        output_text=text,
        status="completed",
        usage=SimpleNamespace(total_input_tokens=10, total_output_tokens=20,
                              total_thought_tokens=0, total_tokens=30),
        model_dump=lambda mode, exclude_none: dict(dump),
    )


class FakeClient:
    """Raises the queued errors in order, then returns the response."""

    def __init__(self, errors=(), text=json.dumps(VALID_OUTPUT)):
        self.errors = list(errors)
        self.text = text
        self.calls = 0

    @property
    def interactions(self):
        return self

    def create(self, **request):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return interaction(self.text)


@pytest.fixture
def no_io(monkeypatch, tmp_path):
    """No real photo, prompt file, sleep or client: record the waits instead."""
    photo = tmp_path / "menu.jpg"
    photo.write_bytes(b"jpeg bytes")
    monkeypatch.setattr(extract, "prepare_image", lambda src: photo)
    monkeypatch.setattr(extract, "load_prompt", lambda: "prompt")
    waits = []
    monkeypatch.setattr(extract.time, "sleep", waits.append)
    monkeypatch.setattr(extract, "make_client", lambda: pytest.fail("make_client must not be called"))
    return SimpleNamespace(photo=photo, waits=waits)


# ---- _status_code / _is_transient ----

def test_status_code_reads_code_or_status_code_attribute():
    assert extract._status_code(HttpError(503)) == 503
    assert extract._status_code(SimpleNamespace(status_code=429)) == 429


def test_status_code_without_integer_code_is_none():
    assert extract._status_code(ValueError("x")) is None
    assert extract._status_code(SimpleNamespace(code="503")) is None


# Written out, not read from extract.RETRY_STATUS, so removing a code from it fails a test.
@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_is_transient_retry_status_codes(code):
    assert extract._is_transient(HttpError(code))


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_is_transient_client_errors_are_not_retried(code):
    assert not extract._is_transient(HttpError(code))


def test_is_transient_timeouts_and_network_errors():
    request = httpx.Request("POST", "https://example.test")
    assert extract._is_transient(extract.HardTimeout("hung"))
    assert extract._is_transient(APIConnectionError(request=request))
    assert extract._is_transient(httpx.ReadTimeout("slow", request=request))
    assert extract._is_transient(httpx.ConnectError("down", request=request))


def test_is_transient_other_errors_are_not_retried():
    assert not extract._is_transient(ValueError("bad input"))


# ---- call_model: retries ----

def test_call_model_retries_transient_error_then_succeeds(no_io):
    client = FakeClient(errors=[HttpError(503)])

    record = extract.call_model(no_io.photo, "A", client=client)

    assert client.calls == 2
    assert record["attempts"] == 2
    assert no_io.waits == [5]
    assert record["output"] == VALID_OUTPUT


def test_call_model_does_not_retry_non_transient_error(no_io):
    client = FakeClient(errors=[HttpError(400)])

    with pytest.raises(HttpError):
        extract.call_model(no_io.photo, "A", client=client)

    assert client.calls == 1
    assert no_io.waits == []


def test_call_model_gives_up_after_max_attempts_with_capped_backoff(no_io):
    client = FakeClient(errors=[HttpError(429)] * extract.MAX_ATTEMPTS)

    with pytest.raises(HttpError):
        extract.call_model(no_io.photo, "A", client=client)

    assert client.calls == extract.MAX_ATTEMPTS
    assert no_io.waits == [5, 10, 20, 40, 60]


def test_call_model_replaces_client_after_hard_timeout(no_io, monkeypatch):
    hung = FakeClient(errors=[extract.HardTimeout("hung")])
    fresh = FakeClient()
    monkeypatch.setattr(extract, "make_client", lambda: fresh)

    record = extract.call_model(no_io.photo, "A", client=hung)

    assert (hung.calls, fresh.calls) == (1, 1)
    assert record["attempts"] == 2


# ---- call_model / extract: response handling ----

def test_call_model_records_request_settings_and_usage(no_io):
    record = extract.call_model(no_io.photo, "B", client=FakeClient())

    assert record["model"] == "gemini-3.6-flash"
    assert record["thinking_level"] == "medium"
    assert record["parse_error"] is None
    assert (record["input_tokens"], record["output_tokens"], record["total_tokens"]) == (10, 20, 30)


def test_call_model_raw_response_drops_echoed_request(no_io):
    record = extract.call_model(no_io.photo, "A", client=FakeClient())

    assert "input" not in record["raw_response"]
    assert "system_instruction" not in record["raw_response"]
    assert record["raw_response"]["steps"] == [{"type": "model_output"}]


def test_call_model_unparseable_output_is_recorded_not_raised(no_io):
    record = extract.call_model(no_io.photo, "A", client=FakeClient(text="not json"))

    assert record["output"] is None
    assert record["parse_error"]
    assert record["raw_text"] == "not json"


def test_extract_raises_on_unparseable_output(no_io, monkeypatch):
    monkeypatch.setattr(extract, "make_client", lambda: FakeClient(text='{"items": "oops"}'))

    with pytest.raises(ValueError, match="unparseable response"):
        extract.extract(no_io.photo, "A")


def test_extract_returns_items(no_io, monkeypatch):
    monkeypatch.setattr(extract, "make_client", lambda: FakeClient())

    assert extract.extract(no_io.photo, "A") == VALID_OUTPUT


# ---- _create_with_deadline / make_client ----

def test_create_with_deadline_raises_hard_timeout_for_hung_call(monkeypatch):
    release = threading.Event()

    class HungClient(FakeClient):
        def create(self, **request):
            release.wait(5)

    monkeypatch.setattr(extract, "WALL_TIMEOUT_S", 0.05)
    try:
        with pytest.raises(extract.HardTimeout):
            extract._create_with_deadline(HungClient(), {})
    finally:
        release.set()


def test_create_with_deadline_passes_worker_error_to_caller():
    with pytest.raises(HttpError):
        extract._create_with_deadline(FakeClient(errors=[HttpError(500)]), {})


def test_make_client_without_api_key_raises(monkeypatch):
    monkeypatch.setattr(extract, "load_dotenv", lambda path: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        extract.make_client()
