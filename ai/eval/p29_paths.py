# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-15, P29 prep). Reviewed by Jinwoo Park.
"""P29 prep: precision and line counts per matching path on dev, and owner-burden simulations of
grading policies (ai/docs/p29_proposal.md). Caches only: M3a translations, M4 verdicts, Naver.

    python ai/eval/p29_paths.py --json ai/runs/2026-10-15_p29/dev_paths.json

Pipelines (C0 and C1 of match_eval.py, dev, gold match_gold_v1_1):
  full  S1+S2b+S3 -> M3a -> M4   (M4 adds nothing on dev; see ai/runs/2026-10-15_m4)
  m4    S1+S2b+S3 -> M4          (the M4 reference row; gives the M4 path its lines)
Path of a line = what produced its rank-1 result (read from status, score, evidence; no gold):
  alias_exact    exact, alias score 1.0 (normalize + alias, S1 variants)   multi  S1 two products
  s2_exact       exact, brand + age/edition (S2, S2b default product)       s3_exact  exact edit distance
  s2b_confirm    S2b one candidate, confirm recommended                    s3_confirm  S3 one candidate
  m3a_confirm / m4_confirm   LLM candidate with confirm recommended
  llm_top        LLM candidate first, not confirm recommended              choose  several rule candidates
  single         one rule candidate, no confirm flag                        register  no candidate
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from match_eval import (CONFIRMED, M3_BASE, MATCHERS, REPO_ROOT, gold_refs, judge, load_catalog,  # noqa: E402
                        make_m3, make_m4, split_new_products)
from app.matching.types import ExtractedProduct  # noqa: E402

GOLD = REPO_ROOT / "eval" / "match_gold_v1_1.json"
M3_CACHE = REPO_ROOT / "ai" / "runs" / "2026-10-14_m3" / "cache"
M4_CACHE = REPO_ROOT / "ai" / "runs" / "2026-10-15_m4" / "judge_cache"
PATHS = ("alias_exact", "multi", "s2_exact", "s3_exact", "s2b_confirm", "s3_confirm", "m3a_confirm", "m4_confirm",
         "llm_top", "single", "choose", "register")
LIMIT = 5

# Grade per path: A auto-confirmed (owner does nothing), B confirm (one tap on one suggestion),
# C choose among candidates, D register / link by hand. Policies are proposals, not decisions.
POLICIES = {
    "P1 LLM 확인 = B": {"alias_exact": "A", "multi": "A", "s2_exact": "A", "s3_exact": "A",
                 "s2b_confirm": "B", "s3_confirm": "B", "m3a_confirm": "B", "m4_confirm": "B"},
    "P2 LLM 확인 자동 수락": {"alias_exact": "A", "multi": "A", "s2_exact": "A", "s3_exact": "A",
                       "s2b_confirm": "B", "s3_confirm": "B", "m3a_confirm": "A", "m4_confirm": "A"},
    "P3 별칭만 자동": {"alias_exact": "A", "multi": "A", "s2_exact": "B", "s3_exact": "B",
                  "s2b_confirm": "B", "s3_confirm": "B", "m3a_confirm": "C", "m4_confirm": "C"},
}
DEFAULT_GRADE = {"llm_top": "C", "single": "C", "choose": "C", "register": "D"}


def path_of(r) -> str:
    if r.status == "multi":
        return "multi"
    if r.status == "unmatched" or not r.candidates:
        return "register"
    top = r.candidates[0]
    if r.status == "exact_match":
        return {1.0: "alias_exact", 0.8: "s2_exact", 0.6: "s3_exact"}.get(round(top.score, 2), "alias_exact")
    confirm = bool(top.evidence.get("confirmRecommended"))
    if top.method == "llm":
        stage = top.evidence.get("m3")
        if confirm:
            return "m4_confirm" if stage == "M4" else "m3a_confirm"
        return "llm_top"
    if confirm:
        return "s3_confirm" if round(top.score, 2) == 0.6 else "s2b_confirm"
    return "single" if len(r.candidates) == 1 else "choose"


def run(pipeline: str, condition: str, gold: dict, m3, m4) -> list[dict]:
    base_resolve = MATCHERS[M3_BASE]
    in_split = split_new_products(gold, "dev")
    catalogs, rows = {}, []
    for photo in gold["photos"]:
        if photo["split"] != "dev":
            continue
        bar = photo["bar"]
        if bar not in catalogs:
            catalogs[bar] = load_catalog(bar, condition, gold["new_products"], in_split)
        catalog, key_to_id = catalogs[bar]

        def in_catalog(g: str) -> bool:
            return not g.startswith("new:") or condition == "C1"

        seen = {}
        for item in photo["items"]:
            seen.setdefault(item["raw_name"], item["gold"])
        for name, g in seen.items():
            base = r = base_resolve(ExtractedProduct(product_name=name), catalog)
            info4 = None
            if r.status not in CONFIRMED:
                if pipeline == "full":
                    r, _ = m3.resolve(photo["photo_id"], name, catalog, r, "merge", False)
                r, info4 = m4.resolve(photo["photo_id"], name, catalog, r)
            outcome = judge(g, r, key_to_id, in_catalog)
            gold_ids = {key_to_id[x] for x in gold_refs(g) if x in key_to_id and in_catalog(x)}
            rank1_gold = bool(r.candidates) and r.candidates[0].product_id in gold_ids
            kind = ("non_whisky" if g == "non_whisky" else "unknown" if g == "unknown"
                    else "known" if all(in_catalog(x) for x in gold_refs(g)) else "absent")
            path = path_of(r)
            if (path in ("m3a_confirm", "m4_confirm") and path_of(base) in ("s2b_confirm", "s3_confirm")
                    and base.candidates[0].product_id == r.candidates[0].product_id):
                path = path_of(base)  # the LLM agreed with a rule's confirm: credited to the rule (M3 README)
            if path in ("alias_exact", "s2_exact", "s3_exact", "multi"):
                correct = outcome in ("correct", "partial")  # partial: one of a both: line's two products
            elif path == "register":
                correct = kind in ("absent", "non_whisky", "unknown")  # nothing to pick is right
            else:
                correct = rank1_gold
            rows.append({"photo_id": photo["photo_id"], "name": name, "gold": g, "kind": kind, "path": path,
                         "correct": correct, "gold_in_candidates": bool(gold_ids & {c.product_id for c in r.candidates}),
                         "outcome": outcome,
                         "m4": {k: info4.get(k) for k in ("m4", "confidence", "picked")} if isinstance(info4, dict)
                         and "confidence" in info4 else None})
    return rows


def path_table(rows: list[dict]) -> dict:
    out = {}
    for p in PATHS:
        sel = [r for r in rows if r["path"] == p]
        if sel:
            out[p] = {"lines": len(sel), "correct": sum(r["correct"] for r in sel),
                      "precision": round(sum(r["correct"] for r in sel) / len(sel), 3),
                      "gold_in_candidates": sum(r["gold_in_candidates"] for r in sel)}
    return out


def simulate(rows: list[dict], grades: dict, photos: list[str]) -> dict:
    per_photo = {pid: Counter() for pid in photos}  # photos without whisky lines count with 0
    wrong = Counter()
    for r in rows:
        g = grades.get(r["path"], DEFAULT_GRADE.get(r["path"], "C"))
        per_photo[r["photo_id"]][g] += 1
        if g in ("A", "B") and not r["correct"]:
            wrong[g] += 1
    owner = [c["C"] + c["D"] for c in per_photo.values()]
    owner_b = [c["B"] + c["C"] + c["D"] for c in per_photo.values()]
    totals = Counter()
    for c in per_photo.values():
        totals.update(c)
    return {"grades": {g: totals[g] for g in "ABCD"},
            "choose_register_per_photo_mean": round(statistics.mean(owner), 2), "choose_register_max": max(owner),
            "photos_choose_register_under_5": f"{sum(o < LIMIT for o in owner)}/{len(owner)}",
            "with_confirm_per_photo_mean": round(statistics.mean(owner_b), 2),
            "photos_with_confirm_under_5": f"{sum(o < LIMIT for o in owner_b)}/{len(owner_b)}",
            "wrong_auto_A": wrong["A"], "wrong_suggested_B": wrong["B"]}


def confidence_table(rows: list[dict]) -> list[dict]:
    """M4 judge confidence vs correctness of its verdict (same: picked is gold; new/none: gold not in catalog)."""
    bins = ((0.0, 0.8), (0.8, 0.9), (0.9, 0.95), (0.95, 1.0001))
    calls = [r for r in rows if r["m4"] and r["m4"]["m4"] in ("same", "different", "vetoed")]
    out = []
    for lo, hi in bins:
        sel = [r for r in calls if lo <= (r["m4"]["confidence"] or 0) < hi]
        ok = [r for r in sel if (r["m4"]["m4"] == "same" and r["correct"]) or
              (r["m4"]["m4"] == "different" and r["kind"] in ("absent", "unknown", "non_whisky"))]
        out.append({"bin": f"[{lo}, {min(hi, 1.0)}" + ("]" if hi > 1 else ")"), "verdicts": len(sel),
                    "correct": len(ok), "accuracy": round(len(ok) / len(sel), 3) if sel else None})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    from llm import CachedLLM
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    m3 = make_m3(CachedLLM(M3_CACHE, cache_only=True), GOLD, "dev")
    m4 = make_m4(m3, M4_CACHE, None, budget=0)  # verdicts from the cache only; a miss stops the run
    result = {}
    for pipeline in ("full", "m4"):
        for condition in ("C0", "C1"):
            rows = run(pipeline, condition, gold, m3, m4)
            photos = [p["photo_id"] for p in gold["photos"] if p["split"] == "dev"]
            result[f"{pipeline}/{condition}"] = {
                "lines": len(rows), "paths": path_table(rows),
                "policies": {name: simulate(rows, grades, photos) for name, grades in POLICIES.items()},
                "m4_confidence": confidence_table(rows), "rows": rows}
    for key, r in result.items():
        print(f"== {key} ({r['lines']} lines)")
        for p, t in r["paths"].items():
            print(f"  {p:12} {t['lines']:4} correct {t['correct']:4}  precision {t['precision']:.3f}")
        for name, s in r["policies"].items():
            print(f"  {name}: {s}")
        print(f"  M4 confidence: {r['m4_confidence']}")
    print(f"M4 judge calls (must be 0): {m4.judge.stats['llm_calls']}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
