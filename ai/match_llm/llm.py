"""Gemini calls for the matching LLM layer, with a response cache and a call cap (eval_plan.md, M3).

    llm = CachedLLM(cache_dir)
    parsed, record = llm.call("m3a", prompt_text, input_obj, Schema)

Responses are cached by (model, thinking level, prompt SHA-256, input JSON); a cache hit
makes no API call and does not count toward the cap. With `cache_only` a miss is an error,
so rescoring never calls the API. The API key is read only from GEMINI_API_KEY in .env
(via extract.make_client) and is never written to the cache.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))

from extract import HardTimeout, _create_with_deadline, _is_transient, make_client  # noqa: E402

MODEL = "gemini-3.1-flash-lite"
THINKING_LEVEL = "low"
CALL_LIMIT = 200  # API calls per run (retries count); eval_plan.md M3 원칙 5
MAX_ATTEMPTS = 5
MIN_INTERVAL_S = 4.5


class CallLimitReached(RuntimeError):
    pass


class CacheMiss(RuntimeError):
    pass


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CachedLLM:
    def __init__(self, cache_dir: Path, cache_only: bool = False, limit: int = CALL_LIMIT,
                 min_interval: float = MIN_INTERVAL_S, client=None):
        self.cache_dir = Path(cache_dir)
        self.cache_only = cache_only
        self.limit = limit
        self.min_interval = min_interval
        self._client = client
        self._last = 0.0
        # Per kind ("m3a", "m3b"): API calls made, cache hits, and usage of the requests behind them
        # (from the cache record for hits, so a rescore reports the same latency and tokens).
        self.stats: dict[str, dict] = {}

    @property
    def api_calls(self) -> int:
        return sum(s["api_calls"] for s in self.stats.values())

    def _kind_stats(self, kind: str) -> dict:
        return self.stats.setdefault(kind, {"requests": 0, "api_calls": 0, "cache_hits": 0, "parse_errors": 0,
                                            "latency_ms": [], "input_tokens": 0, "output_tokens": 0,
                                            "thought_tokens": 0})

    def call(self, kind: str, prompt: str, input_obj: dict, schema: type[BaseModel]) -> tuple[dict | None, dict]:
        """Returns (parsed output or None on a parse error, cache record)."""
        input_json = json.dumps(input_obj, ensure_ascii=False, sort_keys=True)
        prompt_sha = sha256_text(prompt)
        key = sha256_text(json.dumps([MODEL, THINKING_LEVEL, prompt_sha, input_json], ensure_ascii=False))
        path = self.cache_dir / f"{key}.json"
        stats = self._kind_stats(kind)
        stats["requests"] += 1
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            stats["cache_hits"] += 1
        elif self.cache_only:
            raise CacheMiss(f"{kind} input not in cache {self.cache_dir} (key {key[:12]})")
        else:
            record = self._request(kind, prompt, prompt_sha, input_obj, schema, key)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        meta = record["meta"]
        stats["latency_ms"].append(meta["latency_ms"])
        for name in ("input_tokens", "output_tokens", "thought_tokens"):
            stats[name] += meta.get(name) or 0
        try:
            parsed = schema.model_validate_json(record["output_text"]).model_dump()
        except ValidationError:
            stats["parse_errors"] += 1
            parsed = None
        return parsed, record

    def _request(self, kind, prompt, prompt_sha, input_obj, schema, key) -> dict:
        request = dict(
            model=MODEL,
            system_instruction=prompt,
            input=[{"type": "text", "text": json.dumps(input_obj, ensure_ascii=False)}],
            response_format={"type": "text", "mime_type": "application/json", "schema": schema.model_json_schema()},
            generation_config={"thinking_level": THINKING_LEVEL},
            store=False,
        )
        stats = self._kind_stats(kind)
        attempts = 0
        while True:
            if self.api_calls >= self.limit:
                raise CallLimitReached(f"LLM call limit {self.limit} reached; stopping (eval_plan.md M3 원칙 5)")
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            attempts += 1
            stats["api_calls"] += 1
            self._last = time.monotonic()
            started_at = datetime.now(timezone.utc).isoformat()
            t0 = time.perf_counter()
            try:
                if self._client is None:
                    self._client = make_client()
                interaction = _create_with_deadline(self._client, request)
                break
            except Exception as exc:
                if not _is_transient(exc) or attempts >= MAX_ATTEMPTS:
                    raise
                if isinstance(exc, HardTimeout):
                    self._client = None
                backoff = min(60, 5 * 2 ** (attempts - 1))
                print(f"    {kind} retry {attempts}/{MAX_ATTEMPTS - 1}: {type(exc).__name__} {str(exc)[:100]} "
                      f"(wait {backoff}s)", file=sys.stderr, flush=True)
                time.sleep(backoff)
        latency_ms = round((time.perf_counter() - t0) * 1000)
        usage = interaction.usage
        return {
            "key": key, "kind": kind, "input": input_obj, "output_text": interaction.output_text or "",
            "meta": {"model": MODEL, "thinking_level": THINKING_LEVEL, "prompt_sha256": prompt_sha,
                     "started_at": started_at, "latency_ms": latency_ms, "attempts": attempts,
                     **{name: getattr(usage, f"total_{name}", None)
                        for name in ("input_tokens", "output_tokens", "thought_tokens")}},
        }

    def summary(self) -> dict:
        out = {}
        for kind, s in self.stats.items():
            lat = s["latency_ms"]
            out[kind] = {**{k: v for k, v in s.items() if k != "latency_ms"},
                         "mean_latency_ms": round(sum(lat) / len(lat)) if lat else None}
        return {"model": MODEL, "thinking_level": THINKING_LEVEL, "api_calls_this_run": self.api_calls,
                "by_kind": out}
