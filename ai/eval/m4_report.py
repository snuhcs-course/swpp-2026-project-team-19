# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-15, M4). Reviewed by Jinwoo Park.
"""M4 metrics and the provisional go check from a match_eval.py --json file (ai/docs/m4_plan.md 5-6절).

    python ai/eval/m4_report.py ai/runs/2026-10-15_m4/dev_r0.json [--out ai/runs/2026-10-15_m4/dev_r0_report.json]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

KINDS = ("confirm", "choose", "register", "wrong")
GO_REDUCTION = 0.20
GO_WRONG = 0.10


def ratio(num, den):
    return round(num / den, 4) if den else None


def m4_lines(result: dict) -> list[dict]:
    return [l for l in result["m3_lines"] if isinstance(l.get("m4"), dict)]


def row(result: dict) -> dict:
    totals = result["owner_burden_totals"]
    photos = len(result["owner_burden_by_kind"])
    out = {"matcher": result["matcher"], "condition": result["condition"], "lines": result["lines"],
           "known_top1": result["known_top1"], "false_merge_rate": result["false_merge_rate"],
           "accept_error_rate": result["accept_error_rate"],
           **{f"{k}": totals[k] for k in KINDS},
           **{f"{k}_per_photo": round(totals[k] / photos, 2) for k in KINDS},
           "b_plus_c": totals["choose"] + totals["register"],
           "photos_bcd_under_5": result["photos_under_limit_without_confirm"],
           "confirm_recommended_by_source": result["confirm_recommended_by_source"]}
    lines = m4_lines(result)
    if lines:
        raised = [l for l in lines if l["m4"].get("raised_confirm")]
        targets = [l for l in lines if l["m4"].get("m4") not in ("skipped",)]
        verdicts = Counter(l["m4"]["m4"] for l in lines)
        new = [l for l in lines if l["m4"].get("product_id") == "new"]
        out["m4"] = {
            "target_lines": len(targets), "skipped": verdicts.get("skipped", 0),
            "verdicts": dict(verdicts),
            "raised_confirm": len(raised),
            "raised_confirm_wrong": sum(not l["rank1_gold"] for l in raised),
            "raised_confirm_wrong_rate": ratio(sum(not l["rank1_gold"] for l in raised), len(raised)),
            "picked_not_confirm": sum(bool(l["m4"].get("picked")) and not l["m4"].get("raised_confirm")
                                      and l["m4"]["m4"] != "vetoed" for l in lines),
            "new_verdicts": len(new), "new_verdicts_gold_absent": sum(l["kind"] in ("absent",) for l in new),
            "lines": [{"photo_id": l["photo_id"], "name": l["name"], "gold": l["gold"], "kind": l["kind"],
                       "burden": l["burden"], "rank1_gold": l["rank1_gold"],
                       **{k: l["m4"].get(k) for k in ("m4", "picked", "confidence", "reason", "raised_confirm",
                                                       "options", "vetoed", "short_unverified")}}
                      for l in lines],
        }
    return out


def go_check(rows: dict) -> dict:
    """m4_plan.md 6절, provisional."""
    base, m4 = rows.get(("M3a", "C1")), rows.get(("M3a+M4", "C1"))
    checks = {}
    if base and m4:
        red = ratio(base["b_plus_c"] - m4["b_plus_c"], base["b_plus_c"])
        checks["1_c1_bc_reduction"] = {"M3a": base["b_plus_c"], "M3a+M4": m4["b_plus_c"], "reduction": red,
                                       "pass": red is not None and red >= GO_REDUCTION}
    for cond in ("C0", "C1"):
        r = rows.get(("M3a+M4", cond))
        if r and "m4" in r:
            n, wrong = r["m4"]["raised_confirm"], r["m4"]["raised_confirm_wrong"]
            checks[f"2_wrong_rate_{cond}"] = {"n": n, "wrong": wrong, "rate": ratio(wrong, n),
                                              "pass": n == 0 or wrong / n <= GO_WRONG}
        b = rows.get(("M3a", cond))
        if r and b:
            checks[f"3_false_merge_{cond}"] = {"M3a": b["false_merge_rate"], "M3a+M4": r["false_merge_rate"],
                                               "pass": r["false_merge_rate"] <= b["false_merge_rate"]}
    checks["provisional_go"] = bool(checks) and all(c["pass"] for c in checks.values() if isinstance(c, dict))
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    data = json.loads(args.run.read_text(encoding="utf-8"))
    rows = {(r["matcher"], r["condition"]): row(r) for r in data["results"]}
    report = {"run": args.run.as_posix(), "rows": [{k: v for k, v in r.items() if k != "m4"} | (
        {"m4": {k: v for k, v in r["m4"].items() if k != "lines"}} if "m4" in r else {}) for r in rows.values()],
              "go": go_check(rows), "m4_calls": data.get("m4"), "m3_llm": data.get("llm"),
              "m4_lines": {f"{m}/{c}": r["m4"]["lines"] for (m, c), r in rows.items() if "m4" in r}}
    print(f"{'matcher':10} {'cond':4} {'(a)':>4} {'(b)':>4} {'(c)':>4} {'(d)':>4} {'b+c':>4} {'FM':>6} {'accErr':>7}  M4")
    for r in rows.values():
        m4 = r.get("m4")
        extra = (f"targets {m4['target_lines']} raised {m4['raised_confirm']} wrong {m4['raised_confirm_wrong']} "
                 f"verdicts {m4['verdicts']}") if m4 else ""
        print(f"{r['matcher']:10} {r['condition']:4} {r['confirm']:4} {r['choose']:4} {r['register']:4} {r['wrong']:4} "
              f"{r['b_plus_c']:4} {r['false_merge_rate']:6.3f} {r['accept_error_rate']:7.3f}  {extra}")
    print(json.dumps(report["go"], ensure_ascii=False, indent=1))
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
