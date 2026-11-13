"""Regression check on 15 labeled menu photos (I4-P6). Offline: no API key, no photo, no network.

    python -m pytest ai/regression                       # what CI runs
    python ai/regression/regression.py                   # the same check with a per-photo table
    python ai/regression/regression.py --update          # rewrite fixtures/ and baseline.json
    python ai/regression/regression.py --extraction <run dir> [--run 1]   # score a new extraction run
    python ai/regression/regression.py --check-photos <data_dir>          # local photos = the listed SHA-256

Fixtures (fixtures/<photo_id>.json) hold the expected output of one photo: every item's name,
price, pour size and unit (the layer-1 label) and its catalog product (the layer-2 gold). They are
built from selection.json, eval/labels_*.json and eval/match_gold_*.json, and the tests fail when
they drift from those files.

Two things are checked against baseline.json.

Extraction replay. The model's recorded answers for these photos (ai/runs/.../<stem>_r<k>.json,
`raw_text`) go through the server's own code after the model call (HybridExtraction ->
to_flow_items -> ExtractionItems, backend/app/extraction; hybrid_v2.convert_output for a prompt
v2 record, whose non-whisky lines are counted as other_items), are flattened back to one row per
price option, and are scored against the fixture with ai/eval/score.py. score.py does not read
the pour size, so the paired rows' pour sizes are compared here too (pour_wrong). The number of items
the server makes is kept too, since it shows how glass and bottle rows were grouped. The input is fixed, so
the score must equal the baseline exactly: a difference means the schema, the conversion or the
scorer changed. This does not call the model, so it cannot see a prompt or model change; for
that, make a new run and score it with --extraction.

Matching. Every expected line goes through the server's rule matcher
(resolve_product_staged, stages S1+S2+S2b+S3) against the catalog the seed script loads
(catalog_v2_service.json + catalog_v2_service_i3_additions.json), under two conditions:
  deployed  the catalog as it is (these bars' own menu spellings are aliases)
  heldout   aliases whose only source is that bar's menu are dropped ("the product is known,
            this spelling is new"), as ai/eval/i3_match_eval.py --catalog service does
A line may get better than its baseline, never worse (SEVERITY): a correct line that stops
being correct, or a new false merge, fails the check. After an intended change, run --update
and say in the PR which lines changed and why.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))

import i3_match_eval as harness  # noqa: E402
from score import match_photo, normalize, score_photo  # noqa: E402

SELECTION = HERE / "selection.json"
FIXTURE_DIR = HERE / "fixtures"
BASELINE = HERE / "baseline.json"
CATALOG_FILES = ("ai/catalog/catalog_v2_service.json", "ai/catalog/catalog_v2_service_i3_additions.json")
CONDITIONS = ("deployed", "heldout")
RUN_FILE = re.compile(r"^(?P<stem>.+)_r(?P<run>\d+)\.json$")
UNIT_OF_LABEL = {"잔": "glass", "병": "bottle", None: None}
SCORE_KEYS = ("n_gt", "n_out", "matched_strict", "matched", "correct", "fp", "fn", "priced",
              "price_correct", "unit_confusion")
# label set -> labels, gold, photo directory under <data_dir>, recorded hybrid runs
SOURCES = {
    "val_v1_1": {"labels": "eval/labels_v1_1.json", "gold": "eval/match_gold_v1_1.json", "photo_dir": "eval_photos",
                 "runs": ("ai/runs/2026-10-14_e2e/hybrid_val_v1", "ai/runs/2026-10-14_e2e/hybrid_val_v1_rerun")},
    "test_v1_1": {"labels": "eval/labels_heldout_v1_1.json", "gold": "eval/match_gold_v1_1.json",
                  "photo_dir": "eval_photos_test", "runs": ("ai/runs/2026-10-14_e2e/hybrid_test_v1",)},
    "final": {"labels": "eval/labels_final_v1.json", "gold": "eval/match_gold_final_v1.json",
              "photo_dir": "eval_photos_final", "runs": ("ai/runs/2026-10-17_p47/hybrid_final_v1",)},
}
# Lower is better. A line whose product is not in the catalog (or is not whisky) is right when
# it stays unmatched, so "unmatched" is 0 for those kinds (severity()).
SEVERITY = {"correct": 0, "partial": 1, "ambiguous_ok": 1, "unmatched": 2, "ambiguous_bad": 3,
            "overconfident": 4, "false_merge": 4}


def read_json(rel: str | Path):
    return json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))


def dump_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


# ---- fixtures -------------------------------------------------------------------------------

def build_fixtures() -> list[dict]:
    """The fixtures as selection.json, the labels and the gold define them (nothing is read from fixtures/)."""
    fixtures = []
    for sel in read_json(SELECTION.relative_to(REPO_ROOT))["photos"]:
        src = SOURCES[sel["label_set"]]
        label = next(p for p in read_json(src["labels"])["photos"] if p["photo_id"] == sel["photo_id"])
        gold = next(p for p in read_json(src["gold"])["photos"] if p["photo_id"] == sel["photo_id"])
        if [i["raw_name"] for i in label["items"]] != [i["raw_name"] for i in gold["items"]]:
            raise SystemExit(f"{sel['photo_id']}: gold names differ from {src['labels']}")
        items = [{"raw_name": li["raw_name"], "price_krw": li["price_krw"], "pour_ml": li["pour_ml"],
                  "unit": li["unit"], "note": li.get("note"), "gold": gi["gold"]}
                 for li, gi in zip(label["items"], gold["items"])]
        fixtures.append({
            "photo_id": sel["photo_id"], "bar": label["bar"],
            "photo": {"file": sel["file"], "photo_dir": src["photo_dir"], "sha256": sel["sha256"]},
            "labels": src["labels"], "gold": src["gold"],
            "why": sel["why"], "history": sel["history"],
            "expected_items": items,
        })
    return fixtures


def fixture_path(photo_id: str) -> Path:
    return FIXTURE_DIR / f"{photo_id}.json"


def load_fixtures() -> list[dict]:
    order = [p["photo_id"] for p in read_json(SELECTION.relative_to(REPO_ROOT))["photos"]]
    return [json.loads(fixture_path(pid).read_text(encoding="utf-8")) for pid in order]


# ---- extraction replay ----------------------------------------------------------------------

def server_output(record: dict) -> dict:
    """A recorded model answer through the server code that follows the model call.

    Returns {"items": flow items sent to matching, "otherItems": non-whisky lines kept aside}.
    A prompt v2 record (prompt_version "hybrid-v2") goes through hybrid_v2.convert_output; any
    other record is prompt v1 output, which has no non-whisky lines.
    """
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.extraction import hybrid_v2
    from app.extraction.convert import to_flow_items
    from app.extraction.hybrid import HybridExtraction
    from app.extraction.schema import ExtractionItems

    raw_text = record.get("raw_text") or ""
    if record.get("prompt_version") == hybrid_v2.PROMPT_VERSION:
        out = hybrid_v2.convert_output(raw_text, record.get("ocr_lines") or [])
        return {"items": out["items"], "otherItems": out["otherItems"]}
    hybrid = HybridExtraction.model_validate_json(raw_text).model_dump()
    v1_items = [{k: v for k, v in item.items() if k != "source_lines"} for item in hybrid["items"]]
    items = ExtractionItems.model_validate({"items": to_flow_items(v1_items)}).model_dump(mode="json")["items"]
    return {"items": items, "otherItems": []}


def match_items(be, flow_items: list[dict], catalog) -> list[tuple[str, object]]:
    """What the import does after extraction (menu_import_processing._resolve_and_draft): every
    product line, and nothing else, goes to the rule matcher. Returns (name, result) per line."""
    return [(item["productName"], be.resolve(item["productName"], catalog))
            for item in flow_items if item["lineType"] == "product"]


def flatten(flow_items: list[dict]) -> list[dict]:
    """Flow items back to one row per price option, the shape of the labels. Only product lines."""
    rows = []
    for item in flow_items:
        if item["lineType"] != "product":
            continue
        options = item["options"] or [{"optionLabel": None, "pourMl": None, "priceKrw": None}]
        for o in options:
            rows.append({"raw_name": item["rawText"], "price_krw": o["priceKrw"], "pour_ml": o["pourMl"],
                         "unit": UNIT_OF_LABEL[o["optionLabel"]]})
    return rows


def duplicates(rows: list[dict]) -> int:
    """Rows that repeat an earlier row (same name, unit, pour size and price)."""
    seen, n = set(), 0
    for r in rows:
        key = (normalize(r["raw_name"]), r["unit"], r["pour_ml"], r["price_krw"])
        n += key in seen
        seen.add(key)
    return n


def score_rows(fixture: dict, rows: list[dict]) -> dict:
    s = score_photo(fixture["expected_items"], rows, fixture["photo_id"])
    errors = [{"type": e["type"], "expected": (e.get("gt") or {}).get("raw_name"),
               "got": (e.get("out") or {}).get("raw_name")}
              for e in s["errors"] if not e.get("counted_correct")]
    # score.py pairs rows by name and unit and checks the price; it never reads the pour size
    pairs, _, _ = match_photo(fixture["expected_items"], rows, lenient=True)
    pour_wrong = [(fixture["expected_items"][gi], rows[oi]) for gi, oi, _ in pairs
                  if fixture["expected_items"][gi]["pour_ml"] != rows[oi]["pour_ml"]]
    errors += [{"type": "pour size", "expected": f"{g['raw_name']} {g['pour_ml']}ml",
                "got": f"{o['raw_name']} {o['pour_ml']}ml"} for g, o in pour_wrong]
    return {**{k: s[k] for k in SCORE_KEYS}, "pour_wrong": len(pour_wrong), "duplicates": duplicates(rows),
            "errors": errors}


def record_output(record: dict) -> dict | None:
    """server_output of one run record, or None when the server would reject the answer."""
    from pydantic import ValidationError
    try:
        return server_output(record)
    except ValidationError:
        return None


def replay(fixtures: list[dict], run_dirs: dict[str, tuple[str, ...]] | None = None, run: int | None = None) -> dict:
    """record path -> score, for every recorded answer of the fixture photos."""
    out = {}
    for fx in fixtures:
        stem = Path(fx["photo"]["file"]).stem
        label_set = next(k for k, v in SOURCES.items() if v["labels"] == fx["labels"])
        for run_dir in (run_dirs or {k: v["runs"] for k, v in SOURCES.items()})[label_set]:
            for f in sorted((REPO_ROOT / run_dir).glob(f"{stem}_r*.json")):
                m = RUN_FILE.match(f.name)
                if not m or m["stem"] != stem or (run is not None and int(m["run"]) != run):
                    continue
                output = record_output(json.loads(f.read_text(encoding="utf-8")))
                items = output["items"] if output else []
                # flow_items pins the glass/bottle grouping, which flatten() undoes
                out[f"{Path(run_dir).as_posix()}/{f.name}"] = {
                    "photo_id": fx["photo_id"], "rejected": output is None, "flow_items": len(items),
                    "other_items": len(output["otherItems"]) if output else 0,
                    **score_rows(fx, flatten(items))}
    return out


# ---- matching -------------------------------------------------------------------------------

def load_seed() -> dict:
    catalogs = [read_json(rel) for rel in CATALOG_FILES]
    return {"brands": [b for c in catalogs for b in c["brands"]],
            "products": [p for c in catalogs for p in c["products"]]}


def match_lines(fixtures: list[dict], seed: dict | None = None) -> dict:
    """condition -> photo_id -> [{name, gold, kind, outcome, status, state, rank1}] for every expected line.
    `state` is the review state (app.matching.review_state): confirmed, or what the owner has to do."""
    be = harness.Backend(REPO_ROOT)
    from app.matching.linking_guards import apply_linking_guards
    from app.matching.review_state import review_state
    seed = seed or load_seed()
    out = {}
    for condition in CONDITIONS:
        catalogs = {}
        out[condition] = {}
        for fx in fixtures:
            bar = fx["bar"]
            if bar not in catalogs:
                catalogs[bar] = harness.build_catalog(be, bar if condition == "heldout" else "", "service", seed)
            bc = catalogs[bar]
            keys = {pid: key for key, pid in bc.key_to_id.items()}
            rows = []
            for name, graw in harness.label_lines(fx["expected_items"]):
                # as menu import stores it: the rules, then the guards on a confirmed line
                r = apply_linking_guards(name, be.resolve(name, bc.catalog), bc.catalog)
                g = harness.gold_for(be, graw, bc.key_to_id, dev=True)
                outcome = be.judge(g, r, bc.key_to_id, lambda ref: ref in bc.key_to_id)
                kind = ("non_whisky" if g == "non_whisky" else "unknown" if g == "unknown"
                        else "known" if all(x in bc.key_to_id for x in be.gold_refs(g)) else "absent")
                rank1 = r.proposed_product_id if r.status == "exact_match" else (
                    r.candidates[0].product_id if r.candidates else None)
                rows.append({"name": name, "gold": g, "kind": kind, "outcome": outcome, "status": r.status,
                             "state": str(review_state(r)), "rank1": keys.get(rank1)})
            out[condition][fx["photo_id"]] = rows
    return out


def severity(row: dict) -> int:
    if row["kind"] != "known" and row["outcome"] == "unmatched":
        return 0
    return SEVERITY[row["outcome"]]


def compare_matching(baseline: dict, current: dict) -> tuple[list[str], list[str]]:
    """(regressions, improvements) as readable lines. A changed line list is a regression."""
    worse, better = [], []
    for condition, photos in baseline.items():
        for pid, base_rows in photos.items():
            cur_rows = current.get(condition, {}).get(pid)
            if cur_rows is None or [r["name"] for r in cur_rows] != [r["name"] for r in base_rows]:
                worse.append(f"{condition} {pid}: the expected lines differ from the baseline (run --update)")
                continue
            for b, c in zip(base_rows, cur_rows):
                if c["kind"] != b["kind"]:
                    # e.g. known -> absent: the product left the catalog, and an unmatched line would
                    # otherwise look as right as the correct line it replaced
                    worse.append(f"{condition} {pid}: {c['name']!r} (gold {c['gold']}) was {b['kind']} and is "
                                 f"{c['kind']} now: the catalog changed (run --update if that is intended)")
                    continue
                if severity(c) == severity(b):
                    continue
                text = (f"{condition} {pid}: {c['name']!r} (gold {c['gold']}) "
                        f"{b['outcome']} -> {c['outcome']} (now {c['rank1']})")
                (worse if severity(c) > severity(b) else better).append(text)
    return worse, better


def matching_counts(rows: list[dict]) -> dict:
    known = [r for r in rows if r["kind"] == "known"]
    return {"lines": len(rows), "known": len(known),
            "known_correct": sum(r["outcome"] == "correct" for r in known),
            "false_merge": sum(r["outcome"] in ("false_merge", "overconfident") for r in rows),
            "wrong_candidates": sum(r["outcome"] == "ambiguous_bad" for r in rows)}


# ---- check ----------------------------------------------------------------------------------

def current_state(fixtures: list[dict]) -> dict:
    return {"_note": "Written by ai/regression/regression.py --update. Do not edit by hand.",
            "catalog": list(CATALOG_FILES), "extraction": replay(fixtures), "matching": match_lines(fixtures)}


def check(baseline: dict, fixtures: list[dict]) -> tuple[list[str], list[str]]:
    """(problems, improvements)."""
    problems = []
    now = replay(fixtures)
    for path in sorted(set(baseline["extraction"]) | set(now)):
        b, c = baseline["extraction"].get(path), now.get(path)
        if b != c:
            diff = "missing" if b is None or c is None else ", ".join(
                f"{k} {b[k]} -> {c[k]}" for k in b if k != "errors" and b[k] != c.get(k)) or "errors differ"
            problems.append(f"extraction replay {path}: {diff}")
    worse, better = compare_matching(baseline["matching"], match_lines(fixtures))
    return problems + worse, better


def check_photos(data_dir: Path, fixtures: list[dict]) -> list[str]:
    problems = []
    for fx in fixtures:
        path = data_dir / fx["photo"]["photo_dir"] / fx["photo"]["file"]
        if not path.is_file():
            problems.append(f"{fx['photo_id']}: {path} is missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != fx["photo"]["sha256"]:
            problems.append(f"{fx['photo_id']}: {path} is not the listed photo (SHA-256 differs)")
    return problems


def print_table(fixtures: list[dict], state: dict) -> None:
    print(f"{'photo':18} {'items':>5} {'runs':>4} {'extra':>5} {'missed':>6} {'price':>5} {'pour':>4} {'unit':>4} {'dup':>3}  "
          f"{'deployed ok/known':>17} {'heldout ok/known':>16} {'FM':>3} {'wrong':>5}")
    for fx in fixtures:
        pid = fx["photo_id"]
        recs = [r for r in state["extraction"].values() if r["photo_id"] == pid]
        dep = matching_counts(state["matching"]["deployed"][pid])
        held = matching_counts(state["matching"]["heldout"][pid])
        print(f"{pid:18} {len(fx['expected_items']):5d} {len(recs):4d} {sum(r['fp'] for r in recs):5d} "
              f"{sum(r['fn'] for r in recs):6d} {sum(r['priced'] - r['price_correct'] for r in recs):5d} "
              f"{sum(r['pour_wrong'] for r in recs):4d} "
              f"{sum(r['unit_confusion'] for r in recs):4d} {sum(r['duplicates'] for r in recs):3d}  "
              f"{dep['known_correct']:>8d}/{dep['known']:<8d} {held['known_correct']:>7d}/{held['known']:<8d} "
              f"{dep['false_merge'] + held['false_merge']:3d} {dep['wrong_candidates'] + held['wrong_candidates']:5d}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--update", action="store_true", help="rewrite fixtures/ and baseline.json")
    ap.add_argument("--extraction", type=Path, help="score the records of a new extraction run directory")
    ap.add_argument("--run", type=int, help="run number for --extraction (default: every run)")
    ap.add_argument("--check-photos", type=Path, metavar="DATA_DIR", help="compare local photos with the listed SHA-256")
    args = ap.parse_args(argv)

    if args.update:
        FIXTURE_DIR.mkdir(exist_ok=True)
        fixtures = build_fixtures()
        for fx in fixtures:
            fixture_path(fx["photo_id"]).write_text(dump_json(fx), encoding="utf-8")
        state = current_state(fixtures)
        BASELINE.write_text(dump_json(state), encoding="utf-8")
        print_table(fixtures, state)
        print(f"wrote {len(fixtures)} fixtures and {BASELINE.relative_to(REPO_ROOT)}")
        return 0

    fixtures = load_fixtures()
    if args.check_photos:
        problems = check_photos(args.check_photos, fixtures)
        print("\n".join(problems) or f"{len(fixtures)} photos match")
        return 1 if problems else 0
    if args.extraction:
        run_dir = args.extraction.resolve()
        scores = replay(fixtures, {k: (str(run_dir),) for k in SOURCES}, args.run)
        for path, s in scores.items():
            print(f"{s['photo_id']:18} {Path(path).name:28} out {s['n_out']:3d} correct {s['correct']:3d}/{s['n_gt']:<3d} "
                  f"extra {s['fp']:2d} missed {s['fn']:2d} price {s['priced'] - s['price_correct']:2d} "
                  f"pour {s['pour_wrong']:2d} unit {s['unit_confusion']:2d} dup {s['duplicates']:2d} "
                  f"other {s['other_items']:2d}{'  REJECTED' if s['rejected'] else ''}")
        found = {s["photo_id"] for s in scores.values()}
        missing = [fx["photo_id"] for fx in fixtures if fx["photo_id"] not in found]
        if missing:
            print("no record for: " + ", ".join(missing))
        return 0

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    problems, better = check(baseline, fixtures)
    print_table(fixtures, current_state(fixtures))
    for line in better:
        print("better: " + line)
    for line in problems:
        print("REGRESSION: " + line)
    if better and not problems:
        print("Some lines improved. Run --update to protect them.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
