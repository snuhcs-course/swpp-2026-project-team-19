"""I5-P19: does claude-sonnet-5.5 write the bottle prices of 007_bokchun_03 at a tenth every time?

    python ai/eval/i5_sonnet_bokchun03_repeat.py --out ai/runs/2026-11-27_i5_pr_prep/sonnet_bokchun03 --check
    python ai/eval/i5_sonnet_bokchun03_repeat.py --out ai/runs/2026-11-27_i5_pr_prep/sonnet_bokchun03
    python ai/eval/i5_sonnet_bokchun03_repeat.py --out ai/runs/2026-11-27_i5_pr_prep/sonnet_bokchun03 --report

On 2026-11-26 (row_pairing report section 12, follow-up report E) Sonnet 5.5 wrote all six bottle
prices of this photo at a tenth, in one run. This makes runs 2, 3 and 4 of that photo with the
11/26 request: i5_model_ladder stage 3 (`anthropic/claude-sonnet-5.5` through OpenRouter,
`reasoning.effort` medium), condition B (the photo and its OCR lines, answered from the CLOVA
cache: no CLOVA call), hybrid prompt v2.1, `max_tokens` 48000, the regression fixture's labels.
The request is `i5_model_ladder.call_openrouter` and the inputs `i5_model_ladder.inputs`, the
functions that made the 11/26 record; this script checks that the prompt, the prepared image and
the number of OCR lines are those of the 11/26 record before calling.

Unlike i5_model_ladder.run_one, a call is never tried again: a call without an answer or with an
answer outside the schema is recorded as it is and counts as a run without a result.

Spending: COST_LIMIT_USD for the three calls. Before each call the cost of the records plus
CALL_BOUND_USD must stay within it, and the command stops after a call that cost more than
CALL_BOUND_USD. CALL_BOUND_USD is about four times what the 11/26 call of this photo cost
($0.039); the most a call could cost at the 48,000-token cap is about $0.54, which no Sonnet call of
the 11/26 Sonnet calls came near (the most of the 17: $0.088).

`--report` scores runs 1 (11/26) to 4 with i5_model_ladder.score_rows (the 11/26 function) and lists
the six bottle cells of each run next to the gemini-3.8-flash records of the same photo (server code
11/25, concurrent imports 11/26). The verdict rule is in ai/runs/2026-11-27_i5_pr_prep/report.md H.1,
committed before the first call.

The API key is read from the repo .env and is never printed or written.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in ("ai/regression", "ai/eval", "ai/extract", "backend"):
    sys.path.insert(0, str(REPO_ROOT / _p))

import i5_model_ladder as ladder  # noqa: E402
import score  # noqa: E402
from pydantic import ValidationError  # noqa: E402

STEM = "007_bokchun_03"
RUNS = (2, 3, 4)
PROMPT = REPO_ROOT / "backend" / "app" / "extraction" / "hybrid_prompt_v2_1.md"
MAX_TOKENS = 48000
COST_LIMIT_USD = 0.5
CALL_BOUND_USD = 0.15
RUNS_1126 = REPO_ROOT / "ai" / "runs" / "2026-11-26_i5_p19_followup" / "regression_sonnet" / "anthropic__claude-sonnet-5.5" / "B"
FLASH = {
    "3.8 Flash, 서버 코드 (11/25)": REPO_ROOT / "ai" / "runs" / "2026-11-25_i5_p19_server_route" / f"{STEM}.json",
    "3.8 Flash, 동시 호출 (11/26)": REPO_ROOT / "ai" / "runs" / "2026-11-26_i5_a2_p43" / "concurrent" / f"{STEM}.json",
}


def setup(data_dir: Path) -> tuple[dict, list[dict]]:
    """i5_model_ladder's globals as `--photos regression --prompt-b <v2.1>` sets them; the fixture and labels."""
    import i5_row_pairing
    import regression
    ladder.PROMPT_B = PROMPT.resolve()
    ladder.FIXTURES = i5_row_pairing.known_photos(data_dir)
    ladder.PHOTOS = tuple((Path(fx["photo"]["file"]).stem, "regression") for fx in regression.load_fixtures()) + (
        ("007_bokchun_02", "val_v1_1"), ("012_beck_04", "test_v1_1"))
    return ladder.FIXTURES[STEM], ladder.load_labels()[STEM]


