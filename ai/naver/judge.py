# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P17). Reviewed by Jinwoo Park.
"""LLM check: is a candidate the same product? (naver_plan.md, 4절)

    verdict = judge(candidate)

candidate (one format for Naver aliases now and menu-line matching (S4) later):
  mode         "alias" | "match"
  product      alias mode: the input product {display_name, brand, age_years, edition_name}
  alias        alias mode: the candidate Korean spelling
  menu_line    match mode: the menu line
  options      match mode: catalog candidates [{product_id, display_name, age_years, edition_name}]
  evidence     [{endpoint, title, snippet, url}] (Naver results; may be empty in match mode)
  matcher_tag  {tag, status, products} from tagger.MatcherTagger.tag (reference only)
verdict:
  verdict      "same" | "different" | "unsure"
  product_id   alias mode: None. match mode: a chosen option id, "new", "none", or None (unsure)
  confidence   0-1
  reason       one line (Korean)
  meta         model, thinking level, prompt version/hash, latency, attempts, tokens

No auto-confirm threshold is applied here (set in P29); verdicts are only recorded.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))

from extract import _create_with_deadline, _is_transient, make_client  # noqa: E402

MODEL = "gemini-3.5-flash-lite"
THINKING_LEVEL = "low"
PROMPT_VERSION = "v1"
PROMPT_PATH = Path(__file__).with_name(f"judge_prompt_{PROMPT_VERSION}.md")
MAX_EVIDENCE = 4
MAX_ATTEMPTS = 5
MIN_INTERVAL_S = 4.5  # <= ~13 requests per minute on the free tier
DEFAULT_BUDGET = 300  # calls per run; the free-tier daily limit is far above one smoke run


class Verdict(BaseModel):
    verdict: Literal["same", "different", "unsure"]
    product_id: Optional[str]
    confidence: float = Field(ge=0, le=1)
    reason: str


class BudgetExceeded(RuntimeError):
    pass


def model_input(candidate: dict) -> dict:
    """The JSON the model sees: the candidate without provenance fields it does not need."""
    out = {"mode": candidate["mode"]}
    for key in ("product", "alias", "menu_line", "options"):
        if candidate.get(key) is not None:
            out[key] = candidate[key]
    out["evidence"] = [{k: e.get(k) for k in ("endpoint", "title", "snippet", "url")}
                       for e in candidate.get("evidence", [])[:MAX_EVIDENCE]]
    tag = candidate.get("matcher_tag")
    if tag:
        out["matcher_tag"] = {"tag": tag["tag"], "status": tag["status"],
                              "products": [p["display_name"] for p in tag.get("products", [])]}
    return out


def check_verdict(candidate: dict, v: Verdict) -> Optional[str]:
    """Consistency of product_id with the mode; returns a problem description or None."""
    if candidate["mode"] == "alias":
        return None if v.product_id is None else "alias mode must return product_id null"
    ids = {str(o["product_id"]) for o in candidate.get("options", [])}
    if v.verdict == "same" and v.product_id not in ids:
        return "match mode 'same' must name one of the options"
    if v.verdict == "different" and v.product_id not in ("new", "none"):
        return "match mode 'different' must be 'new' or 'none'"
    return None


class Judge:
    def __init__(self, client=None, budget: int = DEFAULT_BUDGET, min_interval: float = MIN_INTERVAL_S):
        self._client = client
        self.budget = budget
        self.min_interval = min_interval
        self.prompt = PROMPT_PATH.read_text(encoding="utf-8")
        self.prompt_sha256 = hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()
        self._last = 0.0
        self.stats = {"llm_calls": 0, "retries": 0, "parse_errors": 0, "latency_ms": [],
                      "input_tokens": 0, "output_tokens": 0, "thought_tokens": 0}

    @property
    def client(self):
        if self._client is None:
            self._client = make_client()
        return self._client

    def _request(self, candidate: dict) -> dict:
        return dict(
            model=MODEL,
            system_instruction=self.prompt,
            input=[{"type": "text", "text": json.dumps(model_input(candidate), ensure_ascii=False)}],
            response_format={"type": "text", "mime_type": "application/json",
                             "schema": Verdict.model_json_schema()},
            generation_config={"thinking_level": THINKING_LEVEL},
            store=False,
        )

    def _call(self, request: dict):
        attempts = 0
        while True:
            if self.stats["llm_calls"] >= self.budget:
                raise BudgetExceeded(f"LLM call budget {self.budget} reached")
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            attempts += 1
            self.stats["llm_calls"] += 1
            self._last = time.monotonic()
            t0 = time.perf_counter()
            try:
                interaction = _create_with_deadline(self.client, request)
                return interaction, attempts, round((time.perf_counter() - t0) * 1000)
            except Exception as exc:
                if not _is_transient(exc) or attempts >= MAX_ATTEMPTS:
                    raise
                self.stats["retries"] += 1
                backoff = min(60, 5 * 2 ** (attempts - 1))
                print(f"    judge retry {attempts}/{MAX_ATTEMPTS - 1}: {type(exc).__name__} "
                      f"{str(exc)[:100]} (wait {backoff}s)", file=sys.stderr, flush=True)
                time.sleep(backoff)

    def __call__(self, candidate: dict) -> dict:
        interaction, attempts, latency_ms = self._call(self._request(candidate))
        self.stats["latency_ms"].append(latency_ms)
        usage = interaction.usage
        tokens = {k: getattr(usage, f"total_{k}", None) for k in ("input_tokens", "output_tokens", "thought_tokens")}
        for k, v in tokens.items():
            self.stats[k] += v or 0
        meta = {"model": MODEL, "thinking_level": THINKING_LEVEL, "prompt_version": PROMPT_VERSION,
                "prompt_sha256": self.prompt_sha256, "latency_ms": latency_ms, "attempts": attempts, **tokens}
        text = interaction.output_text or ""
        try:
            v = Verdict.model_validate_json(text)
        except ValidationError as exc:
            self.stats["parse_errors"] += 1
            return {"verdict": "unsure", "product_id": None, "confidence": 0.0,
                    "reason": "parse error", "parse_error": str(exc)[:300], "raw_text": text[:500], "meta": meta}
        out = {**v.model_dump(), "meta": meta}
        problem = check_verdict(candidate, v)
        if problem:
            out["format_problem"] = problem
        return out


_default: Optional[Judge] = None


def judge(candidate: dict) -> dict:
    """judge(candidate) -> verdict, with a shared Judge (rate limit and budget per process)."""
    global _default
    if _default is None:
        _default = Judge()
    return _default(candidate)
