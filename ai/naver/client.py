# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P17). Reviewed by Jinwoo Park.
"""NAVER API HUB (NAVER Cloud) search client with a response cache (naver_plan.md).

    client = NaverSearchClient()
    result = client.search("blog", "Arran 10")

Endpoints and headers follow the ncloud docs (naver-api-hub-overview,
naver-api-hub-search-examples): GET https://naverapihub.apigw.ntruss.com/search/v1/<endpoint>,
headers X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY, 25,000 calls per day for the
Search API. Shopping search is not offered by API HUB and is not used.

Keys are read only from .env (repo root, then the workspace next to the data dir) and
never written to the cache, results or log lines. Responses are cached in
<data_dir>/naver_cache/ (outside the repo); a cached result keeps its original fetch time.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "https://naverapihub.apigw.ntruss.com/search/v1"
ENDPOINTS = ("blog", "webkr", "encyc", "cafearticle")
ID_HEADER = "X-NCP-APIGW-API-KEY-ID"
SECRET_HEADER = "X-NCP-APIGW-API-KEY"
MIN_INTERVAL_S = 0.25  # at most 4 calls per second (limit: 5)
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
TIMEOUT_S = 15


def data_dir() -> Path:
    load_dotenv(REPO_ROOT / ".env")
    raw = os.environ.get("BOTTLEMAP_DATA_DIR") or "../bottlemap-p14/data"
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def load_env() -> None:
    """Repo .env first; the workspace .env (next to the data dir) fills in missing names."""
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(data_dir().parent / ".env")


class NaverSearchError(RuntimeError):
    pass


class NaverSearchClient:
    def __init__(self, cache_dir: Path | None = None, transport: httpx.BaseTransport | None = None,
                 min_interval: float = MIN_INTERVAL_S, use_cache: bool = True):
        self.cache_dir = cache_dir if cache_dir is not None else data_dir() / "naver_cache"
        self.use_cache = use_cache
        self.min_interval = min_interval
        self._transport = transport
        self._http: httpx.Client | None = None
        self._last_call = 0.0
        self._lock = threading.Lock()
        # Counters for the run log (no keys).
        self.stats = {"api_calls": 0, "cache_hits": 0, "retries": 0, "errors": 0, "latency_ms": []}

    def _client(self) -> httpx.Client:
        if self._http is None:
            load_env()
            client_id = os.environ.get("NAVER_HUB_CLIENT_ID")
            secret = os.environ.get("NAVER_HUB_CLIENT_SECRET")
            if not client_id or not secret:
                raise NaverSearchError("NAVER_HUB_CLIENT_ID / NAVER_HUB_CLIENT_SECRET are not set in .env")
            self._http = httpx.Client(base_url=BASE_URL, timeout=TIMEOUT_S, transport=self._transport,
                                      headers={ID_HEADER: client_id, SECRET_HEADER: secret})
        return self._http

    @staticmethod
    def _params(query: str, display: int, start: int) -> dict:
        return {"query": query, "display": display, "start": start}

    def _cache_path(self, endpoint: str, params: dict) -> Path:
        key = hashlib.sha256(json.dumps([endpoint, params], ensure_ascii=False, sort_keys=True)
                             .encode("utf-8")).hexdigest()[:32]
        return self.cache_dir / endpoint / f"{key}.json"

    def _throttle(self) -> None:
        with self._lock:
            wait = self._last_call + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def search(self, endpoint: str, query: str, display: int = 10, start: int = 1) -> dict:
        """Return {endpoint, query, request (path + params, no keys), fetched_at, from_cache,
        total, items}. Items are the API items unchanged (title/description keep <b> tags)."""
        if endpoint not in ENDPOINTS:
            raise ValueError(f"unsupported endpoint {endpoint!r}; use one of {ENDPOINTS}")
        params = self._params(query, display, start)
        path = self._cache_path(endpoint, params)
        if self.use_cache and path.exists():
            self.stats["cache_hits"] += 1
            return {**json.loads(path.read_text(encoding="utf-8")), "from_cache": True}

        body, latency_ms = self._get(endpoint, params)
        record = {
            "endpoint": endpoint,
            "query": query,
            "request": f"GET /search/v1/{endpoint}?{urlencode(params)}",
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "latency_ms": latency_ms,
            "total": body.get("total"),
            "items": body.get("items", []),
        }
        if self.use_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        return {**record, "from_cache": False}

    def _get(self, endpoint: str, params: dict) -> tuple[dict, int]:
        client = self._client()
        attempts = 0
        while True:
            attempts += 1
            self._throttle()
            t0 = time.perf_counter()
            try:
                response = client.get(f"/{endpoint}", params=params)
                status = response.status_code
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                response, status = None, None
                detail = type(exc).__name__
            latency_ms = round((time.perf_counter() - t0) * 1000)
            self.stats["api_calls"] += 1
            self.stats["latency_ms"].append(latency_ms)
            if status == 200:
                return response.json(), latency_ms
            if response is not None:
                detail = f"HTTP {status}: {_error_text(response)}"
            if (status is None or status in RETRY_STATUS) and attempts < MAX_ATTEMPTS:
                self.stats["retries"] += 1
                wait = 2 ** attempts
                print(f"    naver retry {attempts}/{MAX_ATTEMPTS - 1} {endpoint}: {detail} (wait {wait}s)",
                      file=sys.stderr, flush=True)
                time.sleep(wait)
                continue
            self.stats["errors"] += 1
            raise NaverSearchError(f"{endpoint} {params.get('query')!r}: {detail}")


def _error_text(response: httpx.Response) -> str:
    """Error code and message from either error body format (gateway or search API)."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body.get("error"), dict):
        err = body["error"]
        return f"{err.get('errorCode')} {err.get('message')}"
    return f"{body.get('errorCode') or body.get('errId')} {body.get('errorMessage') or body.get('errMsg')}"