def same_inputs(sent: dict) -> list[str]:
    """What differs from the 11/26 record's request."""
    old = json.loads((RUNS_1126 / f"{STEM}_r1.json").read_text(encoding="utf-8"))
    return [f"{key}: 11/26 {old[key]!r}, now {now!r}" for key, now in (
        ("prompt_sha256", sent["prompt_sha256"]), ("image_sha256", sent["image_sha256"]),
        ("ocr_lines_sent", sent["ocr_lines"]), ("prompt_file", sent["prompt_file"])) if old[key] != now]


def call_once(stage: dict, fixture: dict, sent: dict, key: str, run: int) -> dict:
    """One call, no retry; the record has the fields of i5_model_ladder.run_one."""
    record = {"model": stage["model"], "route": stage["route"], "reasoning": stage["thinking"], "condition": "B",
              "photo_id": fixture["photo_id"], "source_image": fixture["photo"]["file"],
              "prompt_file": sent["prompt_file"], "prompt_sha256": sent["prompt_sha256"],
              "image_sha256": sent["image_sha256"], "ocr_lines_sent": sent["ocr_lines"], "format_retry": False,
              "failures": [], "run": run, "max_tokens": stage["max_tokens"], "retries": "none",
              "started_at": datetime.now(timezone.utc).isoformat(), "attempts": 1, "rows": None, "raw_text": None}
    try:
        answer = ladder.call_openrouter(stage, sent, key)
    except ladder.TransportError as error:
        record["failures"].append({"attempt": 1, "kind": "transport", "detail": str(error).replace(key, "***")[:300]})
        return record
    text = answer.pop("text")
    record.update(raw_text=text, **answer)
    try:
        if answer["status"] != "completed":
            raise ValueError(f"status {answer['status']}")
        record["rows"] = ladder.parse_rows(sent, "B", text)
    except (ValidationError, ValueError) as error:
        record["failures"].append({"attempt": 1, "kind": "format", "detail": str(error)[:300]})
    return record


def spent(out: Path) -> float:
    return sum(json.loads(p.read_text(encoding="utf-8")).get("cost_usd") or 0 for p in out.glob(f"{STEM}_r*.json"))


def bottle_cells(labels: list[dict], rows: list[dict] | None) -> list[dict]:
    """The bottle label items of the photo and the price of the row score.py pairs with each."""
    pairs = {gi: oi for gi, oi, _ in score.match_photo(labels, rows, lenient=True)[0]} if rows else {}
    return [{"name": g["raw_name"], "label": g["price_krw"],
             "got": rows[pairs[gi]]["price_krw"] if gi in pairs else None}
            for gi, g in enumerate(labels) if g["unit"] == "bottle" and score.price_checked(g)]


