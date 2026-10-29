"""The NTS business check adapter, through httpx.MockTransport; no test calls the real API."""

import json
import logging
from datetime import date

import httpx
import pytest

from app.adapters.business_verification import BusinessVerificationUnavailable
from app.adapters.nts_business_verification import (
    MAX_ATTEMPTS,
    VALIDATE_URL,
    NtsBusinessVerifier,
    NtsSettings,
    load_nts_settings,
)
from app.api.deps import get_business_verifier
from app.models import BusinessStatus

KEY = "secret-service-key"
NUMBER = "1234567891"
NAME = "김사장"
OPENED = date(2020, 3, 2)


def nts_result(valid: str, status_code: str | None = "01") -> dict:
    """A `/validate` answer shaped like the real ones (both checked by hand on 2026-10-29): a mismatch
    has `valid_msg` and no `status`; a match has `status` with the fields of the `/status` API."""
    result = {"b_no": NUMBER, "valid": valid, "request_param": {"b_no": NUMBER, "start_dt": "20200302", "p_nm": NAME}}
    if valid == "02":
        result["valid_msg"] = "확인할 수 없습니다."
    if status_code is not None:
        result["status"] = {"b_no": NUMBER, "b_stt": "계속사업자", "b_stt_cd": status_code}
    return {"status_code": "OK", "request_cnt": 1, "valid_cnt": int(valid == "01"), "data": [result]}


def verifier_with(*responses):
    """A verifier whose calls get `responses` in order (an httpx.Response, a dict for a 200 JSON body,
    or an exception to raise). Returns it with the list of requests sent."""
    sent: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(200, json=answer) if isinstance(answer, dict) else answer

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return NtsBusinessVerifier(NtsSettings(KEY), client=client), sent


def verify(verifier):
    return verifier.verify(NUMBER, NAME, OPENED)


def test_sends_the_three_values_with_the_key_in_a_header():
    verifier, sent = verifier_with(nts_result("01"))

    verify(verifier)

    request = sent[0]
    assert request.method == "POST"
    assert str(request.url) == VALIDATE_URL
    assert request.headers["Authorization"] == f"Infuser {KEY}"
    assert json.loads(request.content) == {"businesses": [{"b_no": NUMBER, "start_dt": "20200302", "p_nm": NAME}]}


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("01", BusinessStatus.ACTIVE),
        ("02", BusinessStatus.SUSPENDED),
        ("03", BusinessStatus.CLOSED),
        ("", None),
        (None, None),
    ],
)
def test_a_match_carries_the_business_status(code, status):
    verifier, _ = verifier_with(nts_result("01", status_code=code))

    check = verify(verifier)

    assert check.matched is True
    assert check.business_status == status


def test_a_mismatch_is_an_answer_not_a_failure():
    verifier, _ = verifier_with(nts_result("02", status_code=None))

    check = verify(verifier)

    assert check.matched is False
    assert check.business_status is None


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(httpx.Response(503), id="5xx"),
        pytest.param(httpx.Response(429), id="rate limited"),
        pytest.param(httpx.ConnectTimeout("timeout"), id="timeout"),
        pytest.param(httpx.ConnectError("refused"), id="network error"),
    ],
)
def test_retries_once_then_gives_up(answer):
    verifier, sent = verifier_with(answer, answer)

    with pytest.raises(BusinessVerificationUnavailable):
        verify(verifier)
    assert len(sent) == MAX_ATTEMPTS


def test_a_retry_that_succeeds_is_an_answer():
    verifier, sent = verifier_with(httpx.Response(502), nts_result("01"))

    assert verify(verifier).matched is True
    assert len(sent) == 2


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(httpx.Response(401, json={"code": -4, "msg": "등록되지 않은 인증키 입니다."}), id="bad key"),
        pytest.param(httpx.Response(400), id="bad request"),
    ],
)
def test_client_errors_are_not_retried(answer):
    verifier, sent = verifier_with(answer)

    with pytest.raises(BusinessVerificationUnavailable):
        verify(verifier)
    assert len(sent) == 1


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(httpx.Response(200, content=b"<html>"), id="not JSON"),
        pytest.param(httpx.Response(200, json=[]), id="not an object"),
        pytest.param({"status_code": "OK"}, id="no data"),
        pytest.param({"data": []}, id="empty data"),
        pytest.param({"data": ["x"]}, id="item not an object"),
        pytest.param({"data": [{"b_no": NUMBER}]}, id="no valid"),
        pytest.param({"data": [{"valid": "99"}]}, id="unknown valid code"),
    ],
)
def test_unexpected_responses_are_failures(answer):
    verifier, _ = verifier_with(answer)

    with pytest.raises(BusinessVerificationUnavailable):
        verify(verifier)


def test_logs_carry_neither_the_values_nor_the_key(caplog):
    verifier, _ = verifier_with(httpx.Response(503, text=f"{NUMBER} {NAME}"), httpx.Response(503))

    with caplog.at_level(logging.DEBUG), pytest.raises(BusinessVerificationUnavailable) as error:
        verify(verifier)

    logged = caplog.text + str(error.value) + repr(verifier.settings)
    for secret in (KEY, NUMBER, NAME, "20200302"):
        assert secret not in logged


def test_closes_the_client_it_opens(monkeypatch):
    closed = []

    class Client(httpx.Client):
        def close(self):
            closed.append(True)
            super().close()

    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=nts_result("01")))
    monkeypatch.setattr(httpx, "Client", lambda: Client(transport=transport))

    assert NtsBusinessVerifier(NtsSettings(KEY)).verify(NUMBER, NAME, OPENED).matched is True
    assert closed == [True]


def test_the_key_setting_turns_the_check_on(monkeypatch):
    assert load_nts_settings() is None
    assert get_business_verifier() is None

    monkeypatch.setenv("NTS_SERVICE_KEY", f"  {KEY}  ")

    assert load_nts_settings() == NtsSettings(KEY)
    assert isinstance(get_business_verifier(), NtsBusinessVerifier)
