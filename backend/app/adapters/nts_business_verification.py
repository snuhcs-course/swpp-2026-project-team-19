"""The NTS business registration validation API (공공데이터포털, 국세청_사업자등록정보 진위확인 및
상태조회 서비스), behind `BusinessVerifier`.

One POST to `/validate` per check with the number, opening date (YYYYMMDD) and representative
name. `valid = "01"` means the three match; `"02"` means they do not, without saying which one is
wrong. A match also carries the status code (`b_stt_cd`): 01 active, 02 suspended, 03 closed.

The service key goes in the `Authorization` header, not the query string, so it never appears in
a logged URL. Nothing checked here (number, name, date) or the response body is logged.
"""

import logging
import os
from dataclasses import dataclass
from datetime import date

import httpx

from app.adapters.business_verification import BusinessCheck, BusinessVerificationUnavailable
from app.models import BusinessStatus

logger = logging.getLogger(__name__)

VALIDATE_URL = "https://api.odcloud.kr/api/nts-businessman/v1/validate"
# The applicant waits for this inside `POST /api/owner-applications`: two tries of 5 s at most.
TIMEOUT_S = 5.0
MAX_ATTEMPTS = 2
RETRY_STATUS = {429, 500, 502, 503, 504}

MATCHED = "01"
NOT_MATCHED = "02"
STATUS_CODES = {"01": BusinessStatus.ACTIVE, "02": BusinessStatus.SUSPENDED, "03": BusinessStatus.CLOSED}


@dataclass(frozen=True)
class NtsSettings:
    service_key: str

    def __repr__(self) -> str:  # keep the key out of logs and tracebacks
        return "NtsSettings()"


def load_nts_settings() -> NtsSettings | None:
    """None when NTS_SERVICE_KEY is not set: the check is then not configured (spec 3.11.2)."""
    key = os.getenv("NTS_SERVICE_KEY", "").strip()
    return NtsSettings(service_key=key) if key else None


class NtsBusinessVerifier:
    def __init__(self, settings: NtsSettings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client

    def verify(self, business_registration_number: str, representative_name: str, opening_date: date) -> BusinessCheck:
        body = {
            "businesses": [
                {
                    "b_no": business_registration_number,
                    "start_dt": opening_date.strftime("%Y%m%d"),
                    "p_nm": representative_name,
                }
            ]
        }
        payload = self._post(body)
        try:
            result = payload["data"][0]
            valid = result["valid"]
        except (KeyError, IndexError, TypeError) as error:
            raise _unavailable(f"malformed response ({type(error).__name__})") from error
        if valid == NOT_MATCHED:
            return BusinessCheck(matched=False)
        if valid != MATCHED:
            raise _unavailable("unknown valid code")
        status = result.get("status")
        code = status.get("b_stt_cd") if isinstance(status, dict) else None
        return BusinessCheck(matched=True, business_status=STATUS_CODES.get(code))

    def _post(self, body: dict) -> dict:
        headers = {"Authorization": f"Infuser {self.settings.service_key}"}
        client = self.client or httpx.Client()
        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    response = client.post(VALIDATE_URL, json=body, headers=headers, timeout=TIMEOUT_S)
                except httpx.HTTPError as error:
                    failure = f"request failed ({type(error).__name__})"
                else:
                    if response.status_code == 200:
                        try:
                            payload = response.json()
                        except ValueError as error:
                            raise _unavailable("response is not JSON") from error
                        if not isinstance(payload, dict):
                            raise _unavailable("malformed response (not an object)")
                        return payload
                    failure = f"HTTP {response.status_code}"
                    if response.status_code not in RETRY_STATUS:
                        break
                if attempt < MAX_ATTEMPTS:
                    logger.info("NTS business check attempt %d failed: %s; retrying", attempt, failure)
            raise _unavailable(failure)
        finally:
            if self.client is None:
                client.close()


def _unavailable(reason: str) -> BusinessVerificationUnavailable:
    logger.warning("NTS business check unavailable: %s", reason)
    return BusinessVerificationUnavailable(reason)
