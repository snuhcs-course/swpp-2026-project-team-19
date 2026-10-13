# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P17). Reviewed by Jinwoo Park.
"""P17 smoke run: Naver candidates -> matcher tag -> LLM judge (naver_plan.md, 5절).

    python ai/naver/run_smoke.py                 # 10 products, writes ai/runs/<date>_naver_smoke/
    python ai/naver/run_smoke.py --limit 1       # first product only (check before the full run)
    python ai/naver/run_smoke.py --no-judge      # Naver + matcher only

Smoke products: new products of match_gold_v1 outside the P28 sample (naver_sample_v1),
5 independent bottlings + 5 distillery releases, drawn with seed 20261014. The P28 sample
is only used to exclude its keys; its contents are not printed or written.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from candidates import (brand_age_query, build_queries, edition_brand_aliases, extract_candidates,  # noqa: E402
                        ko_brand_aliases, learn_brand_aliases, clean_text)
from client import ENDPOINTS, NaverSearchClient, NaverSearchError  # noqa: E402
from sample import REPO_ROOT, is_independent, strata  # noqa: E402
from tagger import MatcherTagger  # noqa: E402

GOLD = REPO_ROOT / "eval" / "match_gold_v1.json"
SAMPLE = REPO_ROOT / "eval" / "naver_sample_v1.json"
SEED_CATALOG = REPO_ROOT / "ai" / "catalog" / "catalog_v1_draft.json"
SMOKE_SEED = 20261014
SMOKE_PER_STRATUM = 5
DISPLAY = 10


def smoke_products(gold: dict) -> list[str]:
    excluded = {k for keys in json.loads(SAMPLE.read_text(encoding="utf-8"))["sample"].values() for k in keys}
    rng = random.Random(SMOKE_SEED)
    out = []
    for name, keys in strata(gold).items():
        pool = [k for k in keys if k not in excluded]
        out += sorted(rng.sample(pool, SMOKE_PER_STRATUM))
    assert not set(out) & excluded
    return out


def collect(client: NaverSearchClient, product: dict, ko_brands: list[str],
            edition_brands: list[str]) -> tuple[list[dict], list[str], dict]:
    """Search every query on every endpoint. Without a catalog Korean brand, the brand learned
    from the first results is used for the "<Korean brand> <age>년" query."""
    results, errors = [], []
    queries = build_queries(product, ko_brands, edition_brands)
    done: list[str] = []

    def run(query: str) -> None:
        for endpoint in ENDPOINTS:
            try:
                results.append(client.search(endpoint, query, display=DISPLAY))
            except NaverSearchError as exc:
                errors.append(str(exc))
        done.append(query)

    for q in queries:
        run(q)
    learned = []
    if not ko_brands:
        texts = [clean_text(it.get("title", "")) + " | " + clean_text(it.get("description", ""))
                 for r in results for it in r["items"]]
        learned = learn_brand_aliases(product["brand"], texts)
        q = brand_age_query(product, learned[0], edition_brands) if learned else None
        if q and q not in done:
            run(q)
    return results, errors, {"queries": done,
                             "learned_brand_for_query": learned[0] if learned and product.get("age_years") else None}


def bottler_missing(product: dict, cand: dict) -> bool:
    """Rule flag (P18 c): an independent bottling's candidate that starts at the distillery,
    i.e. without the bottler's name. Recorded next to the LLM verdict, never overriding it."""
    return is_independent(product) and cand["anchor_kind"] == "edition_brand"


def judge_input(product: dict, cand: dict, tag: dict) -> dict:
    return {"mode": "alias",
            "product": {**{k: product[k] for k in ("display_name", "brand", "age_years", "edition_name")},
                        "bottling": "independent" if is_independent(product) else "official"},
            "alias": cand["alias"], "evidence": cand["evidence"], "matcher_tag": tag}


def is_disagreement(tag: str, verdict: str) -> bool:
    """Matcher and LLM point different ways (naver_plan.md, 5절)."""
    return ((tag == "same" and verdict != "same") or (tag == "other_product" and verdict == "same"))


