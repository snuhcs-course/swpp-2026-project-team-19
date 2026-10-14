# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-15, M4). Reviewed by Jinwoo Park.
"""M4: Naver evidence + judge.py match mode on lines still open after M3a (ai/docs/m4_plan.md).

    m4 = M4(m3_engine, naver_client, judge_fn)
    result, info = m4.resolve(photo_id, name, catalog, current)

`current` is the line's result after S1+S2b+S3 (and M3a for "M3a+M4"). Target lines: no
candidate, or two or more candidates without a confirm recommended rank 1 (gold-free).
For a target line with a whisky translation:
  1. Naver: the menu line as printed, then the English name built from the M3a translation;
     blog, webkr, cafearticle; display 10 (cached in <data_dir>/naver_cache/).
  2. Evidence: results deduplicated by URL, ranked by how many line tokens they contain; top 4.
  3. Options (max 20): current candidates, the translation's brand family (M3b family), and
     products whose core tokens all appear in one Naver result (same age when the line has one).
  4. judge(match mode) picks an option id, "new", "none" or unsure.
  5. A pick passes the four M3a vetoes (M3._check) and is merged like M3a (m3.combine): never
     exact, confirm recommended only when the current result had no candidate or the pick
     is among the current candidates and no short edition token is missing.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "naver"))
sys.path.insert(0, str(Path(__file__).parent))

from app.core.normalize import normalize  # noqa: E402
from app.matching.types import CatalogLookup, ResolutionResult  # noqa: E402
from candidates import clean_text  # noqa: E402
from m3 import M3, combine, core_tokens, english_name, line_age, tokens, translation_tokens  # noqa: E402

ENDPOINTS = ("blog", "webkr", "cafearticle")
DISPLAY = 10
MAX_EVIDENCE = 4
MAX_OPTIONS = 20
STAGE = "M4"
CONFIRMED = ("exact_match", "multi")
_HANGUL_WORD = re.compile(r"[가-힣]{2,}")


def is_target(r: ResolutionResult) -> bool:
    if r.status in CONFIRMED:
        return False
    if not r.candidates:
        return True
    return len(r.candidates) >= 2 and not r.candidates[0].evidence.get("confirmRecommended")


def line_keys(name: str, t: dict) -> tuple[set[str], list[str]]:
    """(latin/number tokens of the line and translation, Korean words of the printed line)."""
    keys = translation_tokens(t) | set(tokens(name))
    if t.get("age") is not None:
        keys.add(str(t["age"]))
    return keys, [normalize(w) for w in _HANGUL_WORD.findall(name)]


class M4:
    def __init__(self, m3: M3, naver, judge_fn, cache_dir: Path | None = None):
        """`judge_fn(candidate) -> verdict` (judge.Judge or quota.GuardedJudge); `cache_dir` keeps verdicts."""
        self.m3 = m3
        self.naver = naver
        self.judge = judge_fn
        self.cache_dir = cache_dir
        self.stats = {"target_lines": 0, "skipped_translation": 0, "no_options": 0, "llm_requests": 0,
                      "llm_cache_hits": 0, "naver_requests": 0, "naver_errors": 0,
                      "naver_ms": [], "llm_ms": [], "line_ms": []}

    # --- Naver -----------------------------------------------------------------------

    def queries(self, name: str, t: dict) -> list[str]:
        return list(dict.fromkeys(q for q in (name, english_name(t)) if q))

    def search(self, name: str, t: dict) -> tuple[list[dict], int, list[str]]:
        """Naver items as {endpoint, query, url, title, snippet, fetched_at}; latency of cache misses."""
        items, ms, errors = [], 0, []
        for q in self.queries(name, t):
            for ep in ENDPOINTS:
                self.stats["naver_requests"] += 1
                try:
                    res = self.naver.search(ep, q, display=DISPLAY)
                except Exception as exc:  # NaverSearchError: recorded, the line goes on with what it has
                    self.stats["naver_errors"] += 1
                    errors.append(f"{ep} {q!r}: {str(exc)[:120]}")
                    continue
                if not res.get("from_cache"):
                    ms += res.get("latency_ms") or 0
                for it in res["items"]:
                    items.append({"endpoint": ep, "query": q, "url": it.get("link") or it.get("url") or "",
                                  "title": clean_text(it.get("title", "")),
                                  "snippet": clean_text(it.get("description", "")),
                                  "fetched_at": res.get("fetched_at")})
        seen, out = set(), []
        for it in items:
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            out.append(it)
        return out, ms, errors

    @staticmethod
    def rank_evidence(items: list[dict], name: str, t: dict) -> list[dict]:
        keys, ko = line_keys(name, t)

        def score(it: dict) -> int:
            text = f"{it['title']} {it['snippet']}"
            have = set(tokens(text))
            flat = normalize(text)
            return len(keys & have) + sum(w in flat for w in ko)

        return sorted(items, key=lambda it: -score(it))  # stable: API order breaks ties

    # --- options -----------------------------------------------------------------------

    def options(self, name: str, t: dict, catalog: CatalogLookup, current: ResolutionResult,
                items: list[dict]) -> list[tuple[UUID, str]]:
        out: dict[UUID, str] = {}
        for c in current.candidates:
            out.setdefault(c.product_id, "current")
        for pid in self.m3.family(t, catalog):
            out.setdefault(pid, "family")
        age = line_age(name, t)
        catalog_ids = set(self.m3._catalog_products(catalog))
        for it in items:
            have = set(tokens(f"{it['title']} {it['snippet']}"))
            for pid in catalog_ids:
                if pid in out:
                    continue
                product = self.m3.products[pid]
                core = core_tokens(product)
                if core and set(core) <= have and (age is None or product.age_years == age):
                    out[pid] = "naver"
        return list(out.items())[:MAX_OPTIONS]

    # --- judge -------------------------------------------------------------------------

    def _judge(self, candidate: dict) -> dict:
        prompt_sha = getattr(self.judge, "prompt_sha256", "")
        key = hashlib.sha256(json.dumps([prompt_sha, candidate], ensure_ascii=False, sort_keys=True,
                                        default=str).encode("utf-8")).hexdigest()
        path = self.cache_dir / f"{key}.json" if self.cache_dir else None
        self.stats["llm_requests"] += 1
        if path is not None and path.exists():
            self.stats["llm_cache_hits"] += 1
            return json.loads(path.read_text(encoding="utf-8"))["verdict"]
        verdict = self.judge(candidate)
        self.stats["llm_ms"].append(verdict.get("meta", {}).get("latency_ms") or 0)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"key": key, "candidate": candidate, "verdict": verdict}, ensure_ascii=False,
                                       indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
        return verdict

    # --- one line ------------------------------------------------------------------------

    def resolve(self, photo_id: str, name: str, catalog: CatalogLookup,
                current: ResolutionResult) -> tuple[ResolutionResult, dict | None]:
        if not is_target(current):
            return current, None
        t = self.m3.translation(photo_id, name)
        if t is None or t["kind"] != "whisky":
            self.stats["skipped_translation"] += 1
            return current, {"m4": "skipped", "why": "no_translation" if t is None else t["kind"]}
        self.stats["target_lines"] += 1
        t0 = time.perf_counter()
        items, naver_ms, errors = self.search(name, t)
        ranked = self.rank_evidence(items, name, t)
        evidence = [{k: it[k] for k in ("endpoint", "title", "snippet", "url")} for it in ranked[:MAX_EVIDENCE]]
        opts = self.options(name, t, catalog, current, ranked)
        info: dict = {"m4": "no_options", "queries": self.queries(name, t), "naver_items": len(items),
                      "naver_errors": errors, "evidence": [{k: e[k] for k in ("endpoint", "url", "title")} for e in evidence],
                      "options": [{"product": self.m3.products[p].display_name, "via": via} for p, via in opts]}
        self.stats["naver_ms"].append(naver_ms)
        if not opts:
            self.stats["no_options"] += 1
            self.stats["line_ms"].append(round((time.perf_counter() - t0) * 1000))
            return current, info
        candidate = {"mode": "match", "menu_line": name,
                     "options": [{"product_id": str(p), "display_name": self.m3.products[p].display_name,
                                  "age_years": self.m3.products[p].age_years,
                                  "edition_name": self.m3.products[p].edition_name} for p, _ in opts],
                     "evidence": evidence}
        verdict = self._judge(candidate)
        self.stats["line_ms"].append(round((time.perf_counter() - t0) * 1000))
        info.update(m4=verdict["verdict"], product_id=verdict.get("product_id"), confidence=verdict.get("confidence"),
                    reason=verdict.get("reason"), format_problem=verdict.get("format_problem"))
        pick = verdict.get("product_id")
        if verdict["verdict"] != "same" or pick not in {str(p) for p, _ in opts}:
            return current, info
        pid = UUID(pick)
        info["picked"] = self.m3.products[pid].display_name
        self.m3._no_confirm = {}
        kept, vetoed = self.m3._check(name, t, {pid: ["m4"]}, catalog)
        info["vetoed"] = vetoed
        if not kept:
            info["m4"] = "vetoed"
            return current, info
        if self.m3._no_confirm:
            info["short_unverified"] = {self.m3.products[p].display_name: s for p, s in self.m3._no_confirm.items()}
        r = combine(current, kept, "merge", STAGE, set(self.m3._no_confirm))
        info["raised_confirm"] = bool(r.candidates[0].evidence.get("confirmRecommended"))
        return r, info

    def summary(self) -> dict:
        def lat(values: list[int]) -> dict:
            v = sorted(values)
            return {"n": len(v), "mean_ms": round(sum(v) / len(v)) if v else None,
                    "p95_ms": v[min(len(v) - 1, int(round(0.95 * (len(v) - 1))))] if v else None}
        s = {k: v for k, v in self.stats.items() if not k.endswith("_ms")}
        return s | {"naver_latency_per_line": lat(self.stats["naver_ms"]), "llm_latency_per_call": lat(self.stats["llm_ms"]),
                    "line_latency": lat(self.stats["line_ms"])}
