"""I5-P19 follow-up F: would "drop a whisky line without a price whose OCR box touches the photo's
edge" catch the neighbour-page lines of 011_mirabeau_03, and what else would it drop? No API call.

    python ai/eval/i5_edge_guard_check.py --out ai/runs/2026-11-26_i5_p19_followup/edge_guard.json

Reads the recorded answers made with hybrid prompt v2.1 (each has the model's rows with their OCR
`source_lines`) and the OCR line table the server builds from the CLOVA cache (boxes on a 0-1000
scale of the photo, as in `raw_output.ocr.lines`). For every whisky row without a price:

  box      the union of the boxes of its name lines (the server's `itemSources[].box` also adds the
           price lines; a row without a price has none)
  touches  the box reaches within MARGIN of the left, right, top or bottom edge
  kind     neighbour  one of the 12 lines of the page next to 011_mirabeau_03 (report 10.6)
           label      the photo's labels have an item of that name (a line of this menu)
           other      neither

The rule drops a row when it has no price and `touches`. It is a proposal: nothing in the server
does this.
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
from app.extraction.hybrid import run_ocr  # noqa: E402

RUNS = REPO_ROOT / "ai" / "runs"
# name, folder, glob, how to get the model's items out of a record
SETS = (
    ("3.8 Flash, 평가 스크립트 (11/21)", RUNS / "2026-11-21_i5_row_pairing/regression_38flash_v2_1/google__gemini-3.8-flash/B", "*_r*.json", "raw_text"),
    ("3.8 Flash, 서버 코드 (11/25)", RUNS / "2026-11-25_i5_p19_server_route", "0*.json", "meta"),
    ("3.8 Flash, 동시 호출 (11/26)", RUNS / "2026-11-26_i5_a2_p43/concurrent", "0*.json", "meta"),
    ("Sonnet 5.5, 회귀 17장 (11/26)", RUNS / "2026-11-26_i5_p19_followup/regression_sonnet/anthropic__claude-sonnet-5.5/B", "*_r*.json", "raw_text"),
    ("3.7 Flash, 6장 (11/25)", RUNS / "2026-11-25_i5_fallback_ladder/google__gemini-3.7-flash/B", "*_r*.json", "raw_text"),
    ("GPT-6.1 Terra, 6장 (11/25)", RUNS / "2026-11-25_i5_fallback_ladder/openai__gpt-6.1-terra/B", "*_r*.json", "raw_text"),
    ("Sonnet 5.5, 6장 (11/25)", RUNS / "2026-11-25_i5_fallback_ladder/anthropic__claude-sonnet-5.5/B", "*_r*.json", "raw_text"),
)
NEIGHBOUR_PHOTO = "011_mirabeau_03"
NEIGHBOUR_NAMES = ("하이랜드 파크 12년", "하이랜드 파크 캐스크 스트", "하이랜드 파크 5년", "하이랜드 파크 18년",
                   "하이랜드 파크 16년", "글렌킨 12년", "오큰토 아메", "오큰토 12년", "오큰토 쇼비", "오큰토 쓰러", "오큰토 18")
MARGINS = (0, 5, 10, 20, 30)
SIDES = ("left", "top", "right", "bottom")


def items_of(record: dict, how: str) -> list[dict] | None:
    if how == "meta":
        raw = (record.get("meta") or {}).get("rawOutput")
        return raw["items"] if raw else None
    return json.loads(record["raw_text"])["items"] if record.get("raw_text") else None


def stem_of(path: Path) -> str:
    return path.stem.rsplit("_r", 1)[0] if "_r" in path.stem[-4:] else path.stem


def sides_touched(box: list[int], margin: int) -> list[str]:
    x0, y0, x1, y1 = box
    return [side for side, near in zip(SIDES, (x0 <= margin, y0 <= margin, x1 >= 1000 - margin, y1 >= 1000 - margin)) if near]


def main(argv=None) -> int:
    from extract import data_dir as default_data_dir
    import i5_row_pairing
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    data_dir = default_data_dir()
    fixtures = i5_row_pairing.known_photos(data_dir)
    tables: dict[str, dict] = {}
    labels: dict[str, set[str]] = {}

    def table(stem: str) -> dict:
        if stem not in tables:
            photo = fixtures[stem]["photo"]
            path = data_dir / photo["photo_dir"] / photo["file"]
            cache = json.loads((data_dir / "ocr_cache" / f"{path.stem}__table-off.json").read_text(encoding="utf-8"))
            ocr = run_ocr(path.read_bytes(), rx.MIME_TYPES[path.suffix.lower()], rx.REPLAY_CLOVA, rx.ReplayOcr(cache))
            tables[stem] = {row["id"]: row["box"] for row in ocr["table"]}
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

    report = {"sets": {}, "rows": []}
    for name, folder, pattern, how in SETS:
        paths = sorted(folder.glob(pattern))
        records = whisky = no_price = 0
        for path in paths:
            if path.name == "summary.json":
                continue
            items = items_of(json.loads(path.read_text(encoding="utf-8")), how)
            if items is None:
                continue
            records += 1
            stem = stem_of(path)
            boxes = table(stem)
            for item in items:
                if item.get("category", "whisky") != "whisky":
                    continue
                whisky += 1
                if item["price_krw"] is not None:
                    continue
                no_price += 1
                lines = [boxes[i] for i in item["source_lines"]["name"] if i in boxes]
                box = [min(b[0] for b in lines), min(b[1] for b in lines), max(b[2] for b in lines), max(b[3] for b in lines)] if lines else None
                if stem == NEIGHBOUR_PHOTO and item["raw_name"] in NEIGHBOUR_NAMES:
                    kind = "neighbour"
                elif score.normalize(item["raw_name"]) in label_names(stem):
                    kind = "label"
                else:
                    kind = "other"
                report["rows"].append({"set": name, "record": path.name, "photo": stem, "name": item["raw_name"],
                                       "unit": item["unit"], "kind": kind, "box": box,
                                       "touches": {m: sides_touched(box, m) if box else [] for m in MARGINS}})
        report["sets"][name] = {"records": records, "whisky_rows": whisky, "rows_without_price": no_price}

    print("| 기록 묶음 | 기록 | 위스키 행 | 가격 없는 행 | 그중 옆 페이지 줄 | 정답에 있는 줄 | 그 밖 |")
    print("|---|---|---|---|---|---|---|")
    for name, info in report["sets"].items():
        kinds = Counter(row["kind"] for row in report["rows"] if row["set"] == name)
        print(f"| {name} | {info['records']} | {info['whisky_rows']} | {info['rows_without_price']} | {kinds['neighbour']} | {kinds['label']} | {kinds['other']} |")
    print("\n| 가장자리 여유 (0~1000 눈금) | 옆 페이지 줄 중 버려짐 | 정답에 있는 줄 중 버려짐 | 그 밖의 줄 중 버려짐 |")
    print("|---|---|---|---|")
    totals = Counter(row["kind"] for row in report["rows"])
    report["by_margin"] = {}
    for margin in MARGINS:
        dropped = Counter(row["kind"] for row in report["rows"] if row["touches"][margin])
        report["by_margin"][margin] = dict(dropped)
        print(f"| {margin} | {dropped['neighbour']} / {totals['neighbour']} | {dropped['label']} / {totals['label']} | {dropped['other']} / {totals['other']} |")
    print("\nneighbour rows: right edge x1 values", sorted({row["box"][2] for row in report["rows"] if row["kind"] == "neighbour" and row["box"]}),
          "| without a box:", sum(1 for row in report["rows"] if row["kind"] == "neighbour" and not row["box"]))
    print("\nrows without a price that are not neighbour-page lines:")
    seen = Counter((row["set"], row["photo"], row["name"], row["kind"], str(row["box"]), str(row["touches"][10])) for row in report["rows"] if row["kind"] != "neighbour")
    for (set_name, photo, row_name, kind, box, touch), n in sorted(seen.items()):
        print(f"  {set_name} | {photo} | {row_name} | {kind} | box {box} | touches(10) {touch} | x{n}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
