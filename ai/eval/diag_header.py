"""Post-hoc diagnostic: item accuracy ignoring the brand/bottler title rule.

    python ai/eval/diag_header.py --set test ai/runs/2026-10-13_test_v2_A2
    python ai/eval/diag_header.py ai/runs/2026-10-13_val_v2_A2

Not part of the decision rule (eval_plan.md); score.py is unchanged and its
numbers stay the pre-registered results.

After score.py's matching, the leftover false positives and misses of a photo
are paired once more (1:1, label order then output order). A pair counts as
correct when one name, with its leading title up to and including the first
")" removed (e.g. "라 메종드 위스키(LMDW) "), equals the other name under
score.normalize, the units are equal and score.price_ok holds. Both directions
are tried: title only in the label, or title only in the output.

Writes <run_dir>/diag_header.json and prints a markdown table.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from score import (LABEL_SETS, REPO_ROOT, RUN_FILE, load_bars, load_labels, load_photo_map,
                   normalize, price_ok, score_photo)

TITLE = re.compile(r"^[^()]*\([^()]*\)\s*")


def strip_title(name: str) -> str | None:
    """Name without its leading "title(...)" part, or None if there is none."""
    m = TITLE.match(name)
    rest = name[m.end():] if m else ""
    return rest if rest.strip() else None


def title_match(a: str, b: str) -> bool:
    """True if a minus its title equals b, or b minus its title equals a."""
    for x, y in ((a, b), (b, a)):
        rest = strip_title(x)
        if rest is not None and normalize(rest) == normalize(y):
            return True
    return False


def rescue(photo: dict) -> list[dict]:
    """Pair score.py's leftover misses and false positives that differ only by a title."""
    fn = [e["gt"] for e in photo["errors"] if e["type"] == "누락"]
    fp = [e["out"] for e in photo["errors"] if e["type"] in ("오탐(분류 필요)", "비위스키 포함")]
    used: set[int] = set()
    pairs = []
    for g in fn:
        for k, o in enumerate(fp):
            if (k not in used and g.get("unit") == o.get("unit") and price_ok(g, o)
                    and title_match(g["raw_name"], o.get("raw_name") or "")):
                used.add(k)
                pairs.append({"gt": g["raw_name"], "out": o["raw_name"], "price_krw": g.get("price_krw")})
                break
    return pairs


def accuracy(ps: list[dict], adjusted: bool) -> float:
    correct = sum(p["correct"] + (len(p["rescued"]) if adjusted else 0) for p in ps)
    denom = sum(p["n_gt"] + p["fp"] - (len(p["rescued"]) if adjusted else 0) for p in ps)
    return correct / denom if denom else 1.0


def spread(vals: list[float]) -> dict:
    return {"mean": statistics.mean(vals), "min": min(vals), "max": max(vals)}


def diag_run_dir(run_dir: Path, labels: dict, stem_to_id: dict, bars: dict) -> dict:
    by_run: dict[int, dict[str, list]] = defaultdict(dict)
    for f in sorted(run_dir.glob("*_r*.json")):
        m = RUN_FILE.match(f.name)
        if not m or m["stem"] not in stem_to_id:
            continue
        out = json.loads(f.read_text(encoding="utf-8")).get("output") or {"items": []}
        by_run[int(m["run"])][stem_to_id[m["stem"]]] = out["items"]

    runs = {}
    for r, outputs in sorted(by_run.items()):
        photos = []
        for pid in sorted(labels):
            p = score_photo(labels[pid], outputs.get(pid, []), pid)
            photos.append({"photo_id": pid, "n_gt": p["n_gt"], "fp": p["fp"], "correct": p["correct"],
                           "rescued": rescue(p)})
        by_bar = defaultdict(list)
        for p in photos:
            by_bar[bars[p["photo_id"]]].append(p)
        runs[r] = {
            "official": accuracy(photos, False),
            "diag": accuracy(photos, True),
            "rescued": sum(len(p["rescued"]) for p in photos),
            "bars": {b: {"official": accuracy(ps, False), "diag": accuracy(ps, True)} for b, ps in by_bar.items()},
            "photos": photos,
        }

    def collect(fn):
        vals = defaultdict(lambda: {"official": [], "diag": []})
        for run in runs.values():
            for key, o, d in fn(run):
                vals[key]["official"].append(o)
                vals[key]["diag"].append(d)
        return {k: {kind: spread(v) for kind, v in kv.items()} for k, kv in sorted(vals.items())}

    return {
        "run_dir": run_dir.name,
        "note": "post-hoc diagnostic; not part of the eval_plan.md decision rule",
        "summary": {"official": spread([r["official"] for r in runs.values()]),
                    "diag": spread([r["diag"] for r in runs.values()])},
        "per_bar": collect(lambda run: [(b, v["official"], v["diag"]) for b, v in run["bars"].items()]),
        "per_photo": collect(lambda run: [(p["photo_id"], accuracy([p], False), accuracy([p], True))
                                          for p in run["photos"]]),
        "runs": runs,
    }


def fmt(v: dict) -> str:
    return f"{v['mean']:.3f} ({v['min']:.3f}–{v['max']:.3f})"


def print_report(res: dict, label_set: str) -> None:
    print(f"\n## {res['run_dir']} (라벨 셋: {label_set})\n")
    print("| 회차 | 항목 정답률 (score.py) | 제목 규칙 무관 정답률 | 다시 정답으로 친 쌍 |")
    print("| --- | --- | --- | --- |")
    for r, run in res["runs"].items():
        print(f"| r{r} | {run['official']:.3f} | {run['diag']:.3f} | {run['rescued']} |")
    s = res["summary"]
    total = sum(run["rescued"] for run in res["runs"].values())
    print(f"| 평균 (최소–최대) | {fmt(s['official'])} | {fmt(s['diag'])} | 합계 {total} |")
    for title, rows in (("바", res["per_bar"]), ("사진", res["per_photo"])):
        print(f"\n| {title} | score.py | 제목 규칙 무관 |\n| --- | --- | --- |")
        for k, v in rows.items():
            print(f"| {k} | {fmt(v['official'])} | {fmt(v['diag'])} |")


def main() -> None:
    sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
    from extract import data_dir

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--set", dest="label_set", choices=sorted(LABEL_SETS), default="val")
    args = parser.parse_args()

    labels = load_labels(args.label_set)
    bars = load_bars(args.label_set)
    stem_to_id = load_photo_map(data_dir(), args.label_set)
    for run_dir in args.run_dirs:
        res = diag_run_dir(run_dir, labels, stem_to_id, bars)
        res["label_set"] = args.label_set
        (run_dir / "diag_header.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print_report(res, args.label_set)


if __name__ == "__main__":
    main()
