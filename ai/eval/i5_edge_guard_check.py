"""I5-P19 facing-page guard: what does the server's guard drop from the recorded answers? No API call.

    python ai/eval/i5_edge_guard_check.py --out ai/runs/2026-11-27_i5_pr_prep/edge_guard_check.json

The guard (backend/app/extraction/edge_guard.py, EXTRACTION_EDGE_STRIP_PERMILLE, default 100)
drops a whisky line without a price (a glass/bottle mark or a pour size alone does not count) whose OCR name
lines lie wholly in the left or right strip of the photo (0-1000 scale). This script runs that
very function on the recorded answers made with hybrid prompt v2.1, the way the server does:

  1. the OCR line table is rebuilt from the CLOVA cache, as the server builds it (boxes 0-1000);
  2. the model's answer goes through hybrid_v2.convert_output (the server's conversion);
  3. edge_guard.drop_edge_rows takes the whisky items and the meta.

Every whisky line without a price is sorted into one of three kinds:

  neighbour  one of the 12 lines of the page next to 011_mirabeau_03 (2026-11-21 report 10.6)
  label      the photo's labels have an item of that name (a line of this menu)
  other      neither

and the expectation of the PR prep handoff is checked: every neighbour line dropped, no label line
dropped, nothing else dropped, and the 17 regression photos read through the server code
(2026-11-25_i5_p19_server_route) scoring the same after the guard (572 of 572). The script exits 1
when any of these differs. It also prints what a strip of 0, 50, 100, 150 and 200 would drop, for
the report; the strip is not chosen from this.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in ("ai/regression", "ai/eval", "ai/extract", "backend"):
    sys.path.insert(0, str(REPO_ROOT / _p))

import i5_model_ladder as ladder  # noqa: E402
import run_extraction as rx  # noqa: E402
import score  # noqa: E402
from app.extraction.edge_guard import DEFAULT_STRIP_PERMILLE, drop_edge_rows, has_price  # noqa: E402
from app.extraction.hybrid import run_ocr  # noqa: E402
from app.extraction.hybrid_v2 import WHISKY, convert_output, line_groups  # noqa: E402

RUNS = REPO_ROOT / "ai" / "runs"
SERVER_SET = "3.8 Flash, 서버 코드 (11/25)"
# name, folder, glob, how to get the model's answer out of a record
SETS = (
    ("3.8 Flash, 평가 스크립트 (11/21)", RUNS / "2026-11-21_i5_row_pairing/regression_38flash_v2_1/google__gemini-3.8-flash/B", "*_r*.json", "raw_text"),
    (SERVER_SET, RUNS / "2026-11-25_i5_p19_server_route", "0*.json", "meta"),
    ("3.8 Flash, 동시 호출 (11/26)", RUNS / "2026-11-26_i5_a2_p43/concurrent", "0*.json", "meta"),
    ("Sonnet 5.5, 회귀 17장 (11/26)", RUNS / "2026-11-26_i5_p19_followup/regression_sonnet/anthropic__claude-sonnet-5.5/B", "*_r*.json", "raw_text"),
    ("3.7 Flash, 6장 (11/25)", RUNS / "2026-11-25_i5_fallback_ladder/google__gemini-3.7-flash/B", "*_r*.json", "raw_text"),
    ("GPT-6.1 Terra, 6장 (11/25)", RUNS / "2026-11-25_i5_fallback_ladder/openai__gpt-6.1-terra/B", "*_r*.json", "raw_text"),
    ("Sonnet 5.5, 6장 (11/25)", RUNS / "2026-11-25_i5_fallback_ladder/anthropic__claude-sonnet-5.5/B", "*_r*.json", "raw_text"),
)
NEIGHBOUR_PHOTO = "011_mirabeau_03"
NEIGHBOUR_NAMES = ("하이랜드 파크 12년", "하이랜드 파크 캐스크 스트", "하이랜드 파크 5년", "하이랜드 파크 18년",
                   "하이랜드 파크 16년", "글렌킨 12년", "오큰토 아메", "오큰토 12년", "오큰토 쇼비", "오큰토 쓰러", "오큰토 18")
STRIPS = (0, 50, 100, 150, 200)
EXPECTED = {"neighbour": (60, 60), "label": (0, 7), "other_dropped": 0, "server_score": (572, 572)}
SCORE_KEYS = ("ok", "wrong", "missing", "name_only", "extra")


def answer_text(record: dict, how: str) -> str | None:
    if how == "meta":
        raw = (record.get("meta") or {}).get("rawOutput")
        return json.dumps(raw, ensure_ascii=False) if raw else None
    return record.get("raw_text") or None


def stem_of(path: Path) -> str:
    return path.stem.rsplit("_r", 1)[0] if "_r" in path.stem[-4:] else path.stem


def kept_rows(text: str, dropped_orders: set[int]) -> list[dict]:
    """The scored whisky rows (i5_model_ladder.parse_rows format) of the lines the guard kept.

    convert_output numbers the whisky items in the order of the whisky line groups, so item k is
    group k; a dropped item's rows are left out."""
    groups = [g for g in line_groups(json.loads(text)["items"]) if g[0]["category"] == WHISKY]
    return [{k: row[k] for k in ("raw_name", "price_krw", "pour_ml", "unit")}
            for order, group in enumerate(groups, start=1) if order not in dropped_orders for row in group]