def pct(values: list[int], q: float):
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def latency_summary(values: list[int]) -> dict:
    return {"n": len(values), "mean_ms": round(statistics.mean(values)) if values else None,
            "p50_ms": pct(values, 0.5), "p95_ms": pct(values, 0.95), "max_ms": max(values) if values else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="first N smoke products only")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--budget", type=int, default=120, help="max LLM calls in this run")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "ai" / "runs" / f"{date.today().isoformat()}_naver_smoke")
    args = parser.parse_args()

    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    seed = json.loads(SEED_CATALOG.read_text(encoding="utf-8"))
    keys = smoke_products(gold)[: args.limit]
    client = NaverSearchClient()
    tagger = MatcherTagger(gold)
    judge = None
    if not args.no_judge:
        from judge import Judge
        judge = Judge(budget=args.budget)

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.perf_counter()
    records = []
    for key in keys:
        product = gold["new_products"][key]
        ko_brands = ko_brand_aliases(product["brand"], seed)
        edition_brands = edition_brand_aliases(product, seed) if is_independent(product) else []
        results, errors, qinfo = collect(client, product, ko_brands, edition_brands)
        extracted = extract_candidates(product, results, ko_brands, edition_brands)
        cands = []
        for cand in extracted["candidates"]:
            tag = tagger.tag(cand["alias"], key)
            verdict = judge(judge_input(product, cand, tag)) if judge else None
            cands.append({**cand, "bottler_missing": bottler_missing(product, cand), "matcher": tag, "llm": verdict})
            v = verdict["verdict"] if verdict else "-"
            print(f"  {key[:34]:34} {cand['alias'][:28]:28} tag={tag['tag']:13} llm={v}", flush=True)
        records.append({
            "key": key, "stratum": "independent" if is_independent(product) else "official", "product": product,
            "ko_brand_aliases": ko_brands, "edition_brand_aliases": edition_brands, **qinfo,
            "endpoint_results": {ep: sum(len(r["items"]) for r in results if r["endpoint"] == ep) for ep in ENDPOINTS},
            "endpoint_total_hits": {ep: sum(r["total"] or 0 for r in results if r["endpoint"] == ep) for ep in ENDPOINTS},
            "naver_errors": errors, "anchors": extracted["anchors"],
            "candidate_total": extracted["candidate_total"], "candidates": cands,
        })
    wall_s = round(time.perf_counter() - t0, 1)

    all_cands = [c for r in records for c in r["candidates"]]
    tags = Counter(c["matcher"]["tag"] for c in all_cands)
    verdicts = Counter(c["llm"]["verdict"] for c in all_cands if c["llm"])
    cross = Counter(f"{c['matcher']['tag']} / {c['llm']['verdict']}" for c in all_cands if c["llm"])
    disagreements = [{"key": r["key"], "stratum": r["stratum"], "product": r["product"]["display_name"],
                      "alias": c["alias"], "tag": c["matcher"]["tag"],
                      "matcher_products": [p["display_name"] for p in c["matcher"]["products"]],
                      "llm": c["llm"]["verdict"], "confidence": c["llm"]["confidence"], "reason": c["llm"]["reason"]}
                     for r in records for c in r["candidates"]
                     if c["llm"] and is_disagreement(c["matcher"]["tag"], c["llm"]["verdict"])]
    summary = {
        "run": {"started_at": started, "wall_s": wall_s, "products": len(records), "smoke_seed": SMOKE_SEED,
                "display": DISPLAY, "endpoints": list(ENDPOINTS), "matcher": tagger_matcher(),
                "judge": None if judge is None else {"model": "gemini-3.5-flash-lite", "thinking_level": judge_meta("THINKING_LEVEL"),
                                                     "prompt_version": judge_meta("PROMPT_VERSION"), "prompt_sha256": judge.prompt_sha256}},
        "endpoint_results": {ep: sum(r["endpoint_results"][ep] for r in records) for ep in ENDPOINTS},
        "endpoint_results_with_candidate": dict(Counter(e["endpoint"] for c in all_cands for e in c["evidence"])),
        "korean_candidates_per_product": {r["key"]: {"found": r["candidate_total"], "kept": len(r["candidates"])} for r in records},
        "matcher_tags": dict(tags),
        "llm_verdicts": dict(verdicts),
        "tag_x_verdict": dict(cross),
        "disagreements": disagreements,
        "naver": {k: v for k, v in client.stats.items() if k != "latency_ms"} | {"latency": latency_summary(client.stats["latency_ms"])},
        "llm": None if judge is None else ({k: v for k, v in judge.stats.items() if k != "latency_ms"}
                                           | {"latency": latency_summary(judge.stats["latency_ms"])}),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("endpoint_results", "matcher_tags", "llm_verdicts", "tag_x_verdict",
                                              "naver", "llm")}, ensure_ascii=False, indent=1))
    print(f"disagreements: {len(disagreements)}  wall {wall_s}s  -> {args.out}")


def tagger_matcher() -> str:
    from tagger import MATCHER
    return MATCHER


def judge_meta(name: str):
    import judge as judge_module
    return getattr(judge_module, name)


if __name__ == "__main__":
    main()