def report(out: Path, labels: list[dict]) -> dict:
    sonnet = {1: RUNS_1126 / f"{STEM}_r1.json", **{run: out / f"{STEM}_r{run}.json" for run in RUNS}}
    result = {"runs": {}, "flash": {}}
    print("| 회차 | 날짜 | 맞음 / 틀림 / 누락 (16칸) | 병 6칸 중 1/10 | 청구액 | 지연 | 추론 토큰 | 제공자 |")
    print("|---|---|---|---|---|---|---|---|")
    for run, path in sonnet.items():
        if not path.exists():
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        rows = rec.get("rows")
        s = ladder.score_rows(labels, rows) if rows is not None else None
        bottles = bottle_cells(labels, rows)
        tenth = sum(1 for b in bottles if b["got"] is not None and b["got"] * 10 == b["label"])
        result["runs"][run] = {"score": s, "bottles": bottles, "tenth": tenth, "cost_usd": rec.get("cost_usd"),
                               "latency_ms": rec.get("latency_ms"), "thought_tokens": rec.get("thought_tokens"),
                               "provider": rec.get("provider"), "failures": rec.get("failures"),
                               "date": rec["started_at"][:10]}
        cell = "답 없음/형식 실패" if s is None else f"{s['ok']} / {s['wrong']} / {s['missing']}"
        print(f"| r{run} | {rec['started_at'][:10]} | {cell} | {tenth} / {len(bottles)} | ${rec.get('cost_usd') or 0:.4f} | "
              f"{(rec.get('latency_ms') or 0) / 1000:.1f}초 | {rec.get('thought_tokens')} | {rec.get('provider')} |")
    for name, path in FLASH.items():
        rec = json.loads(path.read_text(encoding="utf-8"))
        s = ladder.score_rows(labels, rec["rows"])
        result["flash"][name] = {"score": s, "bottles": bottle_cells(labels, rec["rows"])}
        print(f"| {name} | – | {s['ok']} / {s['wrong']} / {s['missing']} | – | ${rec['cost_usd']:.4f} | "
              f"{rec['meta']['latencyMs'] / 1000:.1f}초 | {rec['meta'].get('thoughtTokens')} | {rec['meta']['route']['provider']} |")

    names = [b["name"] for b in bottle_cells(labels, None)]
    columns = [f"Sonnet r{run}" for run in result["runs"]] + list(result["flash"])
    print("\n| 이름 | 정답 병 가격 | " + " | ".join(columns) + " |")
    print("|---|---|" + "---|" * len(columns))
    for i, name in enumerate(names):
        label = bottle_cells(labels, None)[i]["label"]
        got = [r["bottles"][i]["got"] for r in result["runs"].values()] + [f["bottles"][i]["got"] for f in result["flash"].values()]
        print(f"| {name} | {label:,} | " + " | ".join("–" if g is None else f"{g:,}" for g in got) + " |")

    new_runs = [run for run in RUNS if run in result["runs"]]
    counted = sum(1 for run in new_runs if result["runs"][run]["tenth"] == 6)
    if len(new_runs) == len(RUNS) and all(result["runs"][run]["score"] is not None for run in new_runs):
        verdict = {3: "이 사진에서 재현되는 약점", 0: "11/26은 한 번의 결과"}.get(counted, "흔들림")
    else:
        verdict = "판정 없음 (답이 없거나 형식이 틀린 회차가 있음)"
    result["counted"], result["verdict"] = counted, verdict
    print(f"\n새 3회 중 병 가격 6칸이 모두 1/10인 회차: {counted} -> {verdict}")
    print(f"spent on the new runs: ${spent(out):.4f}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_bytes(json.dumps(result, ensure_ascii=False, indent=1, default=str).encode("utf-8"))
    return result


def main(argv=None) -> int:
    from dotenv import dotenv_values
    from extract import data_dir as default_data_dir
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--check", action="store_true", help="check the inputs against the 11/26 record; no API call")
    ap.add_argument("--report", action="store_true", help="score the records; no API call")
    args = ap.parse_args(argv)
    data_dir = default_data_dir()
    fixture, labels = setup(data_dir)
    if args.report:
        report(args.out, labels)
        return 0
    sent = ladder.inputs(fixture, "B", data_dir)
    differs = same_inputs(sent)
    todo = [run for run in RUNS if not (args.out / f"{STEM}_r{run}.json").exists()]
    print(f"{STEM}: prompt {sent['prompt_sha256'][:12]}, image {sent['image_sha256'][:12]}, OCR lines {sent['ocr_lines']}; "
          f"calls to make {len(todo)}; limit ${COST_LIMIT_USD}, per-call bound ${CALL_BOUND_USD}")
    if differs:
        raise SystemExit("the inputs differ from the 11/26 record: " + "; ".join(differs))
    if args.check:
        return 0
    key = (dotenv_values(REPO_ROOT / ".env").get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set in the repo .env")
    stage = {**ladder.STAGES[3], "max_tokens": MAX_TOKENS}
    args.out.mkdir(parents=True, exist_ok=True)
    for n, run in enumerate(todo):
        if spent(args.out) + CALL_BOUND_USD > COST_LIMIT_USD:
            print(f"stopped before r{run}: the records cost ${spent(args.out):.4f}")
            return 1
        if n:
            time.sleep(ladder.MIN_INTERVAL_S)
        record = call_once(stage, fixture, sent, key, run)
        (args.out / f"{STEM}_r{run}.json").write_bytes(json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"))
        rows = "NO RESULT " + record["failures"][0]["kind"] if record["rows"] is None else f"rows {len(record['rows'])}"
        print(f"r{run} {rows} {(record.get('latency_ms') or 0) / 1000:.1f}s ${record.get('cost_usd')} "
              f"thought {record.get('thought_tokens')} provider {record.get('provider')}", flush=True)
        if (record.get("cost_usd") or 0) > CALL_BOUND_USD:
            print(f"stopped: r{run} cost more than ${CALL_BOUND_USD}")
            return 1
    report(args.out, labels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
