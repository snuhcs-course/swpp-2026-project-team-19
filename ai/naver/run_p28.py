# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-15, P28). Reviewed by Jinwoo Park.
"""P28: Naver candidates -> matcher tags (v1, v2 reference) -> LLM judge on the 40-product sample.

    python ai/naver/run_p28.py --limit 1      # first product only (check before the full run)
    python ai/naver/run_p28.py                # all 40, writes ai/runs/2026-10-15_p28/ and review/p28_review.csv

Collection, extraction, the v1 matcher tag and the judge are the a22bfee code of run_smoke.py,
unchanged (ai/docs/p28_plan.md). The only additions: the v2 tag column (catalog_v2_draft, not
shown to the LLM), a verdict cache for resuming, and the quota stop (quota.py).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from candidates import bottler_missing, edition_brand_aliases, extract_candidates, ko_brand_aliases  # noqa: E402
from client import ENDPOINTS, NaverSearchClient  # noqa: E402
from quota import GuardedJudge, QuotaStop  # noqa: E402
from run_smoke import DISPLAY, GOLD, SAMPLE, SEED_CATALOG, collect, judge_input, latency_summary  # noqa: E402
from sample import REPO_ROOT, is_independent  # noqa: E402
from tagger import MATCHER, STAGES, MatcherTagger  # noqa: E402

from app.matching.memory_catalog import InMemoryCatalog  # noqa: E402
from app.matching.types import ProductInfo  # noqa: E402

V2_CATALOG = REPO_ROOT / "ai" / "catalog" / "catalog_v2_draft.json"
OUT = REPO_ROOT / "ai" / "runs" / "2026-10-15_p28"
REVIEW = REPO_ROOT / "review" / "p28_review.csv"
MAX_EVIDENCE_IN_SHEET = 4  # the judge sees at most 4 (judge.MAX_EVIDENCE)


def load_seed_catalog(path: Path) -> tuple[InMemoryCatalog, dict[str, uuid.UUID]]:
    """Every product and alias of a seed-format catalog (no menu aliases excluded)."""
    seed = json.loads(path.read_text(encoding="utf-8"))
    products = [ProductInfo(uuid.UUID(p["id"]), p["display_name"], p.get("age_years"), p.get("edition_name"),
                            uuid.UUID(p["brand_id"])) for p in seed["products"]]
    aliases = [(uuid.UUID(p["id"]), a["alias_text"]) for p in seed["products"] for a in p["aliases"]]
    brand_aliases = [(uuid.UUID(b["id"]), a["alias_text"]) for b in seed["brands"] for a in b["aliases"]]
    return InMemoryCatalog(products, aliases, brand_aliases), {p["key"]: uuid.UUID(p["id"]) for p in seed["products"]}


class SeedTagger(MatcherTagger):
    """MatcherTagger.tag on another catalog; the input key is a product key of that catalog."""

    def __init__(self, path: Path):
        self.catalog, self.key_to_id = load_seed_catalog(path)
        self.id_to_key = {v: k for k, v in self.key_to_id.items()}

    def product_id(self, key: str) -> uuid.UUID:
        return self.key_to_id[key.removeprefix("new:")]


def sample_keys() -> list[tuple[str, str]]:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))["sample"]
    return [(stratum, key) for stratum in ("independent", "official") for key in sample[stratum]]


def short_tag(tag: dict) -> str:
    names = ", ".join(p["display_name"] or p["key"] or "?" for p in tag["products"][:3])
    return f"{tag['tag']}" + (f" ({names})" if names else "")


def write_review(records: list[dict], path: Path) -> None:
    cols = ["row_id", "stratum", "product_key", "product", "candidate", "tag_v1", "tag_v2", "bottler_missing",
            "evidence_titles", "evidence_snippets", "evidence_urls", "llm_verdict", "llm_confidence", "llm_reason",
            "human_verdict", "note"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in records:
            for i, c in enumerate(r["candidates"], 1):
                ev = c["evidence"][:MAX_EVIDENCE_IN_SHEET]
                llm = c["llm"] or {}
                w.writerow({
                    "row_id": f"{r['key']}#{i}", "stratum": r["stratum"], "product_key": r["key"],
                    "product": r["product"]["display_name"], "candidate": c["alias"],
                    "tag_v1": short_tag(c["matcher"]), "tag_v2": short_tag(c["matcher_v2"]),
                    "bottler_missing": "yes" if c["bottler_missing"] else "",
                    "evidence_titles": "\n".join(f"[{j}] {e['title']}" for j, e in enumerate(ev, 1)),
                    "evidence_snippets": "\n".join(f"[{j}] {e['snippet']}" for j, e in enumerate(ev, 1)),
                    "evidence_urls": "\n".join(f"[{j}] {e['url']}" for j, e in enumerate(ev, 1)),
                    "llm_verdict": llm.get("verdict", "pending"), "llm_confidence": llm.get("confidence", ""),
                    "llm_reason": llm.get("reason", ""), "human_verdict": "", "note": "",
                })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="first N sample products only")
    parser.add_argument("--budget", type=int, default=220, help="max LLM calls in this run")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--review", type=Path, default=REVIEW)
    args = parser.parse_args()

    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    seed = json.loads(SEED_CATALOG.read_text(encoding="utf-8"))
    keys = sample_keys()[: args.limit]
    client = NaverSearchClient()
    tagger = MatcherTagger(gold)
    tagger_v2 = SeedTagger(V2_CATALOG)
    judge = GuardedJudge(budget=args.budget, task="P28")
    args.out.mkdir(parents=True, exist_ok=True)
    cache_path = args.out / "judge_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    stopped = None

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.perf_counter()
    records = []
    for stratum, key in keys:
        product = gold["new_products"][key]
        ko_brands = ko_brand_aliases(product["brand"], seed)
        edition_brands = edition_brand_aliases(product, seed) if is_independent(product) else []
        results, errors, qinfo = collect(client, product, ko_brands, edition_brands)
        extracted = extract_candidates(product, results, ko_brands, edition_brands)
        cands = []
        for cand in extracted["candidates"]:
            tag = tagger.tag(cand["alias"], key)
            tag_v2 = tagger_v2.tag(cand["alias"], key)
            ckey = f"{key}\t{cand['alias']}"
            verdict = cache.get(ckey)
            if verdict is None and stopped is None:
                try:
                    verdict = judge(judge_input(product, cand, tag))
                    cache[ckey] = verdict
                    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
                except QuotaStop as exc:
                    stopped = str(exc)
                    print(f"QUOTA STOP: {stopped}", flush=True)
            cands.append({**cand, "bottler_missing": bottler_missing(is_independent(product), cand["alias"], extracted["anchors"]),
                          "matcher": tag, "matcher_v2": tag_v2, "llm": verdict})
            v = verdict["verdict"] if verdict else "pending"
            print(f"  {key[:34]:34} {cand['alias'][:28]:28} v1={tag['tag']:13} v2={tag_v2['tag']:13} llm={v}", flush=True)
        records.append({
            "key": key, "stratum": stratum, "product": product,
            "ko_brand_aliases": ko_brands, "edition_brand_aliases": edition_brands, **qinfo,
            "endpoint_results": {ep: sum(len(r["items"]) for r in results if r["endpoint"] == ep) for ep in ENDPOINTS},
            "naver_errors": errors, "anchors": extracted["anchors"],
            "candidate_total": extracted["candidate_total"], "candidates": cands,
        })
    wall_s = round(time.perf_counter() - t0, 1)

    all_cands = [c for r in records for c in r["candidates"]]
    judged = [c for c in all_cands if c["llm"]]
    by_stratum = {s: {"products": sum(r["stratum"] == s for r in records),
                      "products_with_candidates": sum(r["stratum"] == s and bool(r["candidates"]) for r in records),
                      "candidates": sum(len(r["candidates"]) for r in records if r["stratum"] == s),
                      "llm_verdicts": dict(Counter(c["llm"]["verdict"] for r in records if r["stratum"] == s
                                                   for c in r["candidates"] if c["llm"]))}
                  for s in ("independent", "official")}
    summary = {
        "run": {"started_at": started, "wall_s": wall_s, "products": len(records), "display": DISPLAY,
                "endpoints": list(ENDPOINTS), "matcher": MATCHER, "matcher_stages": sorted(STAGES),
                "tag_v1_catalog": "catalog_v1_draft + match_gold_v1 new products (C1)",
                "tag_v2_catalog": "catalog_v2_draft (origin/i2-catalog-v2 415e78f), reference only",
                "judge": {"model": "gemini-3.5-flash-lite", "thinking_level": "low", "prompt_version": "v1",
                          "prompt_sha256": judge.prompt_sha256},
                "quota_stop": stopped},
        "candidates": len(all_cands), "judged": len(judged), "pending_judge": len(all_cands) - len(judged),
        "by_stratum": by_stratum,
        "tags_v1": dict(Counter(c["matcher"]["tag"] for c in all_cands)),
        "tags_v2": dict(Counter(c["matcher_v2"]["tag"] for c in all_cands)),
        "llm_verdicts": dict(Counter(c["llm"]["verdict"] for c in judged)),
        "tag_v1_x_verdict": dict(Counter(f"{c['matcher']['tag']} / {c['llm']['verdict']}" for c in judged)),
        "tag_v2_x_verdict": dict(Counter(f"{c['matcher_v2']['tag']} / {c['llm']['verdict']}" for c in judged)),
        "bottler_missing_x_verdict": dict(Counter(c["llm"]["verdict"] for c in judged if c["bottler_missing"])),
        "endpoint_results_with_candidate": dict(Counter(e["endpoint"] for c in all_cands for e in c["evidence"])),
        "naver": {k: v for k, v in client.stats.items() if k != "latency_ms"} | {"latency": latency_summary(client.stats["latency_ms"])},
        "llm": {k: v for k, v in judge.stats.items() if k != "latency_ms"} | {"latency": latency_summary(judge.stats["latency_ms"]),
                                                                              "cached_verdicts_reused": len(judged) - len(judge.stats["latency_ms"])},
    }
    (args.out / "results.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    write_review(records, args.review)
    print(json.dumps({k: summary[k] for k in ("candidates", "judged", "by_stratum", "tags_v1", "tags_v2", "llm_verdicts",
                                              "naver", "llm")}, ensure_ascii=False, indent=1))
    print(f"wall {wall_s}s -> {args.out}, {args.review}" + (f"  QUOTA STOP: {stopped}" if stopped else ""))


if __name__ == "__main__":
    main()
