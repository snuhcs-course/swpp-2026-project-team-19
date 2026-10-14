# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-15, P36 prep). Reviewed by Jinwoo Park.
"""P36 prep: Naver alias candidate queue for every product of catalog_v2_service (ai/docs/p36_plan.md).

    python ai/naver/run_p36.py --stage 1            # Naver + extraction + matcher tag + rule exclusions
    python ai/naver/run_p36.py --stage 2            # judge the candidates left (until done or a quota error)
    python ai/naver/run_p36.py --stage 1 --limit 3  # first products only (check)

Stage 1 writes ai/runs/2026-10-15_p36/candidates.json; stage 2 reads it, judges with judge.py
(alias mode, judge_prompt_v1, unchanged) and writes review/p36_alias_queue.csv. The 40 P28 sample
products reuse ai/runs/2026-10-15_p28/results.json (candidates and verdicts); only their tag and
exclusions are recomputed against catalog_v2_service. Nothing is written to the catalog or the DB.

Rule exclusions (no LLM; a candidate may have several):
  other_product    the matcher (S1+S2b+S3, catalog_v2_service) puts it on another product
  bottler_missing  independent bottling, candidate without the bottler's name (candidates.bottler_missing)
  age_mismatch     the candidate has an age and it differs from the product's (or the product has none)
  existing_alias   its normalized form equals an alias the product already has
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "match_llm"))

from candidates import bottler_missing, edition_brand_aliases, extract_candidates, ko_brand_aliases  # noqa: E402
from client import ENDPOINTS, NaverSearchClient  # noqa: E402
from m3 import bottler_of  # noqa: E402
from quota import GuardedJudge, QuotaStop, check_quota_stop  # noqa: E402
from run_p28 import SeedTagger  # noqa: E402
from run_smoke import collect, latency_summary  # noqa: E402
from sample import REPO_ROOT  # noqa: E402

from app.core.normalize import normalize  # noqa: E402

SERVICE = REPO_ROOT / "ai" / "catalog" / "catalog_v2_service.json"
P28_RESULTS = REPO_ROOT / "ai" / "runs" / "2026-10-15_p28" / "results.json"
OUT = REPO_ROOT / "ai" / "runs" / "2026-10-15_p36"
QUEUE = REPO_ROOT / "review" / "p36_alias_queue.csv"
P47_BARS = {"menu:수이", "menu:오드비"}


def product_input(p: dict, brands: dict) -> dict:
    b = brands[p["brand_id"]]
    return {"key": p["key"], "display_name": p["display_name"], "brand": b["canonical_name"],
            "brand_key": b["key"], "age_years": p.get("age_years"), "edition_name": p.get("edition_name")}


def is_independent(product: dict) -> bool:
    """M3 / P17 bottler list, matched on the brand key or canonical name (match_eval.product_meta)."""
    return bool(bottler_of(product["brand_key"]) or bottler_of(product["brand"]))


def exclusions(cand: dict, product: dict, tag: dict, independent: bool, anchors: list[dict],
               own_aliases: set[str]) -> list[str]:
    out = []
    if tag["tag"] == "other_product":
        out.append("other_product")
    if bottler_missing(independent, cand["alias"], anchors):
        out.append("bottler_missing")
    if cand.get("age_years") is not None and cand["age_years"] != product["age_years"]:
        out.append("age_mismatch")
    if normalize(cand["alias"]) in own_aliases:
        out.append("existing_alias")
    return out


def stage1(args) -> None:
    service = json.loads(SERVICE.read_text(encoding="utf-8"))
    brands = {b["id"]: b for b in service["brands"]}
    p28 = {r["key"]: r for r in json.loads(P28_RESULTS.read_text(encoding="utf-8"))}
    tagger = SeedTagger(SERVICE)
    client = NaverSearchClient()
    products = service["products"][: args.limit]
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.perf_counter()
    records = []
    for n, row in enumerate(products, 1):
        product = product_input(row, brands)
        independent = is_independent(product)
        own = {normalize(a["alias_text"]) for a in row["aliases"]}
        p47_only = bool(row.get("sources")) and set(row["sources"]) <= P47_BARS
        if row["key"] in p28:
            prev = p28[row["key"]]
            anchors, cands_in, source = prev["anchors"], prev["candidates"], "p28"
            errors, total = prev.get("naver_errors", []), prev["candidate_total"]
        else:
            ko = ko_brand_aliases(product["brand"], service)
            edition = edition_brand_aliases(product, service) if independent else []
            results, errors, _ = collect(client, product, ko, edition)
            extracted = extract_candidates(product, results, ko, edition)
            anchors, cands_in, source = extracted["anchors"], extracted["candidates"], "naver"
            total = extracted["candidate_total"]
        cands = []
        for c in cands_in:
            tag = tagger.tag(c["alias"], row["key"])
            reasons = exclusions(c, product, tag, independent, anchors, own)
            cands.append({k: c[k] for k in ("alias", "normalized", "anchor", "anchor_kind", "evidence", "result_count",
                                            "age_years", "edition_tokens") if k in c}
                         | {"matcher": tag, "exclusions": reasons,
                            "llm": c.get("llm") if source == "p28" else None,
                            "llm_source": "p28" if source == "p28" and c.get("llm") else None})
        records.append({"key": row["key"], "product": product, "independent": independent, "p47_only": p47_only,
                        "source": source, "anchors": anchors, "naver_errors": errors, "candidate_total": total,
                        "candidates": cands})
        if n % 25 == 0 or n == len(products):
            print(f"[{n}/{len(products)}] naver calls {client.stats['api_calls']} cache {client.stats['cache_hits']} "
                  f"errors {client.stats['errors']}  {round(time.perf_counter() - t0)}s", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"started_at": started, "wall_s": round(time.perf_counter() - t0, 1), "products": len(records),
            "naver": {k: v for k, v in client.stats.items() if k != "latency_ms"}
            | {"latency": latency_summary(client.stats["latency_ms"])}, "endpoints": list(ENDPOINTS)}
    (OUT / "candidates.json").write_text(json.dumps({"meta": meta, "records": records}, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    print(json.dumps(summary(records) | {"naver": meta["naver"]}, ensure_ascii=False, indent=1))


def summary(records: list[dict]) -> dict:
    cands = [c for r in records for c in r["candidates"]]
    left = [c for c in cands if not c["exclusions"]]
    return {"products": len(records), "products_with_candidates": sum(bool(r["candidates"]) for r in records),
            "p47_only_products": sum(r["p47_only"] for r in records),
            "candidates": len(cands), "excluded": len(cands) - len(left), "left": len(left),
            "exclusion_reasons": dict(Counter(x for c in cands for x in c["exclusions"])),
            "tags": dict(Counter(c["matcher"]["tag"] for c in cands)),
            "llm": dict(Counter((c["llm"] or {}).get("verdict", "pending_judge") for c in left))}


def judge_input(record: dict, cand: dict) -> dict:
    p = record["product"]
    return {"mode": "alias",
            "product": {"display_name": p["display_name"], "brand": p["brand"], "age_years": p["age_years"],
                        "edition_name": p["edition_name"], "bottling": "independent" if record["independent"] else "official"},
            "alias": cand["alias"], "evidence": cand["evidence"], "matcher_tag": cand["matcher"]}


def stage2(args) -> None:
    data = json.loads((OUT / "candidates.json").read_text(encoding="utf-8"))
    records = data["records"]
    cache_path = OUT / "judge_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    stopped = None
    try:
        check_quota_stop()
    except QuotaStop as exc:
        stopped = str(exc)
    judge = GuardedJudge(budget=args.budget, task="P36")
    for r in records:
        for c in r["candidates"]:
            if c["exclusions"] or c["llm"]:
                continue
            ckey = f"{r['key']}\t{c['alias']}"
            if ckey in cache:
                c["llm"], c["llm_source"] = cache[ckey], "p36"
                continue
            if stopped:
                continue
            try:
                c["llm"], c["llm_source"] = judge(judge_input(r, c)), "p36"
                cache[ckey] = c["llm"]
                cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
            except QuotaStop as exc:
                stopped = str(exc)
                print(f"QUOTA STOP: {stopped}", flush=True)
            except Exception as exc:  # BudgetExceeded and other errors: stop judging, keep the rest pending
                stopped = f"{type(exc).__name__}: {str(exc)[:200]}"
                print(f"STOP: {stopped}", flush=True)
    data["meta"]["stage2"] = {"judge": {k: v for k, v in judge.stats.items() if k != "latency_ms"}
                              | {"latency": latency_summary(judge.stats["latency_ms"])},
                              "prompt_sha256": judge.prompt_sha256, "stopped": stopped,
                              "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (OUT / "candidates.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    write_queue(records, QUEUE)
    print(json.dumps(summary(records) | {"stage2": data["meta"]["stage2"]}, ensure_ascii=False, indent=1))


def write_queue(records: list[dict], path: Path) -> None:
    cols = ["product_key", "product", "independent", "p47_only", "candidate", "source", "evidence", "matcher_tag",
            "exclusion", "llm_verdict", "llm_confidence", "llm_reason", "human_decision"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in records:
            for c in r["candidates"]:
                ev = c["evidence"][:3]
                llm = c["llm"] or {}
                tag = c["matcher"]
                names = ", ".join(p["display_name"] or p["key"] or "?" for p in tag["products"][:3])
                w.writerow({
                    "product_key": r["key"], "product": r["product"]["display_name"],
                    "independent": "yes" if r["independent"] else "", "p47_only": "yes" if r["p47_only"] else "",
                    "candidate": c["alias"],
                    "source": " ".join(sorted({f"naver:{e['endpoint']}" for e in c["evidence"]})),
                    "evidence": "\n".join(f"[{j}] {e['title']} | {e['url']}" for j, e in enumerate(ev, 1)),
                    "matcher_tag": tag["tag"] + (f" ({names})" if names else ""),
                    "exclusion": ", ".join(c["exclusions"]),
                    "llm_verdict": llm.get("verdict") or ("" if c["exclusions"] else "pending_judge"),
                    "llm_confidence": llm.get("confidence", ""), "llm_reason": llm.get("reason", ""),
                    "human_decision": "",
                })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", type=int, choices=[1, 2], required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--budget", type=int, default=1500, help="stage 2 Gemini calls (retries count)")
    args = parser.parse_args()
    stage1(args) if args.stage == 1 else stage2(args)


if __name__ == "__main__":
    main()
