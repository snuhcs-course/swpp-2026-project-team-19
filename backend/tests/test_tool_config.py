"""CappedToolLLM: the per-import request cap and the retry around the tool layer's adapter. No API call."""

import logging

import httpx
import pytest

from app.matching import tool_config
from app.matching.tool_config import CappedToolLLM, ToolCallCapReached, is_transient


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
