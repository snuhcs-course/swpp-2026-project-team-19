"""Rescore stored outputs with labels v1.1 (no API call, no new model output).

    python ai/eval/rescore_labels_v1_1.py [--date 2026-10-14]

Extraction: the stored run records of E1 (P11, val and test) and CLOVA + LLM
(P12, test) are scored with score.py against v1 and v1.1. The v1 numbers must
equal the stored scores.json (checked). Per changed label item and run, the
match status (strict / lenient / missed, price correct) under v1 and v1.1 is
compared and attributed to the fix pattern; items whose status changed without
a fix of their own are listed as knock-on.

Matching: the P22 frozen command (--matcher M0 S1+S2 S1+S2b+S3 --condition C0 C1,
test split; dev too, for reference) is run with match_eval.evaluate, once with
eval/match_gold_v1.json and once with eval/match_gold_v1_1.json. match_eval.py
itself is not changed (frozen); only its GOLD path is swapped here. The v1 test
result must equal ai/runs/2026-10-13_match_test.json (checked).

Writes ai/runs/<date>_labels_v1_1_rescore.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
import score  # noqa: E402

RUNS = [  # (name, run dir, v1 set, v1.1 set)
    ("E1 val (P11, A2 v2)", REPO_ROOT / "ai" / "runs" / "2026-10-13_val_v2_A2", "val", "val_v1_1"),
    ("E1 test (P11, A2 v2)", REPO_ROOT / "ai" / "runs" / "2026-10-13_test_v2_A2", "test", "test_v1_1"),
    ("CLOVA + LLM test (P12, v3)", REPO_ROOT / "ai" / "runs" / "2026-10-14_p12_clova" / "test_v3_parse",
     "test", "test_v1_1"),
]
MATCH_V1_TEST = REPO_ROOT / "ai" / "runs" / "2026-10-13_match_test.json"
CANDIDATES = REPO_ROOT / "review" / "labels_v1_1_candidates.json"
SUMMARY_KEYS = ("item_accuracy", "f1_strict", "f1_lenient", "price_accuracy", "unit_confusion", "fp", "fn")


def fix_patterns() -> dict[str, str]:
    """item id -> "label → print" for the approved fixes (category B)."""
    out = {}
    for d in json.loads(CANDIDATES.read_text(encoding="utf-8")):
        if d["category"] == "B":
            for iid in d["item_ids"]:
                out[iid] = f"{d['label_piece']} → {d['print_text']}"
    return out


def item_status(gt: list[dict], out: list[dict]) -> list[tuple]:
    """Per label item: (match kind or None, counted correct)."""
    pairs, _, _ = score.match_photo(gt, out, lenient=True)
    st = [(None, False)] * len(gt)
    for gi, oi, kind in pairs:
        st[gi] = (kind, score.price_ok(gt[gi], out[oi]))
    return st


def records(run_dir: Path, stem_to_id: dict) -> dict[tuple[int, str], list[dict]]:
    recs = {}
    for f in sorted(run_dir.glob("*_r*.json")):
        m = score.RUN_FILE.match(f.name)
        if not m or m["stem"] not in stem_to_id:
            continue
        out = json.loads(f.read_text(encoding="utf-8")).get("output") or {"items": []}
        recs[(int(m["run"]), stem_to_id[m["stem"]])] = out["items"]
    return recs


def extraction(name: str, run_dir: Path, set_v1: str, set_v11: str, fixes: dict[str, str]) -> dict:
    from extract import data_dir
    stem_to_id = score.load_photo_map(data_dir(), set_v1)
    bars = score.load_bars(set_v1)
    res = {}
    for tag, s in (("v1", set_v1), ("v1.1", set_v11)):
        labels = score.load_labels(s)
        r = score.score_run_dir(run_dir, labels, stem_to_id, False, bars)
        res[tag] = {"summary": r["summary"], "per_bar_accuracy": r["per_bar_accuracy"],
                    "runs": {k: v["total"] for k, v in r["runs"].items()}}
    stored = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
    assert stored["summary"] == res["v1"]["summary"], f"{name}: v1 rescore != stored scores.json"

    # attribution
    old, new = score.load_labels(set_v1), score.load_labels(set_v11)
    trans = defaultdict(Counter)  # pattern -> Counter of "v1 → v1.1" transitions
    knock_on = []
    for (run, pid), out in records(run_dir, stem_to_id).items():
        if old[pid] == new[pid]:
            continue
        a, b = item_status(old[pid], out), item_status(new[pid], out)
        for i, (x, y) in enumerate(zip(a, b)):
            if x == y:
                continue
            iid = f"{pid}#{i}"
            t = f"{fmt_status(x)} → {fmt_status(y)}"
            if iid in fixes:
                trans[fixes[iid]][t] += 1
            else:
                knock_on.append({"run": run, "item": iid, "name": new[pid][i]["raw_name"], "change": t})
    res["attribution"] = {k: dict(v) for k, v in trans.items()}
    res["knock_on"] = knock_on
    res["n_runs"] = len(res["v1"]["runs"])
    return res


def fmt_status(st: tuple) -> str:
    kind, ok = st
    if kind is None:
        return "누락"
    return f"{'엄격' if kind == 'strict' else '관대'}{'' if ok else '(가격 오답)'}"


def matching() -> dict:
    import match_eval
    out = {}
    for tag, gold in (("v1", REPO_ROOT / "eval" / "match_gold_v1.json"),
                      ("v1.1", REPO_ROOT / "eval" / "match_gold_v1_1.json")):
        match_eval.GOLD = gold
        out[tag] = {split: [match_eval.evaluate(m, c, split) for m in ("M0", "S1+S2", "S1+S2b+S3")
                            for c in ("C0", "C1")] for split in ("test", "dev")}
    stored = json.loads(MATCH_V1_TEST.read_text(encoding="utf-8"))
    fresh = json.loads(json.dumps(out["v1"]["test"], ensure_ascii=False, default=str))
    assert fresh == stored, "v1 test matching != ai/runs/2026-10-13_match_test.json"
    # per renamed line: outcome v1 vs v1.1
    changes = []
    for split in ("test", "dev"):
        for r1, r2 in zip(out["v1"][split], out["v1.1"][split]):
            e1 = {(e["photo_id"], e["name"]): e for e in r1["errors"]}
            e2 = {(e["photo_id"], e["name"]): e for e in r2["errors"]}
            changes.append({"split": split, "matcher": r1["matcher"], "condition": r1["condition"],
                            "errors_only_v1": [e for k, e in e1.items() if k not in e2 and not any(
                                k[0] == k2[0] and e["gold"] == e2[k2]["gold"] and e["outcome"] == e2[k2]["outcome"]
                                for k2 in e2)],
                            "errors_only_v1_1": [e for k, e in e2.items() if k not in e1 and not any(
                                k[0] == k1[0] and e["gold"] == e1[k1]["gold"] and e["outcome"] == e1[k1]["outcome"]
                                for k1 in e1)]})
    out["changes"] = changes
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    fixes = fix_patterns()
    result = {"extraction": {name: extraction(name, d, s1, s2, fixes) for name, d, s1, s2 in RUNS},
              "matching": matching()}
    out = REPO_ROOT / "ai" / "runs" / f"{args.date}_labels_v1_1_rescore.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")

    for name, r in result["extraction"].items():
        print(f"\n== {name} ({r['n_runs']} runs)")
        for k in SUMMARY_KEYS:
            a, b = r["v1"]["summary"][k], r["v1.1"]["summary"][k]
            if a:
                print(f"  {k:15s} v1 {a['mean']:.4f} [{a['min']:.3f}-{a['max']:.3f}]   "
                      f"v1.1 {b['mean']:.4f} [{b['min']:.3f}-{b['max']:.3f}]")
        for bar in r["v1"]["per_bar_accuracy"]:
            a, b = r["v1"]["per_bar_accuracy"][bar], r["v1.1"]["per_bar_accuracy"][bar]
            if a != b:
                print(f"  [bar] {bar}: {a['mean']:.4f} -> {b['mean']:.4f}")
        for p, t in r["attribution"].items():
            print(f"  {p}: {dict(t)}")
        if r["knock_on"]:
            print(f"  knock-on: {r['knock_on']}")
    for split in ("test", "dev"):
        print(f"\n== matching {split}")
        for r1, r2 in zip(result["matching"]["v1"][split], result["matching"]["v1.1"][split]):
            print(f"  {r1['matcher']:10s} {r1['condition']}  top1 {r1['known_top1']:.3f} -> {r2['known_top1']:.3f}  "
                  f"fm {r1['false_merge_rate']:.3f} -> {r2['false_merge_rate']:.3f}  "
                  f"burden<5 {r1['photos_under_limit']:.2f} -> {r2['photos_under_limit']:.2f}  "
                  f"totals {r1['owner_burden_totals']} -> {r2['owner_burden_totals']}")
    for c in result["matching"]["changes"]:
        if c["errors_only_v1"] or c["errors_only_v1_1"]:
            print(f"  {c['split']} {c['matcher']} {c['condition']}: "
                  f"fixed {[(e['name'], e['outcome']) for e in c['errors_only_v1']]} "
                  f"new {[(e['name'], e['outcome']) for e in c['errors_only_v1_1']]}")
    print(f"\nwrote {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