def main(argv=None) -> int:
    from extract import data_dir as default_data_dir
    import i5_row_pairing
    import i5_server_route_regression as server_route
    import regression
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    data_dir = default_data_dir()
    fixtures = i5_row_pairing.known_photos(data_dir)
    ladder.FIXTURES = fixtures
    ladder.PHOTOS = tuple((Path(fx["photo"]["file"]).stem, "regression") for fx in regression.load_fixtures()) + server_route.EXTRA_PHOTOS
    score_labels = ladder.load_labels()
    tables: dict[str, list[dict]] = {}
    labels: dict[str, set[str]] = {}

    def table(stem: str) -> list[dict]:
        if stem not in tables:
            photo = fixtures[stem]["photo"]
            path = data_dir / photo["photo_dir"] / photo["file"]
            cache = json.loads((data_dir / "ocr_cache" / f"{path.stem}__table-off.json").read_text(encoding="utf-8"))
            tables[stem] = run_ocr(path.read_bytes(), rx.MIME_TYPES[path.suffix.lower()], rx.REPLAY_CLOVA, rx.ReplayOcr(cache))["table"]
        return tables[stem]

    def label_names(stem: str) -> set[str]:
        if stem not in labels:
            fixture = fixtures[stem]
            if "expected_items" in fixture:
                items = fixture["expected_items"]
            else:
                found = [score.load_labels(name).get(fixture["photo_id"]) for name in ("i3", "val_v1_1", "test_v1_1")]
                items = next(x for x in found if x)
            labels[stem] = {score.normalize(item["raw_name"]) for item in items}
        return labels[stem]

    report = {"strip_permille": DEFAULT_STRIP_PERMILLE, "sets": {}, "rows": [], "by_strip": {}}
    server = {"before": Counter(), "after": Counter()}
    for name, folder, pattern, how in SETS:
        records = whisky_rows = whisky_items = without_price = 0
        for path in sorted(folder.glob(pattern)):
            if path.name == "summary.json":
                continue
            text = answer_text(json.loads(path.read_text(encoding="utf-8")), how)
            if text is None:
                continue
            records += 1
            stem = stem_of(path)
            whisky_rows += sum(1 for row in json.loads(text)["items"] if row["category"] == WHISKY)
            converted = convert_output(text, table(stem))
            whisky_items += len(converted["items"])
            meta = {"itemSources": converted["itemSources"], "ocr": {"lines": table(stem)}}
            by_strip = {strip: {row["itemOrder"]: row for row in drop_edge_rows(converted["items"], meta, strip)[1]["droppedEdgeRows"]}
                        for strip in STRIPS}
            # every dropped line has no price (the guard's rule), so every one is among these rows
            sources = {s["itemOrder"]: s for s in converted["itemSources"]}
            for item in converted["items"]:
                if has_price(item):
                    continue
                without_price += 1
                if stem == NEIGHBOUR_PHOTO and item["rawText"] in NEIGHBOUR_NAMES:
                    kind = "neighbour"
                elif score.normalize(item["rawText"]) in label_names(stem):
                    kind = "label"
                else:
                    kind = "other"
                source = sources[item["itemOrder"]]
                report["rows"].append({
                    "set": name, "record": path.name, "photo": stem, "name": item["rawText"], "kind": kind,
                    "nameLines": source["nameLines"], "priceLines": source["priceLines"], "box": source["box"],
                    "dropped": {strip: item["itemOrder"] in by_strip[strip] for strip in STRIPS},
                })
            if name == SERVER_SET:
                labels_of = score_labels[stem]
                for when, dropped in (("before", set()), ("after", set(by_strip[DEFAULT_STRIP_PERMILLE]))):
                    s = ladder.score_rows(labels_of, kept_rows(text, dropped))
                    for key in SCORE_KEYS:
                        server[when][key] += s[key]
                    server[when]["cells"] += sum(score.price_checked(g) for g in labels_of)
        report["sets"][name] = {"records": records, "whisky_rows": whisky_rows, "whisky_items": whisky_items,
                                "items_without_price": without_price}
    report["server_score"] = {when: dict(c) for when, c in server.items()}

    print("| 기록 묶음 | 기록 | 위스키 행 (모델) | 위스키 줄 (서버 변환) | 가격 없는 줄 | 옆 페이지 | 정답에 있음 | 그 밖 |")
    print("|---|---|---|---|---|---|---|---|")
    for name, info in report["sets"].items():
        kinds = Counter(row["kind"] for row in report["rows"] if row["set"] == name)
        print(f"| {name} | {info['records']} | {info['whisky_rows']:,} | {info['whisky_items']:,} | {info['items_without_price']} | "
              f"{kinds['neighbour']} | {kinds['label']} | {kinds['other']} |")
    totals = Counter(row["kind"] for row in report["rows"])
    print(f"\ntotal: records {sum(s['records'] for s in report['sets'].values())}, whisky rows "
          f"{sum(s['whisky_rows'] for s in report['sets'].values()):,}, lines without a price {len(report['rows'])} {dict(totals)}")
    print("\n| 띠 너비 (0~1000 눈금) | 옆 페이지 줄 중 버려짐 | 정답에 있는 줄 중 버려짐 | 그 밖의 줄 중 버려짐 |")
    print("|---|---|---|---|")
    for strip in STRIPS:
        dropped = Counter(row["kind"] for row in report["rows"] if row["dropped"][strip])
        report["by_strip"][strip] = dict(dropped)
        mark = " (기본값)" if strip == DEFAULT_STRIP_PERMILLE else ""
        print(f"| {strip}{mark} | {dropped['neighbour']} / {totals['neighbour']} | {dropped['label']} / {totals['label']} | "
              f"{dropped['other']} / {totals['other']} |")

    print(f"\nlines without a price (strip {DEFAULT_STRIP_PERMILLE}):")
    seen = Counter((row["set"], row["photo"], row["name"], row["kind"], str(row["box"]), str(row["priceLines"]),
                    row["dropped"][DEFAULT_STRIP_PERMILLE]) for row in report["rows"])
    for (set_name, photo, row_name, kind, box, price_lines, dropped), n in sorted(seen.items()):
        print(f"  {set_name} | {photo} | {row_name} | {kind} | box {box} price lines {price_lines} | "
              f"{'DROPPED' if dropped else 'kept'} | x{n}")

    s = report["server_score"]
    print(f"\nserver-code set: before {s['before']}, after {s['after']}")

    at = report["by_strip"][DEFAULT_STRIP_PERMILLE]
    got = {"neighbour": (at.get("neighbour", 0), totals["neighbour"]), "label": (at.get("label", 0), totals["label"]),
           "other_dropped": at.get("other", 0), "server_score": (s["after"]["ok"], s["after"]["cells"])}
    problems = [f"{key}: expected {EXPECTED[key]}, got {got[key]}" for key in EXPECTED if got[key] != EXPECTED[key]]
    if s["after"] != s["before"]:
        problems.append(f"server_score changed: {s['before']} -> {s['after']}")
    report["expected"], report["got"], report["problems"] = EXPECTED, got, problems
    print("\nexpectation:", "MET" if not problems else "NOT MET")
    for problem in problems:
        print("  " + problem)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
