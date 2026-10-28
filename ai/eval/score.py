"""Score extraction runs against a label set (ai/docs/eval_plan.md).

    python ai/eval/score.py ai/runs/2026-10-04_A [ai/runs/2026-10-04_A2 ...]
    python ai/eval/score.py --set test ai/runs/2026-10-13_test_A2

--set val (default) scores against eval/labels_v1.json with photos in
<data_dir>/eval_photos; --set test uses eval/labels_heldout_v1.json with photos in
<data_dir>/eval_photos_test. Labels are pinned by SHA-256. val_v1_1 / test_v1_1 are
the same sets with raw_name as printed on the menu (eval/labels_changelog.md).
--set i3 uses eval/labels_i3_v1.json with photos in <data_dir>/eval_photos_i3.

Each run directory holds one record per call: <photo_stem>_r<k>.json (from
run_experiment.py). A failed or unparseable call counts as an empty output.

Interpretation choices not spelled out in eval_plan.md:
- Names are split on every slash, with or without spaces, and the unsplit name
  is kept as one more candidate (eval_plan 대응 규칙 1).
- Among equally good candidates (same edit distance), a pair whose price also
  matches is preferred, then label order, then output order.
- The headline item accuracy uses the lenient matching (strict, then lenient).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import unicodedata
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LABEL_SETS = {
    "val": {"labels": REPO_ROOT / "eval" / "labels_v1.json",
            "sha256": "c8a29533cc53fb17fb1bfd96f630c7876c8ab5685706b07ad2abd5cff3f81dac",
            "photo_dir": "eval_photos"},
    "test": {"labels": REPO_ROOT / "eval" / "labels_heldout_v1.json",
             "sha256": "07bc5e07e84b43d445520b4e4488ecbf7f928d1ecf5ae6b7b0d94c0908ac98d7",
             "photo_dir": "eval_photos_test"},
    # v1.1: raw_name as printed on the menu (eval/labels_changelog.md); everything else as v1
    "val_v1_1": {"labels": REPO_ROOT / "eval" / "labels_v1_1.json",
                 "sha256": "a34249ebb0528371d23b5c18d3f9ca306a31646fe2a7a447cf4807a389b193cf",
                 "photo_dir": "eval_photos"},
    "test_v1_1": {"labels": REPO_ROOT / "eval" / "labels_heldout_v1_1.json",
                  "sha256": "047bf7d6f7274552f0dce0a4922ce7a72fa4282459d6cf1f6bbfb5271082c986",
                  "photo_dir": "eval_photos_test"},
    # final (P47 only, ai/docs/p47_plan.md): 수이·오드비, guideline v2.3, v1.1 raw_name rule
    "final": {"labels": REPO_ROOT / "eval" / "labels_final_v1.json",
              "sha256": "a8ac42bb36df6b2151b6e6e8938ca141fff5bcbaca2fe391804e4702d3defbf1",
              "photo_dir": "eval_photos_final"},
    # i3 (P30 only, ai/docs/i3_eval_freeze.md): the 8 bars added in I3, guideline v2.3
    "i3": {"labels": REPO_ROOT / "eval" / "labels_i3_v1.json",
           "sha256": "486b47c0aa80e242ff4c34deffd6bccd3c4f100829e236a146d4eea5a11267bb",
           "photo_dir": "eval_photos_i3"},
}
LABELS_PATH = LABEL_SETS["val"]["labels"]
LABELS_SHA256 = LABEL_SETS["val"]["sha256"]
RUN_FILE = re.compile(r"^(?P<stem>.+)_r(?P<run>\d+)\.json$")


# ---------- names ----------

def normalize(name: str) -> str:
    """Lowercase, drop whitespace and punctuation (eval_plan 대응 규칙 1)."""
    return "".join(
        ch for ch in name.lower()
        if not ch.isspace() and not unicodedata.category(ch).startswith("P")
    )


def candidates(raw_name: str) -> list[str]:
    """Whole name plus each slash-separated part, normalized and deduplicated."""
    names = [raw_name] + (raw_name.split("/") if "/" in raw_name else [])
    return list(dict.fromkeys(n for n in map(normalize, names) if n))


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def strict_match(a: str, b: str) -> bool:
    return any(x == y for x in candidates(a) for y in candidates(b))


def lenient_distance(a: str, b: str) -> int | None:
    """Smallest edit distance over candidate pairs whose digit runs are identical
    (in order) and whose non-digit remainder differs by <= 1 edit; else None."""
    best = None
    for x in candidates(a):
        for y in candidates(b):
            if re.findall(r"\d+", x) != re.findall(r"\d+", y):
                continue
            d = levenshtein(re.sub(r"\d+", "", x), re.sub(r"\d+", "", y))
            if d <= 1 and (best is None or d < best):
                best = d
    return best


# ---------- matching ----------

def price_checked(gt: dict) -> bool:
    return gt.get("price_krw") is not None and not gt.get("note")


def price_ok(gt: dict, out: dict) -> bool:
    return not price_checked(gt) or gt["price_krw"] == out.get("price_krw")


def _greedy(pairs, gt_free: set, out_free: set) -> list[tuple[int, int, str]]:
    matched = []
    for _, _, gi, oi, kind in sorted(pairs):
        if gi in gt_free and oi in out_free:
            gt_free.discard(gi)
            out_free.discard(oi)
            matched.append((gi, oi, kind))
    return matched


def match_photo(gt: list[dict], out: list[dict], lenient: bool = True, use_unit: bool = True,
                gt_free: set | None = None, out_free: set | None = None):
    """Pair label items with output items 1:1. Returns (pairs, gt_left, out_left).
    pairs: (gt_idx, out_idx, "strict" | "lenient")."""
    gt_free = set(range(len(gt))) if gt_free is None else set(gt_free)
    out_free = set(range(len(out))) if out_free is None else set(out_free)

    def unit_ok(g, o):
        return not use_unit or g.get("unit") == o.get("unit")

    strict = [
        (0, not price_ok(gt[gi], out[oi]), gi, oi, "strict")
        for gi in gt_free for oi in out_free
        if unit_ok(gt[gi], out[oi]) and strict_match(gt[gi]["raw_name"], out[oi]["raw_name"])
    ]
    pairs = _greedy(strict, gt_free, out_free)
    if lenient:
        loose = []
        for gi in gt_free:
            for oi in out_free:
                if not unit_ok(gt[gi], out[oi]):
                    continue
                d = lenient_distance(gt[gi]["raw_name"], out[oi]["raw_name"])
                if d is not None:
                    loose.append((d, not price_ok(gt[gi], out[oi]), gi, oi, "lenient"))
        pairs += _greedy(loose, gt_free, out_free)
    return pairs, gt_free, out_free


def score_photo(gt: list[dict], out: list[dict], photo_id: str = "") -> dict:
    strict_pairs, _, _ = match_photo(gt, out, lenient=False)
    pairs, gt_left, out_left = match_photo(gt, out, lenient=True)
    # 잔·병 혼동: leftovers re-paired by name only
    confusion, gt_left, out_left = match_photo(gt, out, lenient=True, use_unit=False,
                                              gt_free=gt_left, out_free=out_left)
    correct = [p for p in pairs if price_ok(gt[p[0]], out[p[1]])]
    priced = [p for p in pairs if price_checked(gt[p[0]])]

    errors = []
    for gi, oi, kind in pairs:
        g, o = gt[gi], out[oi]
        if not price_ok(g, o):
            ratio = (o.get("price_krw") or 0) / g["price_krw"]
            swapped = any(
                x is not g and x.get("unit") != g.get("unit") and x.get("price_krw") == o.get("price_krw")
                and strict_match(x["raw_name"], g["raw_name"])
                for x in gt
            )
            if swapped:  # metric-wise a price error; diagnosis-wise a glass/bottle mix-up
                etype = "잔·병 가격 뒤바뀜"
            elif ratio in (10, 100, 1000, 0.1, 0.01, 0.001):
                etype = "가격 단위 환산 오류"
            else:
                etype = "가격 오류(기타)"
            errors.append({"type": etype, "gt": g, "out": o})
        if kind == "lenient":
            errors.append({"type": "이름 오독(관대 일치로 짝)", "gt": g, "out": o, "counted_correct": price_ok(g, o)})
    for gi, oi, _ in confusion:
        errors.append({"type": "잔·병 혼동", "gt": gt[gi], "out": out[oi]})
    for oi in sorted(out_left):
        etype = "비위스키 포함" if not gt else "오탐(분류 필요)"
        errors.append({"type": etype, "out": out[oi]})
    for gi in sorted(gt_left):
        errors.append({"type": "누락", "gt": gt[gi]})

    return {
        "photo_id": photo_id,
        "n_gt": len(gt),
        "n_out": len(out),
        "matched_strict": len(strict_pairs),
        "matched": len(pairs),
        "correct": len(correct),
        # FP for the headline metric = outputs left after unit-aware matching
        "fp": len(out) - len(pairs),
        "fn": len(gt) - len(pairs),
        "priced": len(priced),
        "price_correct": sum(price_ok(gt[gi], out[oi]) for gi, oi, _ in priced),
        "unit_confusion": len(confusion),
        "errors": errors,
    }


def aggregate(photo_scores: list[dict]) -> dict:
    s = defaultdict(int)
    for p in photo_scores:
        for k in ("n_gt", "n_out", "matched_strict", "matched", "correct", "fp", "fn",
                  "priced", "price_correct", "unit_confusion"):
            s[k] += p[k]

    def f1(m):
        prec = m / s["n_out"] if s["n_out"] else 0.0
        rec = m / s["n_gt"] if s["n_gt"] else 0.0
        return 2 * prec * rec / (prec + rec) if prec + rec else 0.0

    denom = s["n_gt"] + s["fp"]
    return {
        **s,
        "item_accuracy": s["correct"] / denom if denom else 0.0,
        "f1_strict": f1(s["matched_strict"]),
        "f1_lenient": f1(s["matched"]),
        "price_accuracy": s["price_correct"] / s["priced"] if s["priced"] else None,
    }


# ---------- I/O ----------

def load_label_file(label_set: str = "val") -> dict:
    cfg = LABEL_SETS[label_set]
    data = cfg["labels"].read_bytes()
    if hashlib.sha256(data).hexdigest() != cfg["sha256"]:
        raise SystemExit(f"{cfg['labels'].name} SHA-256 mismatch (CRLF checkout?): {cfg['labels']}")
    return json.loads(data.decode("utf-8"))


def load_labels(label_set: str = "val") -> dict[str, list[dict]]:
    return {p["photo_id"]: p["items"] for p in load_label_file(label_set)["photos"]}


def load_bars(label_set: str = "val") -> dict[str, str]:
    """photo_id -> bar name."""
    return {p["photo_id"]: p["bar"] for p in load_label_file(label_set)["photos"]}


def load_photo_map(data_dir: Path, label_set: str = "val") -> dict[str, str]:
    """photo_map.json: filename -> photo_id. Returned keyed by file stem."""
    path = data_dir / LABEL_SETS[label_set]["photo_dir"] / "photo_map.json"
    m = json.loads(path.read_text(encoding="utf-8"))["map"]
    return {Path(k).stem: v for k, v in m.items()}


def score_run_dir(run_dir: Path, labels: dict, stem_to_id: dict, only_present: bool = False,
                  bars: dict[str, str] | None = None) -> dict:
    by_run: dict[int, dict[str, list]] = defaultdict(dict)
    failures = []
    for f in sorted(run_dir.glob("*_r*.json")):
        m = RUN_FILE.match(f.name)
        if not m or m["stem"] not in stem_to_id:
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))
        out = rec.get("output")
        if out is None:
            failures.append(f.name)
            out = {"items": []}
        by_run[int(m["run"])][stem_to_id[m["stem"]]] = out["items"]

    runs = {}
    for r, outputs in sorted(by_run.items()):
        missing = sorted(set(labels) - set(outputs))
        scope = sorted(outputs) if only_present else sorted(labels)
        photos = [score_photo(labels[pid], outputs.get(pid, []), pid) for pid in scope]
        runs[r] = {"missing_photos": missing, "total": aggregate(photos), "photos": photos}

    def spread(key):
        vals = [run["total"][key] for run in runs.values() if run["total"][key] is not None]
        if not vals:
            return None
        return {"mean": statistics.mean(vals), "min": min(vals), "max": max(vals), "n": len(vals)}

    keys = ("item_accuracy", "f1_strict", "f1_lenient", "price_accuracy", "unit_confusion",
            "fp", "fn")
    per_photo = defaultdict(list)
    per_bar = defaultdict(list)
    for run in runs.values():
        for p in run["photos"]:
            denom = p["n_gt"] + p["fp"]
            per_photo[p["photo_id"]].append(p["correct"] / denom if denom else 1.0)
        if bars:
            by_bar = defaultdict(list)
            for p in run["photos"]:
                by_bar[bars[p["photo_id"]]].append(p)
            for bar, ps in by_bar.items():
                per_bar[bar].append(aggregate(ps)["item_accuracy"])
    return {
        "run_dir": run_dir.name,
        "failed_calls": failures,
        "summary": {k: spread(k) for k in keys},
        "per_photo_accuracy": {
            pid: {"mean": statistics.mean(v), "min": min(v), "max": max(v)}
            for pid, v in sorted(per_photo.items())
        },
        # bar accuracy = items pooled within the bar per run, then averaged over runs
        "per_bar_accuracy": {
            bar: {"mean": statistics.mean(v), "min": min(v), "max": max(v)}
            for bar, v in sorted(per_bar.items())
        },
        "runs": runs,
    }


def main() -> None:
    import sys
    sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
    from extract import data_dir

    parser = argparse.ArgumentParser(description="Score run directories (eval_plan.md)")
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--set", dest="label_set", choices=sorted(LABEL_SETS), default="val",
                        help="label set: val (labels_v1) or test (labels_heldout_v1)")
    parser.add_argument("--only-present", action="store_true",
                        help="score only photos that have records (pilot); default scores missing photos as empty")
    args = parser.parse_args()

    labels = load_labels(args.label_set)
    bars = load_bars(args.label_set)
    stem_to_id = load_photo_map(data_dir(), args.label_set)
    for run_dir in args.run_dirs:
        result = score_run_dir(run_dir, labels, stem_to_id, args.only_present, bars)
        result["label_set"] = args.label_set
        (run_dir / "scores.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n== {run_dir.name}  (failed calls: {len(result['failed_calls'])})")
        for k, v in result["summary"].items():
            if v:
                print(f"  {k:15s} mean {v['mean']:.3f}  min {v['min']:.3f}  max {v['max']:.3f}  (n={v['n']})")
        for pid, v in result["per_photo_accuracy"].items():
            print(f"  {pid:20s} acc mean {v['mean']:.3f}  [{v['min']:.3f}-{v['max']:.3f}]")
        for bar, v in result["per_bar_accuracy"].items():
            print(f"  [bar] {bar:14s} acc mean {v['mean']:.3f}  [{v['min']:.3f}-{v['max']:.3f}]")


if __name__ == "__main__":
    main()
