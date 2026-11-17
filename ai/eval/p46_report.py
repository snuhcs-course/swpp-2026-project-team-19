"""P46 report: the frozen-set metrics of Iteration 4 as one JSON and one table (I4-P46). Offline.

    python ai/eval/p46_report.py --out ai/runs/<date>_p46 \\
        --extraction v2=ai/runs/<date>_p46/hybrid_v2_i3 --extraction v1=<P30 run dir> \\
        --matching ai/runs/<date>_p46/match/*.json

It only reads what the other commands wrote and puts the numbers side by side:

  extraction   <run dir>/scores.json of ai/eval/score.py --set i3: whisky name F1 (strict),
               price accuracy and item accuracy, mean [min-max] over r1-r3 (NFR-1, NFR-2)
  mixed lines  every line of the 33 photos, whisky and not, scored as ai/regression/mixed_report.py
               scores the regression photos: line recall, price accuracy, duplicate lines, and
               how each line was classified. Whisky lines are eval/labels_i3_v1.json; non-whisky
               lines are the label rows whose match gold is non_whisky plus eval/mixed_lines_i3_v1.json
  matching     result JSONs of ai/eval/i3_match_eval.py, grouped by catalog, input and matcher
               (rules / llm / server): Top-1 (NFR-3), false-merge rate (NFR-4), acceptance error
               and hard lines per photo, mean [min-max] over the runs of a group

A P30 record (prompt v1) keeps the model output under "output" and not the answer text, so it
is replayed from that output; the server code after the model call is the same.

The 33 photos have few non-whisky lines (one bar's page and a promotion page): the mixed-line
counts are reported as counts, and rates over them move by several points per line.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "regression"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))

import mixed_report as mixed  # noqa: E402
import regression as reg  # noqa: E402

LABELS = "eval/labels_i3_v1.json"
GOLD = "eval/match_gold_i3_v1.json"
MIXED_LINES = "eval/mixed_lines_i3_v1.json"
PHOTO_HASHES = "ai/eval/i3_photo_sha256.json"
THRESHOLDS = {"f1_strict": (">=", 0.90, "NFR-1"), "price_accuracy": (">=", 0.95, "NFR-2"),
              "top1": (">=", 0.90, "NFR-3"), "fm_rate": ("<=", 0.02, "NFR-4")}
MATCH_KEYS = ("top1", "fm_rate", "accept_err_rate", "hard_per_photo")


def i3_fixtures(labels: dict, gold: dict, hashes: dict) -> list[dict]:
    """The 33 photos in the shape mixed_report scores: expected rows with their match gold."""
    files = {p["photo_id"]: p["file"] for p in hashes["photos"]}
    gold_items = {p["photo_id"]: p["items"] for p in gold["photos"]}
    fixtures = []
    for photo in labels["photos"]:
        golds = gold_items[photo["photo_id"]]
        if [i["raw_name"] for i in photo["items"]] != [i["raw_name"] for i in golds]:
            raise SystemExit(f"{photo['photo_id']}: gold names differ from the labels")
        fixtures.append({"photo_id": photo["photo_id"], "photo": {"file": files[photo["photo_id"]]},
                         "expected_items": [{"raw_name": li["raw_name"], "price_krw": li["price_krw"],
                                             "pour_ml": li["pour_ml"], "unit": li["unit"], "note": li.get("note"),
                                             "gold": gi["gold"]} for li, gi in zip(photo["items"], golds)]})
    return fixtures


def replayable(record: dict) -> dict:
    """A P30 record has the model output but not its text; give it the text the replay reads."""
    if record.get("raw_text") or record.get("output") is None:
        return record
    return {**record, "raw_text": json.dumps(record["output"], ensure_ascii=False)}


def mixed_report(run_dir: Path, fixtures: list[dict], lines: dict[str, list[dict]]) -> dict:
    """mixed_report.report_run_dir for the I3 photos (P30 records made replayable)."""
    records = []
    for fx in fixtures:
        stem = Path(fx["photo"]["file"]).stem
        expected = mixed.expected_rows(fx, lines)
        for path in sorted(run_dir.glob(f"{stem}_r*.json")):
            m = reg.RUN_FILE.match(path.name)
            if not m or m["stem"] != stem:
                continue
            output = reg.record_output(replayable(json.loads(path.read_text(encoding="utf-8"))))
            score = mixed.score_record(expected, mixed.output_rows(output), rejected=output is None)
            for line in score["errors"] + score["missed"]:
                line.update(photo_id=fx["photo_id"], record=path.name)
            records.append((int(m["run"]), score))
    scores = [score for _, score in records]
    return {**mixed._summary(scores),
            "per_run": {str(run): mixed._summary([s for r, s in records if r == run])
                        for run in sorted({r for r, _ in records})},
            "misclassified": [e for s in scores for e in s["errors"]],
            "missed_non_whisky": [e for s in scores for e in s["missed"] if e["expected"] != "whisky"],
            "records": len(records)}


def spread(values: list[float]) -> dict | None:
    values = [v for v in values if v is not None]
    return {"mean": statistics.mean(values), "min": min(values), "max": max(values), "n": len(values)} if values else None


def matching_groups(paths: list[Path]) -> dict[str, dict]:
    """Result JSONs grouped by (catalog, input kind, matcher); incomplete LLM runs are left out and listed."""
    groups: dict[str, dict] = {}
    incomplete = []
    for path in sorted(paths):
        result = json.loads(path.read_text(encoding="utf-8"))
        kind = "e2e" if result["input"].startswith("extraction") else "label"
        for matcher in ("rules", "llm", "server"):
            if matcher not in result:
                continue
            block = result[matcher]
            if matcher != "rules" and block.get("complete") is False:
                incomplete.append(f"{path.name}:{matcher}")
                continue
            name = f"{result['catalog']}/{kind}/{matcher}" + (
                f" after {block['after']}" if matcher == "server" else "")
            group = groups.setdefault(name, {"files": [], "catalog_digest": set(), "rules_repo_head": set(),
                                             "values": {k: [] for k in MATCH_KEYS}, "lines": [], "e2e_top1": []})
            group["files"].append(path.name)
            group["catalog_digest"].add(result["catalog_digest"])
            group["rules_repo_head"].add(result.get("rules_repo_head"))
            group["lines"].append(block["all"]["lines"])
            for key in MATCH_KEYS:
                group["values"][key].append(block["all"][key])
            if "e2e" in block:
                group["e2e_top1"].append(block["e2e"]["top1_missed_as_fail"])
    out = {}
    for name, group in sorted(groups.items()):
        out[name] = {"files": group["files"], "catalog_digest": sorted(group["catalog_digest"]),
                     "rules_repo_head": sorted(h for h in group["rules_repo_head"] if h),
                     "lines": sorted(set(group["lines"])),
                     **{key: spread(values) for key, values in group["values"].items()},
                     "top1_missed_as_fail": spread(group["e2e_top1"])}
    return {"groups": out, "incomplete_left_out": incomplete}


def verdict(key: str, value: float | None) -> str:
    if key not in THRESHOLDS or value is None:
        return ""
    op, limit, nfr = THRESHOLDS[key]
    met = value >= limit if op == ">=" else value <= limit
    return f" ({nfr} {op} {limit}: {'met' if met else 'NOT met'})"


def _cell(s: dict | None, digits: int = 3) -> str:
    if s is None:
        return "-"
    if s["n"] == 1:
        return f"{s['mean']:.{digits}f}"
    return f"{s['mean']:.{digits}f} [{s['min']:.{digits}f}-{s['max']:.{digits}f}]"


def markdown(report: dict) -> str:
    lines = ["# P46: frozen-set metrics (Iteration 4)", ""]
    if report["extraction"]:
        lines += ["## Extraction (whisky lines, score.py --set i3)", "",
                  "| prompt | name F1 strict | price accuracy | item accuracy | runs |", "|---|---|---|---|---|"]
        for name, e in report["extraction"].items():
            s = e["summary"]
            lines.append(f"| {name} | {_cell(s['f1_strict'])}{verdict('f1_strict', s['f1_strict']['mean'])} "
                         f"| {_cell(s['price_accuracy'])}{verdict('price_accuracy', s['price_accuracy']['mean'])} "
                         f"| {_cell(s['item_accuracy'])} | {s['f1_strict']['n']} |")
        lines.append("")
    if report["mixed"]:
        lines += ["## All lines of the photos (counts over the records of a run dir)", "",
                  "| prompt | records | whisky lines paired | non-whisky lines paired | whisky as non-whisky "
                  "| non-whisky as whisky | wrong kind | duplicates |", "|---|---|---|---|---|---|---|---|"]
        for name, m in report["mixed"].items():
            c = m["counts"]
            lines.append(f"| {name} | {m['records']} | {c['paired_whisky']}/{c['expected_whisky']} "
                         f"| {c['paired_non_whisky']}/{c['expected_non_whisky']} | {c['whisky_as_non_whisky']} "
                         f"| {c['non_whisky_as_whisky']} | {c['wrong_kind']} | {c['duplicates']} |")
        lines.append("")
    if report["matching"]["groups"]:
        lines += ["## Matching (i3_match_eval.py)", "",
                  "| catalog / input / matcher | Top-1 | false-merge rate | acceptance error | hard lines per photo | runs |",
                  "|---|---|---|---|---|---|"]
        for name, g in report["matching"]["groups"].items():
            judged = name.startswith("full/label/")
            lines.append(f"| {name} | {_cell(g['top1'])}{verdict('top1', g['top1']['mean']) if judged else ''} "
                         f"| {_cell(g['fm_rate'], 4)}{verdict('fm_rate', g['fm_rate']['mean'])} "
                         f"| {_cell(g['accept_err_rate'], 4)} | {_cell(g['hard_per_photo'], 2)} | {g['top1']['n']} |")
        lines.append("")
        if report["matching"]["incomplete_left_out"]:
            lines += ["Incomplete LLM runs left out: " + ", ".join(report["matching"]["incomplete_left_out"]), ""]
    return "\n".join(lines)


def build(extraction: dict[str, Path], matching: list[Path], repo: Path = REPO_ROOT) -> dict:
    report = {"report": "frozen-set metrics (I4-P46)", "extraction": {}, "mixed": {},
              "matching": matching_groups(matching)}
    if extraction:
        read = lambda rel: json.loads((repo / rel).read_text(encoding="utf-8"))
        fixtures = i3_fixtures(read(LABELS), read(GOLD), read(PHOTO_HASHES))
        lines = read(MIXED_LINES)
        expected = [row for fx in fixtures for row in mixed.expected_rows(fx, lines["photos"])]
        report["expected_rows"] = {c: sum(row["category"] == c for row in expected) for c in mixed.CATEGORIES}
        report["non_whisky_lines_reviewed"] = lines.get("reviewed")
        for name, run_dir in extraction.items():
            scores = run_dir / "scores.json"
            if scores.is_file():
                data = json.loads(scores.read_text(encoding="utf-8"))
                report["extraction"][name] = {"run_dir": run_dir.as_posix(), "summary": data["summary"],
                                              "failed_calls": len(data["failed_calls"])}
            report["mixed"][name] = {"run_dir": run_dir.as_posix(), **mixed_report(run_dir, fixtures, lines["photos"])}
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True, help="directory for p46_metrics.json and p46_metrics.md")
    ap.add_argument("--extraction", action="append", default=[], metavar="NAME=RUN_DIR")
    ap.add_argument("--matching", type=Path, nargs="*", default=[], help="i3_match_eval.py result JSONs")
    args = ap.parse_args(argv)
    extraction = {}
    for spec in args.extraction:
        name, _, run_dir = spec.partition("=")
        if not run_dir or not Path(run_dir).is_dir():
            ap.error(f"--extraction NAME=RUN_DIR: {spec}")
        extraction[name] = Path(run_dir)
    report = build(extraction, args.matching)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "p46_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    text = markdown(report)
    (args.out / "p46_metrics.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
