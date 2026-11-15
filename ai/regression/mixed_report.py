"""Mixed-menu extraction report on the 15 regression photos (I4-P25). Offline: no API key, no photo.

    python ai/regression/mixed_report.py                          # the recorded prompt v1 and v2 runs
    python ai/regression/mixed_report.py <run dir> [<run dir> ...]  # other run directories
    python ai/regression/mixed_report.py --json report.json --markdown report.md

A menu has whisky lines and other lines (cocktails, food, other drinks). regression.py scores the
whisky lines only. This report scores every line of the photo and says how each was classified.

Expected lines of a photo (`expected_rows`), one row per price option:
  whisky      the fixture rows whose match gold is a product, a new product or unknown
  non-whisky  the fixture rows whose match gold is non_whisky (category other), and the rows of
              mixed_lines.json (cocktail / food / other), which the whisky labels do not have

Output lines of a record (`output_rows`): the rows the server makes from the recorded answer.
Items sent to matching are category whisky; a prompt v2 record's otherItems keep their category.
A prompt v1 record has no categories, so all its rows are whisky.

Expected and output rows are paired once, across categories, with ai/eval/score.py
(`match_photo`: name, strict then lenient, and the same unit). From the pairs:

  line recall          paired expected rows / expected rows (also per whisky and non-whisky)
  extra-line rate      output rows without a pair / output rows
  price accuracy       pairs with the expected price / pairs whose expected row has a checked price
  duplicate-line rate  output rows that repeat an earlier row (name, unit, pour size, price) / output rows
  classification error pairs whose output category differs from the expected one / pairs, split into
      whisky_as_non_whisky   a whisky line kept out of product matching (the line is lost for search)
      non_whisky_as_whisky   a non-whisky line sent to product matching
      wrong_kind             cocktail, food and other mixed up among themselves

A record the server would reject counts as an empty output. Rates are over the summed counts of a
run directory, and `per_run` gives the same per run number (r1, r2, ...), since one answer can differ
from the next. mixed_lines.json says where the non-whisky lines come from and what that limits.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "eval"))

import regression as reg  # noqa: E402
from score import match_photo, price_checked, price_ok  # noqa: E402

MIXED_LINES = HERE / "mixed_lines.json"
DEFAULT_RUNS = ("ai/runs/2026-11-13_p12/hybrid_v1", "ai/runs/2026-11-13_p12/hybrid_v2")
CATEGORIES = ("whisky", "cocktail", "food", "other")
COUNTS = ("records", "rejected", "expected", "expected_whisky", "expected_non_whisky", "output", "paired",
          "paired_whisky", "paired_non_whisky", "extra", "priced", "price_correct", "duplicates",
          "whisky_as_non_whisky", "non_whisky_as_whisky", "wrong_kind")
ROW_KEYS = ("raw_name", "price_krw", "pour_ml", "unit")
MAX_LISTED = 6


def load_mixed_lines() -> dict[str, list[dict]]:
    return json.loads(MIXED_LINES.read_text(encoding="utf-8"))["photos"]


def expected_rows(fixture: dict, mixed: dict[str, list[dict]]) -> list[dict]:
    """Every line of the photo with its category. Fixture rows keep their price note (score.py
    does not check the price of a row with a note)."""
    rows = [{**{k: item[k] for k in ROW_KEYS}, "note": item.get("note"),
             "category": "other" if item["gold"] == "non_whisky" else "whisky"}
            for item in fixture["expected_items"]]
    rows += [{**{k: line[k] for k in ROW_KEYS}, "note": None, "category": line["category"]}
             for line in mixed.get(fixture["photo_id"], [])]
    return rows


def output_rows(output: dict | None) -> list[dict]:
    """Rows of one server output (regression.server_output), whisky rows first."""
    if output is None:
        return []
    rows = [{**row, "category": "whisky"} for row in reg.flatten(output["items"])]
    for item in output["otherItems"]:
        for option in item["options"] or [{"optionLabel": None, "pourMl": None, "priceKrw": None}]:
            rows.append({"raw_name": item["rawText"], "price_krw": option["priceKrw"], "pour_ml": option["pourMl"],
                         "unit": reg.UNIT_OF_LABEL[option["optionLabel"]], "category": item["category"]})
    return rows


def score_record(expected: list[dict], out: list[dict], rejected: bool = False) -> dict:
    """Counts of one record and the lines behind the classification errors."""
    pairs, expected_left, _ = match_photo(expected, out, lenient=True)
    counts = dict.fromkeys(COUNTS, 0)
    counts.update(records=1, rejected=int(rejected), expected=len(expected), output=len(out), paired=len(pairs),
                  expected_whisky=sum(row["category"] == "whisky" for row in expected),
                  extra=len(out) - len(pairs), duplicates=reg.duplicates(out))
    counts["expected_non_whisky"] = counts["expected"] - counts["expected_whisky"]
    confusion: dict[str, int] = {}
    errors = []
    for gi, oi, _ in pairs:
        gold, got = expected[gi], out[oi]
        counts["paired_whisky" if gold["category"] == "whisky" else "paired_non_whisky"] += 1
        if price_checked(gold):
            counts["priced"] += 1
            counts["price_correct"] += price_ok(gold, got)
        key = f"{gold['category']}->{got['category']}"
        confusion[key] = confusion.get(key, 0) + 1
        if gold["category"] == got["category"]:
            continue
        kind = ("whisky_as_non_whisky" if gold["category"] == "whisky"
                else "non_whisky_as_whisky" if got["category"] == "whisky" else "wrong_kind")
        counts[kind] += 1
        errors.append({"type": kind, "line": gold["raw_name"], "expected": gold["category"], "got": got["category"]})
    missed = [{"line": expected[gi]["raw_name"], "expected": expected[gi]["category"]} for gi in sorted(expected_left)]
    return {"counts": counts, "confusion": confusion, "errors": errors, "missed": missed}


def rates(c: dict) -> dict:
    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 4) if b else None

    return {
        "line_recall": ratio(c["paired"], c["expected"]),
        "whisky_line_recall": ratio(c["paired_whisky"], c["expected_whisky"]),
        "non_whisky_line_recall": ratio(c["paired_non_whisky"], c["expected_non_whisky"]),
        "extra_line_rate": ratio(c["extra"], c["output"]),
        "price_accuracy": ratio(c["price_correct"], c["priced"]),
        "duplicate_line_rate": ratio(c["duplicates"], c["output"]),
        "classification_error_rate": ratio(
            c["whisky_as_non_whisky"] + c["non_whisky_as_whisky"] + c["wrong_kind"], c["paired"]),
    }


def _summary(scores: list[dict]) -> dict:
    counts = dict.fromkeys(COUNTS, 0)
    confusion: dict[str, int] = {}
    for score in scores:
        for key in COUNTS:
            counts[key] += score["counts"][key]
        for key, n in score["confusion"].items():
            confusion[key] = confusion.get(key, 0) + n
    return {"counts": counts, "rates": rates(counts), "confusion": dict(sorted(confusion.items()))}


def report_run_dir(run_dir: Path, fixtures: list[dict], mixed: dict[str, list[dict]]) -> dict:
    """The report of one run directory: total, per run number, per photo, and the misclassified lines."""
    records: list[tuple[int, str, dict]] = []
    for fx in fixtures:
        stem = Path(fx["photo"]["file"]).stem
        expected = expected_rows(fx, mixed)
        for path in sorted(run_dir.glob(f"{stem}_r*.json")):
            m = reg.RUN_FILE.match(path.name)
            if not m or m["stem"] != stem:
                continue
            output = reg.record_output(json.loads(path.read_text(encoding="utf-8")))
            score = score_record(expected, output_rows(output), rejected=output is None)
            for line in score["errors"] + score["missed"]:
                line.update(photo_id=fx["photo_id"], record=path.name)
            records.append((int(m["run"]), fx["photo_id"], score))
    scores = [score for _, _, score in records]
    found = {pid for _, pid, _ in records}
    return {
        **_summary(scores),
        "per_run": {str(run): _summary([s for r, _, s in records if r == run])
                    for run in sorted({r for r, _, _ in records})},
        "per_photo": {fx["photo_id"]: _summary([s for _, pid, s in records if pid == fx["photo_id"]])
                      for fx in fixtures if fx["photo_id"] in found},
        "misclassified": [error for score in scores for error in score["errors"]],
        "missed": [line for score in scores for line in score["missed"]],
        "photos_without_record": [fx["photo_id"] for fx in fixtures if fx["photo_id"] not in found],
    }


def build_report(run_dirs: list[str]) -> dict:
    fixtures = reg.load_fixtures()
    mixed = load_mixed_lines()
    expected = [row for fx in fixtures for row in expected_rows(fx, mixed)]
    return {
        "report": "mixed-menu extraction metrics (I4-P25)",
        "fixtures": {
            "photos": len(fixtures),
            "expected_rows": len(expected),
            "by_category": {c: sum(row["category"] == c for row in expected) for c in CATEGORIES},
            "whisky_labels": sorted({fx["labels"] for fx in fixtures}),
            "non_whisky_lines": MIXED_LINES.relative_to(reg.REPO_ROOT).as_posix(),
        },
        "runs": {Path(d).as_posix(): report_run_dir(_resolve(d), fixtures, mixed) for d in run_dirs},
    }


def _resolve(run_dir: str) -> Path:
    path = Path(run_dir)
    return path if path.is_absolute() else reg.REPO_ROOT / path


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


TABLE = (
    ("Records (rejected)", lambda s: f"{s['counts']['records']} ({s['counts']['rejected']})"),
    ("Line recall", lambda s: f"{_pct(s['rates']['line_recall'])} ({s['counts']['paired']}/{s['counts']['expected']})"),
    ("Whisky line recall", lambda s: f"{_pct(s['rates']['whisky_line_recall'])} "
                                     f"({s['counts']['paired_whisky']}/{s['counts']['expected_whisky']})"),
    ("Non-whisky line recall", lambda s: f"{_pct(s['rates']['non_whisky_line_recall'])} "
                                         f"({s['counts']['paired_non_whisky']}/{s['counts']['expected_non_whisky']})"),
    ("Extra-line rate", lambda s: f"{_pct(s['rates']['extra_line_rate'])} ({s['counts']['extra']}/{s['counts']['output']})"),
    ("Price accuracy", lambda s: f"{_pct(s['rates']['price_accuracy'])} "
                                 f"({s['counts']['price_correct']}/{s['counts']['priced']})"),
    ("Duplicate-line rate", lambda s: f"{_pct(s['rates']['duplicate_line_rate'])} "
                                      f"({s['counts']['duplicates']}/{s['counts']['output']})"),
    ("Classification error rate", lambda s: f"{_pct(s['rates']['classification_error_rate'])} "
                                            f"({s['counts']['whisky_as_non_whisky'] + s['counts']['non_whisky_as_whisky'] + s['counts']['wrong_kind']}"
                                            f"/{s['counts']['paired']})"),
    ("Whisky line read as non-whisky", lambda s: str(s["counts"]["whisky_as_non_whisky"])),
    ("Non-whisky line read as whisky", lambda s: str(s["counts"]["non_whisky_as_whisky"])),
    ("Wrong non-whisky kind", lambda s: str(s["counts"]["wrong_kind"])),
)


def _listed(rows: list[dict], describe) -> list[str]:
    """One bullet per line with the number of records it is in. More than MAX_LISTED lines of one
    photo with the same description and count (a page prompt v1 leaves out) become one bullet."""
    seen: dict[tuple, set[str]] = {}
    for e in rows:
        seen.setdefault((e["photo_id"], e["line"], describe(e)), set()).add(e["record"])
    groups: dict[tuple, list[str]] = {}
    for (pid, line, what), records in seen.items():
        groups.setdefault((pid, what, len(records)), []).append(line)
    out = []
    for (pid, what, n), names in groups.items():
        if len(names) > MAX_LISTED:
            out.append(f"- {pid}: {len(names)} lines ({what}; {n})")
        else:
            out += [f"- {pid}: {name} ({what}; {n})" for name in names]
    return out


def markdown(report: dict) -> str:
    fx = report["fixtures"]
    cats = ", ".join(f"{c} {n}" for c, n in fx["by_category"].items())
    lines = ["# Mixed-menu extraction report", "",
             f"{fx['photos']} photos, {fx['expected_rows']} expected rows ({cats}). "
             f"Counts in brackets are summed over the records of the run directory.", ""]
    for run_dir, run in report["runs"].items():
        columns = [("all runs", run)] + [(f"r{k}", v) for k, v in run["per_run"].items()]
        lines += [f"## {run_dir}", "", "| | " + " | ".join(name for name, _ in columns) + " |",
                  "|---|" + "---|" * len(columns)]
        lines += [f"| {label} | " + " | ".join(cell(s) for _, s in columns) + " |" for label, cell in TABLE]
        lines += ["", "Category of paired lines, expected -> output: "
                  + (", ".join(f"{k} {n}" for k, n in run["confusion"].items()) or "none"), ""]
        if run["photos_without_record"]:
            lines += ["No record for: " + ", ".join(run["photos_without_record"]), ""]
        for title, rows, describe in (
            ("Misclassified lines", run["misclassified"], lambda e: f"expected {e['expected']}, got {e['got']}"),
            ("Expected lines the output does not have", run["missed"], lambda e: e["expected"]),
        ):
            listed = _listed(rows, describe)
            if listed:
                lines += [f"{title} (and in how many records of the photo):", "", *listed, ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dirs", nargs="*", default=list(DEFAULT_RUNS), help="run directories (default: the P12 v1 and v2 runs)")
    ap.add_argument("--json", type=Path, help="write the full report as JSON")
    ap.add_argument("--markdown", type=Path, help="write the tables as Markdown")
    args = ap.parse_args(argv)

    missing = [d for d in args.run_dirs if not _resolve(d).is_dir()]
    if missing:
        print("not a directory: " + ", ".join(missing))
        return 2
    report = build_report(args.run_dirs)
    text = markdown(report)
    if args.json:
        args.json.write_text(reg.dump_json(report), encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
