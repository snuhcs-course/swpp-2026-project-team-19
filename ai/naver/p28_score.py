# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-15, P28). Reviewed by Jinwoo Park.
"""P28 precision from the human review sheet (ai/docs/p28_plan.md, 3절).

    python ai/naver/p28_score.py                          # review/p28_review.csv
    python ai/naver/p28_score.py --csv other.csv --json out.json

Fill `human_verdict` (same / different / unsure) first. Rows left empty are skipped and counted.
Metrics: M1 LLM-same precision (human unsure counts as wrong), M1b (unsure excluded),
M2 one-sided Clopper-Pearson 95% upper bound of the false-merge rate, M3 per-confidence-bin
error rates, M4 by stratum, M5 product-level recall, M6 matcher tag x human, M7 bottler_missing.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = REPO_ROOT / "review" / "p28_review.csv"
VERDICTS = ("same", "different", "unsure")
BINS = ((0.0, 0.5), (0.5, 0.8), (0.8, 0.9), (0.9, 0.95), (0.95, 1.0001))


def binom_cdf(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def cp_upper(k: int, n: int, alpha: float = 0.05) -> float | None:
    """One-sided Clopper-Pearson upper bound: the p with P(X <= k | n, p) = alpha."""
    if n == 0:
        return None
    if k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if binom_cdf(k, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def tag_name(cell: str) -> str:
    return cell.split(" ", 1)[0] if cell else ""


def load_rows(path: Path) -> tuple[list[dict], dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    bad = [r["row_id"] for r in rows if r["human_verdict"].strip() and r["human_verdict"].strip() not in VERDICTS]
    if bad:
        raise SystemExit(f"human_verdict must be one of {VERDICTS}: {bad[:10]}")
    info = {"rows": len(rows), "human_filled": sum(bool(r["human_verdict"].strip()) for r in rows),
            "llm_pending": sum(r["llm_verdict"] not in VERDICTS for r in rows)}
    info["human_empty"] = info["rows"] - info["human_filled"]
    for r in rows:
        r["human_verdict"] = r["human_verdict"].strip()
        r["conf"] = float(r["llm_confidence"]) if r["llm_confidence"] else None
    return [r for r in rows if r["human_verdict"] and r["llm_verdict"] in VERDICTS], info


def precision_block(rows: list[dict]) -> dict:
    llm_same = [r for r in rows if r["llm_verdict"] == "same"]
    n = len(llm_same)
    correct = sum(r["human_verdict"] == "same" for r in llm_same)
    wrong = n - correct
    decided = [r for r in llm_same if r["human_verdict"] != "unsure"]
    upper = cp_upper(wrong, n)
    return {
        "rows": len(rows), "llm_same": n,
        "M1_precision": ratio(correct, n), "llm_same_correct": correct, "llm_same_wrong": wrong,
        "llm_same_human_different": sum(r["human_verdict"] == "different" for r in llm_same),
        "llm_same_human_unsure": sum(r["human_verdict"] == "unsure" for r in llm_same),
        "M1b_precision_excl_unsure": ratio(correct, len(decided)),
        "M2_false_merge_upper95": round(upper, 4) if upper is not None else None,
        "llm_vs_human_agreement": ratio(sum(r["llm_verdict"] == r["human_verdict"] for r in rows), len(rows)),
        "human_same_recall": ratio(sum(r["llm_verdict"] == "same" and r["human_verdict"] == "same" for r in rows),
                                   sum(r["human_verdict"] == "same" for r in rows)),
    }


def bin_label(lo: float, hi: float) -> str:
    return f"[{lo}, {min(hi, 1.0)}" + ("]" if hi > 1 else ")")


def confidence_bins(rows: list[dict]) -> list[dict]:
    out = []
    for lo, hi in BINS:
        inside = [r for r in rows if r["conf"] is not None and lo <= r["conf"] < hi]
        same = [r for r in inside if r["llm_verdict"] == "same"]
        out.append({"bin": bin_label(lo, hi), "rows": len(inside),
                    "llm_vs_human_mismatch": ratio(sum(r["llm_verdict"] != r["human_verdict"] for r in inside), len(inside)),
                    "llm_same": len(same),
                    "llm_same_error_rate": ratio(sum(r["human_verdict"] != "same" for r in same), len(same))})
    return out


def product_recall(rows: list[dict]) -> dict:
    by_product = defaultdict(list)
    for r in rows:
        by_product[r["product_key"]].append(r)
    with_human_same = [k for k, rs in by_product.items() if any(r["human_verdict"] == "same" for r in rs)]
    found = [k for k in with_human_same
             if any(r["llm_verdict"] == "same" and r["human_verdict"] == "same" for r in by_product[k])]
    return {"products_reviewed": len(by_product), "products_with_human_same": len(with_human_same),
            "products_with_correct_llm_same": len(found), "M5_recall": ratio(len(found), len(with_human_same))}


def tag_table(rows: list[dict], col: str) -> dict:
    table = defaultdict(Counter)
    for r in rows:
        table[tag_name(r[col])][r["human_verdict"]] += 1
    return {t: dict(c) for t, c in sorted(table.items())}


def decision(overall: dict, independent: dict) -> str:
    """ai/docs/p28_plan.md 4절."""
    m1 = overall["M1_precision"]
    if m1 is None:
        return "판정 불가 (LLM same 없음)"
    if m1 >= 0.9 and independent["llm_same_human_different"] == 0:
        return "통과"
    if m1 >= 0.8:
        return "보류"
    return "불통과"


def score(rows: list[dict], info: dict) -> dict:
    strata = {s: precision_block([r for r in rows if r["stratum"] == s]) for s in ("independent", "official")}
    overall = precision_block(rows)
    bm = [r for r in rows if r["bottler_missing"] == "yes"]
    return {
        "input": info,
        "overall": overall,
        "M3_confidence_bins": confidence_bins(rows),
        "M4_by_stratum": strata,
        "M5_product_recall": product_recall(rows),
        "M6_tag_v1_x_human": tag_table(rows, "tag_v1"),
        "M6_tag_v2_x_human": tag_table(rows, "tag_v2"),
        "M7_bottler_missing": {"rows": len(bm), "human_same": sum(r["human_verdict"] == "same" for r in bm),
                               "llm_same": sum(r["llm_verdict"] == "same" for r in bm)},
        "decision": decision(overall, strata["independent"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--json", type=Path, help="also write the result here")
    args = parser.parse_args()
    rows, info = load_rows(args.csv)
    result = score(rows, info)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    print(text)
    if info["human_empty"]:
        print(f"note: {info['human_empty']} rows without human_verdict were skipped")
    if args.json:
        args.json.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
