"""CappedToolLLM: the per-import request cap, the retry and the wall-clock limits around the tool
layer's adapter. No API call."""

import logging
import threading

import httpx
import pytest

from app.matching import tool_config
from app.matching.tool_config import CappedToolLLM, ToolCallCapReached, ToolCallTimeout, is_transient


class StatusError(Exception):
    def __init__(self, code, attr="code"):
        super().__init__(f"HTTP {code} with request details")
        setattr(self, attr, code)


class Scripted:
    """Each step returns or raises the next scripted answer."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.steps = 0

    def step(self, system, history, tools):
        self.steps += 1
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


@pytest.fixture(autouse=True)
def waits(monkeypatch):
    waits = []
    monkeypatch.setattr(tool_config, "sleep", waits.append)
    return waits


OK = {"calls": [], "usage": {}}


def test_requests_pass_through_until_the_cap():
    inner = Scripted(OK, OK, OK)
    llm = CappedToolLLM(inner, max_calls=2)

    assert llm.step("s", [], []) is OK and llm.step("s", [], []) is OK
    with pytest.raises(ToolCallCapReached):
        llm.step("s", [], [])
    with pytest.raises(ToolCallCapReached):
        llm.step("s", [], [])

    assert inner.steps == 2 and llm.calls == 2
    assert llm.stats == {"ok": 2, "cap_reached": 2}


def test_a_transient_error_is_retried_once_without_counting_toward_the_cap(waits):
    inner = Scripted(StatusError(503), OK)
    llm = CappedToolLLM(inner, max_calls=1)

    assert llm.step("s", [], []) is OK

    assert inner.steps == 2 and llm.calls == 1 and waits == [tool_config.RETRY_WAIT_S]
    assert llm.stats == {"retry": 1, "ok": 1}


def test_a_second_transient_error_fails_the_request(caplog):
    inner = Scripted(httpx.ReadTimeout("slow"), StatusError(429))
    llm = CappedToolLLM(inner, max_calls=5)

    with caplog.at_level(logging.WARNING, logger="app.matching.tool_config"), pytest.raises(StatusError):
        llm.step("s", [], [])

    assert inner.steps == 2 and llm.stats == {"retry": 1, "error": 1}
    # The type only: the message can carry request details.
    assert "StatusError" in caplog.text and "request details" not in caplog.text


def test_other_errors_are_not_retried(waits):
    inner = Scripted(StatusError(400), OK)
    llm = CappedToolLLM(inner, max_calls=5)

    with pytest.raises(StatusError):
        llm.step("s", [], [])

    assert inner.steps == 1 and waits == [] and llm.stats == {"error": 1}


@pytest.mark.parametrize(
    ("error", "transient"),
    [
        (TimeoutError(), True),
        (ConnectionError(), True),
        (httpx.ConnectError("down"), True),
        (httpx.ReadTimeout("slow"), True),
        (StatusError(429), True),
        (StatusError(500), True),
        (StatusError(504, attr="status_code"), True),
        (StatusError(400), False),
        (StatusError(404, attr="status_code"), False),
        (RuntimeError("bug"), False),
        (ValueError("bad"), False),
    ],
)
def test_transient_errors(error, transient):
    assert is_transient(error) is transient


# ---- wall-clock limits -------------------------------------------------------------------------


class Hanging:
    """A step that blocks until `release` is set (a stalled SDK call), then answers `late`."""

    def __init__(self, late=OK):
        self.release = threading.Event()
        self.late = late
        self.started = 0
        self.finished = threading.Event()

    def step(self, system, history, tools):
        self.started += 1
        self.release.wait(10)
        self.finished.set()
        return self.late


def test_a_hung_turn_is_abandoned_after_the_turn_limit_and_not_retried(caplog, waits):
    inner = Hanging()
    llm = CappedToolLLM(inner, max_calls=5, turn_timeout_s=0.05)

    with caplog.at_level(logging.WARNING, logger="app.matching.tool_config"), pytest.raises(ToolCallTimeout):
        llm.step("s", [], [])

    assert inner.started == 1 and waits == []  # not retried, unlike TimeoutError
    assert llm.calls == 1 and llm.stats == {"timeout": 1}
    assert "abandoned: no response within 0 s" in caplog.text
    assert not is_transient(ToolCallTimeout())
    # The abandoned thread finishes later; its answer goes nowhere and changes nothing.
    inner.release.set()
    assert inner.finished.wait(5)
    assert llm.stats == {"timeout": 1} and llm.calls == 1


def test_an_abandoned_turn_replaces_the_adapter():
    hung, fresh = Hanging(), Scripted(OK)
    made = iter([hung, fresh])
    llm = CappedToolLLM(None, max_calls=5, make_llm=lambda: next(made), turn_timeout_s=0.05)
    assert llm.llm is hung  # a new adapter for the import

    with pytest.raises(ToolCallTimeout):
        llm.step("s", [], [])
    assert llm.llm is fresh
    assert llm.step("s", [], []) is OK and fresh.steps == 1
    hung.release.set()


def test_without_a_factory_the_adapter_is_kept_after_a_timeout():
    inner = Hanging()
    llm = CappedToolLLM(inner, max_calls=5, turn_timeout_s=0.05)
    with pytest.raises(ToolCallTimeout):
        llm.step("s", [], [])
    assert llm.llm is inner
    inner.release.set()


def test_the_thread_gets_a_copy_of_the_history_and_errors_come_back():
    seen = []

    class Recording:
        def step(self, system, history, tools):
            seen.append(history)
            raise StatusError(400)

    history = [{"role": "user", "text": "x"}]
    llm = CappedToolLLM(Recording(), max_calls=5)
    with pytest.raises(StatusError):
        llm.step("s", history, [])
    assert seen == [history] and seen[0] is not history


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(tool_config, "monotonic", clock)
    return clock


def test_a_photo_gets_at_most_its_time_in_all(clock, caplog):
    class Slow:
        steps = 0

        def step(self, system, history, tools):
            Slow.steps += 1
            clock.now += 60
            return OK

    llm = CappedToolLLM(Slow(), max_calls=10, photo_timeout_s=150)
    llm.start_photo()
    assert llm.step("s", [], []) is OK and llm.step("s", [], []) is OK
    llm.step("s", [], [])  # started at 120 s, inside the limit
    with caplog.at_level(logging.WARNING, logger="app.matching.tool_config"), pytest.raises(ToolCallTimeout):
        llm.step("s", [], [])  # 180 s: the photo's time is up, no request is sent

    assert Slow.steps == 3 and llm.calls == 3
    assert llm.stats == {"ok": 3, "photo_timeout": 1}
    assert "over 150 s for one photo" in caplog.text
    # The next photo starts with its full time again.
    llm.start_photo()
    assert llm.step("s", [], []) is OK


def test_a_turn_waits_only_for_what_is_left_of_the_photo(clock):
    inner = Hanging()
    llm = CappedToolLLM(inner, max_calls=5, turn_timeout_s=75, photo_timeout_s=100)
    llm.start_photo()
    clock.now += 99.95  # 0.05 s left

    with pytest.raises(ToolCallTimeout):
        llm.step("s", [], [])
    assert llm.stats == {"timeout": 1}
    inner.release.set()


def test_the_photo_limit_is_checked_again_before_a_retry(clock, monkeypatch):
    monkeypatch.setattr(tool_config, "sleep", lambda seconds: setattr(clock, "now", clock.now + seconds))
    inner = Scripted(StatusError(503), OK)
    llm = CappedToolLLM(inner, max_calls=5, photo_timeout_s=3)
    llm.start_photo()

    with pytest.raises(ToolCallTimeout):
        llm.step("s", [], [])  # the 5 s retry wait used up the photo's 3 s
    assert inner.steps == 1 and llm.stats == {"retry": 1, "photo_timeout": 1}


def test_the_default_limits_follow_m3a():
    from app.adapters import gemini_matching_llm

    llm = CappedToolLLM(Scripted(), max_calls=1)
    assert llm.turn_timeout_s == tool_config.TURN_TIMEOUT_S == gemini_matching_llm.WALL_TIMEOUT_S
    assert llm.photo_timeout_s == tool_config.PHOTO_TIMEOUT_S
    assert llm._photo_deadline is None  # no photo limit before start_photo
