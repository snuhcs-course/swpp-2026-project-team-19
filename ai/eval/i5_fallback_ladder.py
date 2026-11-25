"""I5-P18: which OpenRouter models may stand in for gemini-3.8-flash when it fails?

    python ai/eval/i5_fallback_ladder.py --out ai/runs/2026-11-25_i5_fallback_ladder --check
    python ai/eval/i5_fallback_ladder.py --out ai/runs/2026-11-25_i5_fallback_ladder
    python ai/eval/i5_fallback_ladder.py --out ai/runs/2026-11-25_i5_fallback_ladder --report

The plan (photos, condition, pass criterion) is ai/runs/2026-11-25_i5_fallback_ladder/preregistration.md,
committed before the first call. This file is that plan as code; the constants below are not
changed after a result is seen.

Three candidate models, six photos, three runs each: 18 calls a model, 54 in all. One condition:
the photo and its OCR lines (condition B of i5_model_ladder.py), hybrid_prompt_v2_1.md,
`reasoning.effort` medium, `max_tokens` 48000. The request is i5_model_ladder.call_openrouter, so
it is the request the 2026-11-21 gemini-3.8-flash records were made with
(`provider: {data_collection: deny, require_parameters: true}`, strict json_schema). The prompt is
the same text for every model. OCR comes from the cache; no CLOVA call.

Records go to <out>/<model>/B/<stem>_r<run>.json; an existing record is kept, so a command that
stopped continues with the same command. A call is tried again once when it gets no answer or its
answer is cut (`finish_reason: length`) or is not the schema; a wrong price is never retried.

Spending guard: before each call, the cost of the model's records plus the most one more call can
cost (two attempts, each INPUT_TOKENS_BOUND in and `max_tokens` out, at the list price) must stay
within MODEL_COST_LIMIT_USD, and the same over all models within TOTAL_COST_LIMIT_USD. Otherwise
the command stops and says so.

Pass criterion of a model (the worst of its 18 runs decides):
  1. all 18 runs have an answer in the schema
  2. no run has a wrong price
  3. no run misses more than 5% of the photo's priced label items
  4. on 011_mirabeau_02, each of the 20 lines under a bottler title has the title in its name, in
     all three runs
Scoring is i5_model_ladder.score_rows (report section 8.3). The 20 lines are the ones recorded in
ai/runs/2026-11-21_i5_row_pairing/regression_38flash_v2_1/check.json (report section 10.4). The
output row of a line is the row score.py pairs with it, or else the left-over row of the same unit
and price whose name shares the longest ending with it, at least 3 characters (the rule of
i5_title_fix_check.output_names, copied here). The title is the label name up to its first ")",
and it is in the name when the normalized name contains the normalized title.

The API key is read from the repo .env and is never printed or written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in ("ai/regression", "ai/eval", "ai/extract", "backend"):
    sys.path.insert(0, str(REPO_ROOT / _p))

import i5_model_ladder as ladder  # noqa: E402
import score  # noqa: E402

# model -> OpenRouter list price per 1M tokens (input, output), read from the models API on
# 2026-11-25. Used by the spending guard only; the cost in a record is the one OpenRouter reports.
MODELS = {
    "google/gemini-3.7-flash": (0.75, 3.75),
    "openai/gpt-6.1-terra": (1.0, 5.0),
    "anthropic/claude-sonnet-5.5": (2.0, 10.0),
}
# file stem, label set (as i5_model_ladder.PHOTOS; `regression` = the fixture's expected items)
PHOTOS = (("014_tale_07", "i3"), ("014_tale_11", "i3"), ("011_mirabeau_03", "test_v1_1"),
          ("007_bokchun_01", "val_v1_1"), ("018_cheongchun_02", "i3"), ("011_mirabeau_02", "regression"))
RUNS = (1, 2, 3)
CONDITION = "B"
PROMPT = REPO_ROOT / "backend" / "app" / "extraction" / "hybrid_prompt_v2_1.md"
PROMPT_SHA256 = "b14b09b433057d6f6f4c0f6737c2cd9dac5269ee63ef566930510e8420c02e92"
REASONING = "medium"
MAX_TOKENS = 48000
MODEL_COST_LIMIT_USD = 3.0
TOTAL_COST_LIMIT_USD = 6.0
INPUT_TOKENS_BOUND = 30000  # more than any request of these photos (the 3.8 Flash records sent about 8,000)
MISSING_LIMIT = 0.05
TITLE_PHOTO = "011_mirabeau_02"
RUN_1121 = REPO_ROOT / "ai" / "runs" / "2026-11-21_i5_row_pairing"
TITLE_LINES = RUN_1121 / "regression_38flash_v2_1" / "check.json"
# The gemini-3.8-flash records of the same photos, shown next to the candidates (never called here).
BASELINE = (("3.8 Flash, 프롬프트 v2 (11/21 8절, 출력 상한 20,000)", RUN_1121 / "ladder" / "google__gemini-3.8-flash" / "B"),
            ("3.8 Flash, 프롬프트 v2.1 (11/21 10절)", RUN_1121 / "regression_38flash_v2_1" / "google__gemini-3.8-flash" / "B"))


def model_dir(out: Path, model: str) -> Path:
    return out / model.replace("/", "__")


def worst_case_call(model: str, max_tokens: int = MAX_TOKENS) -> float:
    """The most one call can cost: two attempts at the list price."""
    price_in, price_out = MODELS[model]
    return 2 * (INPUT_TOKENS_BOUND * price_in + max_tokens * price_out) / 1e6


def percentile95(values: list[float]) -> float:
    """As i5_regression_compare.py: the value at index int(0.95 * (n - 1)) of the sorted list."""
    ordered = sorted(values)
    return ordered[int(0.95 * (len(ordered) - 1))]


def title_of(label_name: str) -> str:
    """The bottler title of a label name: everything up to its first ")"."""
    return label_name[:label_name.index(")") + 1]


def title_attached(label_name: str, output_name: str | None) -> bool:
    return output_name is not None and score.normalize(title_of(label_name)) in score.normalize(output_name)


def title_lines() -> list[dict]:
    """The 20 lines of 011_mirabeau_02 (label name and price), as recorded on 2026-11-21."""
    return [{"label": row["label"], "price": row["price"]}
            for row in json.loads(TITLE_LINES.read_text(encoding="utf-8"))["mirabeau_02_lines"]]


def common_ending(a: str, b: str) -> int:
    a, b = score.normalize(a), score.normalize(b)
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def output_names(labels: list[dict], rows: list[dict]) -> dict[int, dict | None]:
    """label index -> the output row that stands for it (see the module docstring)."""
    pairs, gt_left, out_left = score.match_photo(labels, rows, lenient=True)
    found: dict[int, dict | None] = {gi: rows[oi] for gi, oi, _ in pairs}
    free = set(out_left)
    for gi in sorted(gt_left):
        g = labels[gi]
        best = max((oi for oi in sorted(free) if rows[oi]["unit"] == g["unit"] and rows[oi]["price_krw"] == g["price_krw"]),
                   key=lambda oi: common_ending(g["raw_name"], rows[oi]["raw_name"]), default=None)
        if best is not None and common_ending(g["raw_name"], rows[best]["raw_name"]) >= 3:
            found[gi] = rows[best]
            free.discard(best)
        else:
            found[gi] = None
    return found


def check_titles(labels: list[dict], rows: list[dict], lines: list[dict]) -> list[dict]:
    """For each of the 20 lines: the name the run wrote, whether the title is in it, the price."""
    found = output_names(labels, rows)
    out = []
    for line in lines:
        gi = next(i for i, g in enumerate(labels) if g["raw_name"] == line["label"] and g["price_krw"] == line["price"])
        row = found[gi]
        out.append({"label": line["label"], "output": row["raw_name"] if row else None,
                    "attached": title_attached(line["label"], row["raw_name"] if row else None),
                    "price_ok": row is not None and row["price_krw"] == line["price"]})
    return out


def attempt_notes(record: dict) -> dict:
    """What the failed attempts of a record were, and what they cost."""
    kinds = {"truncated": 0, "format": 0, "transport": 0}
    for failure in record["failures"]:
        if failure["kind"] == "transport":
            kinds["transport"] += 1
        elif failure["detail"].startswith("status length"):
            kinds["truncated"] += 1
        else:
            kinds["format"] += 1
    return {**kinds, "failed_cost": sum(f.get("cost_usd") or 0 for f in record["failures"])}


def summarize(folder: Path, labels: dict[str, list[dict]], lines: list[dict], runs: tuple[int, ...] | None) -> dict:
    """Score the records of one model folder (`runs` None: every record of the photos that is there)."""
    records, latency = [], []
    totals = {"runs": 0, "failed": 0, "cells": 0, "ok": 0, "wrong": 0, "missing": 0, "name_only": 0, "extra": 0,
              "kinds": {k: 0 for k in ladder.KINDS}, "truncated": 0, "format": 0, "transport": 0,
              "cost": 0.0, "failed_cost": 0.0, "titles_missing": 0}
    worst = {"wrong": 0, "missing_share": 0.0}
    providers: dict[str, int] = {}
    for stem, _ in PHOTOS:
        paths = sorted(folder.glob(f"{stem}_r*.json")) if runs is None else [folder / f"{stem}_r{run}.json" for run in runs]
        for path in paths:
            if not path.exists():
                continue
            rec = json.loads(path.read_text(encoding="utf-8"))
            notes = attempt_notes(rec)
            entry = {"photo": stem, "run": rec.get("run") or int(path.stem.rsplit("_r", 1)[1]), **notes,
                     "cost": (rec.get("cost_usd") or 0) + notes["failed_cost"], "prompt_file": rec["prompt_file"],
                     "max_tokens": rec.get("max_tokens")}
            totals["runs"] += 1
            for key in ("truncated", "format", "transport", "failed_cost"):
                totals[key] += notes[key]
            totals["cost"] += entry["cost"]
            if rec["rows"] is None:
                totals["failed"] += 1
                records.append({**entry, "failed": True})
                continue
            s = ladder.score_rows(labels[stem], rec["rows"])
            share = s["missing"] / s["cells"] if s["cells"] else 0.0
            entry.update(failed=False, cells=s["cells"], ok=s["ok"], wrong=s["wrong"], missing=s["missing"],
                         missing_share=share, name_only=s["name_only"], extra=s["extra"], kinds=s["kinds"],
                         wrong_cells=s["wrong_cells"], latency_s=rec["latency_ms"] / 1000,
                         input_tokens=rec.get("input_tokens"), output_tokens=rec.get("output_tokens"),
                         thought_tokens=rec.get("thought_tokens"), provider=rec.get("provider"))
            if stem == TITLE_PHOTO:
                entry["titles"] = check_titles(labels[stem], rec["rows"], lines)
                totals["titles_missing"] += sum(not t["attached"] for t in entry["titles"])
            for key in ("cells", "ok", "wrong", "missing", "name_only", "extra"):
                totals[key] += s[key]
            for kind in ladder.KINDS:
                totals["kinds"][kind] += s["kinds"][kind]
            worst["wrong"] = max(worst["wrong"], s["wrong"])
            worst["missing_share"] = max(worst["missing_share"], share)
            latency.append(entry["latency_s"])
            providers[str(rec.get("provider"))] = providers.get(str(rec.get("provider")), 0) + 1
            records.append(entry)
    out = {"records": records, "totals": totals, "worst": worst, "providers": providers}
    if latency:
        out["latency"] = {"median_s": round(statistics.median(latency), 1), "p95_s": round(percentile95(latency), 1),
                          "max_s": round(max(latency), 1)}
    if totals["runs"]:
        out["cost_per_photo"] = round(totals["cost"] / totals["runs"], 4)
    return out


def verdict(summary: dict, expected_runs: int = len(PHOTOS) * len(RUNS), title_runs: int = len(RUNS)) -> dict:
    """The pass criterion of the module docstring; `reasons` lists what failed."""
    totals, worst = summary["totals"], summary["worst"]
    title_records = [r for r in summary["records"] if not r.get("failed") and "titles" in r]
    reasons = []
    if totals["runs"] < expected_runs:
        reasons.append(f"{totals['runs']} of {expected_runs} runs recorded")
    if totals["failed"]:
        reasons.append(f"{totals['failed']} runs without an answer in the schema")
    if worst["wrong"]:
        reasons.append(f"wrong prices (worst run {worst['wrong']}, all runs {totals['wrong']})")
    if worst["missing_share"] > MISSING_LIMIT:
        reasons.append(f"missing {worst['missing_share']:.1%} in the worst run")
    if len(title_records) < title_runs or totals["titles_missing"]:
        reasons.append(f"{TITLE_PHOTO}: {totals['titles_missing']} lines without the title "
                       f"({len(title_records)} of {title_runs} runs scored)")
    return {"pass": not reasons, "reasons": reasons}


def print_summary(name: str, summary: dict, result: dict | None) -> None:
    totals = summary["totals"]
    print(f"\n### {name}\n")
    print("| 사진 | 회차 | 정답 칸 | 맞음 | 틀림 | 누락 | 이름만 실패 | 남는 행 | 제목 빠짐 | 입력 | 출력(추론) | 초 | 청구액 | 비고 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in summary["records"]:
        note = ", ".join(f"{label} {r[key]}" for key, label in (("truncated", "잘림"), ("format", "형식 실패"),
                                                                ("transport", "응답 없음")) if r[key])
        if r["failed"]:
            print(f"| {r['photo']} | r{r['run']} | – | – | – | – | – | – | – | – | – | – | ${r['cost']:.4f} | 답 없음. {note} |")
            continue
        titles = "–" if "titles" not in r else str(sum(not t["attached"] for t in r["titles"]))
        print(f"| {r['photo']} | r{r['run']} | {r['cells']} | {r['ok']} | {r['wrong']} | {r['missing']} | {r['name_only']} | "
              f"{r['extra']} | {titles} | {r['input_tokens']} | {r['output_tokens']} ({r['thought_tokens']}) | "
              f"{r['latency_s']:.1f} | ${r['cost']:.4f} | {note} |")
    print(f"\n- 기록 {totals['runs']}개 (답 없음 {totals['failed']}): 정답 칸 {totals['cells']}, 맞음 {totals['ok']}, "
          f"틀림 {totals['wrong']} {totals['kinds']}, 누락 {totals['missing']}, 이름만 실패 {totals['name_only']}, "
          f"남는 행 {totals['extra']}, 제목 빠짐 {totals['titles_missing']}줄")
    print(f"- 가장 나쁜 회차: 틀림 {summary['worst']['wrong']}칸, 누락 {summary['worst']['missing_share']:.1%}")
    if "latency" in summary:
        lat = summary["latency"]
        print(f"- 지연 중앙값 {lat['median_s']}초, p95 {lat['p95_s']}초, 최대 {lat['max_s']}초 (답이 나온 시도만)")
    if totals["runs"]:
        print(f"- 청구액 합 ${totals['cost']:.4f} (그중 실패한 시도 ${totals['failed_cost']:.4f}), 사진 1장당 ${summary['cost_per_photo']:.4f}")
    print(f"- 잘린 시도 {totals['truncated']}, 형식 실패 {totals['format']}, 응답 없음 {totals['transport']}; 제공자 {summary['providers']}")
    for r in summary["records"]:
        for cell in r.get("wrong_cells") or []:
            print(f"  - 틀림 {r['photo']} r{r['run']}: {cell}")
        for t in r.get("titles") or []:
            if not t["attached"] or not t["price_ok"]:
                print(f"  - 제목 {r['photo']} r{r['run']}: 정답 {t['label']!r} -> 출력 {t['output']!r}"
                      + ("" if t["price_ok"] else " (가격 다름)"))
    if result is not None:
        print(f"- **판정: {'통과' if result['pass'] else '통과 못 함'}**" + ("" if result["pass"] else f" ({'; '.join(result['reasons'])})"))


def report(out: Path, labels: dict, lines: list[dict]) -> dict:
    full = {"models": {}, "baseline": {}}
    for model in MODELS:
        summary = summarize(model_dir(out, model) / CONDITION, labels, lines, RUNS)
        result = verdict(summary)
        print_summary(model, summary, result)
        full["models"][model] = {**summary, "verdict": result}
    for name, folder in BASELINE:
        summary = summarize(folder, labels, lines, None)
        print_summary(name, summary, None)
        full["baseline"][name] = summary
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_bytes(json.dumps(full, ensure_ascii=False, indent=1).encode("utf-8"))
    return full


def main(argv=None) -> int:
    from dotenv import dotenv_values
    from extract import data_dir as default_data_dir
    import i5_row_pairing
    import p46_extract
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--data-dir", type=Path)
    ap.add_argument("--check", action="store_true", help="check the inputs and print the spending bounds; no API call")
    ap.add_argument("--report", action="store_true", help="score the records; no API call")
    ap.add_argument("--models", nargs="+", choices=list(MODELS), default=list(MODELS))
    ap.add_argument("--only", nargs="+", metavar="STEM", help="call only these photos")
    ap.add_argument("--runs", type=int, nargs="+", choices=RUNS, help="run numbers to call (default 1 2 3)")
    args = ap.parse_args(argv)
    data_dir = args.data_dir or default_data_dir()
    ladder.PHOTOS, ladder.PROMPT_B = PHOTOS, PROMPT
    ladder.FIXTURES = i5_row_pairing.known_photos(data_dir)
    fixtures = {stem: ladder.FIXTURES[stem] for stem, _ in PHOTOS}
    labels, lines = ladder.load_labels(), title_lines()
    if args.report:
        report(args.out, labels, lines)
        return 0
    problems = p46_extract.check_inputs(list(fixtures.values()), data_dir)
    sha = hashlib.sha256(ladder.read_lf(PROMPT).encode("utf-8")).hexdigest()
    if sha != PROMPT_SHA256:
        problems.append(f"{PROMPT.name} is {sha[:12]}, not {PROMPT_SHA256[:12]}")
    if len(lines) != 20 or any(sum(g["raw_name"] == line["label"] and g["price_krw"] == line["price"]
                                   for g in labels[TITLE_PHOTO]) != 1 for line in lines):
        problems.append(f"the 20 title lines of {TITLE_PHOTO} are not each one label item")
    if problems:
        raise SystemExit("\n".join(problems))
    todo = [(model, run, stem, model_dir(args.out, model) / CONDITION / f"{stem}_r{run}.json")
            for model in args.models for run in (args.runs or RUNS) for stem, _ in PHOTOS
            if not args.only or stem in args.only]
    todo = [job for job in todo if not job[3].exists()]
    print(f"photos {len(PHOTOS)}, priced label items {[sum(score.price_checked(g) for g in labels[s]) for s, _ in PHOTOS]}; "
          f"prompt {PROMPT.name} {sha[:12]}; calls to make {len(todo)}; output cap {MAX_TOKENS}")
    if args.check:
        for model in MODELS:
            print(f"  {model}: records cost ${ladder.stage_cost(model_dir(args.out, model)):.4f}, "
                  f"one call costs at most ${worst_case_call(model):.2f}, limit ${MODEL_COST_LIMIT_USD}")
        for stem in fixtures:
            sent = ladder.inputs(fixtures[stem], CONDITION, data_dir)
            print(f"  {stem}: OCR lines {sent['ocr_lines']}, user text {len(sent['user_text'])} chars, image {len(sent['image'])} bytes")
        return 0
    key = (dotenv_values(REPO_ROOT / ".env").get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set in the repo .env")
    for calls, (model, run, stem, target) in enumerate(todo):
        base = model_dir(args.out, model)
        spent, total = ladder.stage_cost(base), sum(ladder.stage_cost(model_dir(args.out, m)) for m in MODELS)
        if spent + worst_case_call(model) > MODEL_COST_LIMIT_USD or total + worst_case_call(model) > TOTAL_COST_LIMIT_USD:
            print(f"stopped before {model} {stem} r{run}: the model's records cost ${spent:.2f} (all models ${total:.2f}), "
                  f"one more call can cost ${worst_case_call(model):.2f}; limits ${MODEL_COST_LIMIT_USD} / ${TOTAL_COST_LIMIT_USD}")
            return 1
        if calls:
            time.sleep(ladder.MIN_INTERVAL_S)
        stage = {"model": model, "route": "openrouter", "thinking": REASONING, "max_tokens": MAX_TOKENS}
        record = ladder.run_one(stage, fixtures[stem], CONDITION, data_dir, {"openrouter": key})
        record["run"], record["max_tokens"] = run, MAX_TOKENS
        target.parent.mkdir(parents=True, exist_ok=True)
        if record["rows"] is None and all(f["kind"] == "transport" for f in record["failures"]):
            # no answer at all (no provider, 5xx, network): not a result of the model. Logged; the call stays to do.
            with (base / "transport_failures.jsonl").open("ab") as log:
                log.write((json.dumps({"at": record["started_at"], "photo": target.stem, "failures": record["failures"]},
                                      ensure_ascii=False) + chr(10)).encode("utf-8"))
            print(f"{model} {target.stem} no answer twice ({record['failures'][-1]['detail'][:160]}); stopped", flush=True)
            return 1
        target.write_bytes(json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"))
        rows = "FAILED" if record["rows"] is None else len(record["rows"])
        cost = (record.get("cost_usd") or 0) + sum(f.get("cost_usd") or 0 for f in record["failures"])
        print(f"{model} {target.stem} rows {rows} attempts {record['attempts']} {(record.get('latency_ms') or 0) / 1000:.1f}s "
              f"out {record.get('output_tokens')} thought {record.get('thought_tokens')} ${cost:.4f} "
              f"provider {record.get('provider')}", flush=True)
    report(args.out, labels, lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
