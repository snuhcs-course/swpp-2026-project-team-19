"""I5-P19: the 17 regression photos through the server's new extraction code, once.

    python ai/eval/i5_server_route_regression.py --out ai/runs/2026-11-25_i5_p19_server_route --check
    python ai/eval/i5_server_route_regression.py --out ai/runs/2026-11-25_i5_p19_server_route
    python ai/eval/i5_server_route_regression.py --out ai/runs/2026-11-25_i5_p19_server_route --report

Does backend/app/extraction/routed.py (MENU_EXTRACTOR=openrouter) give what the evaluation script
gave on 2026-11-21? Each photo goes through `extract_menu_routed`, the function the server's
extractor calls: the same OCR step (answered from the CLOVA cache, no CLOVA call), prompt v2.1,
google/gemini-3.8-flash through OpenRouter, reasoning medium, output cap 48,000.

Two things differ from the deployed settings, both to keep the run to the question and the money:
- no fallback models, so every answer is stage 0 and one call costs at most what 3.8 Flash costs;
- the Gemini API routes are closed (their client refuses), so a failed OpenRouter call fails the
  photo here instead of spending the free Gemini quota.

Records go to <out>/<stem>.json (the meta the server would store, without the OCR line table, and
the whisky rows that are scored); an existing record is kept. Before each call, the cost of the
records plus the most one call can cost (two attempts of 30,000 tokens in and 48,000 out at the
list price) must stay within COST_LIMIT_USD.

`--report` scores the records next to the 2026-11-21 records of the same photos, with the same
function (i5_model_ladder.score_rows; report sections 9 and 10):
  flash-lite, prompt v2, Gemini API       ai/runs/2026-11-21_i5_row_pairing/regression/v2
  3.8 Flash, prompt v2.1, the eval script  .../regression_38flash_v2_1/google__gemini-3.8-flash/B (run 1)

The API key is read from the repo .env and is never printed or written.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in ("ai/regression", "ai/eval", "ai/extract", "backend"):
    sys.path.insert(0, str(REPO_ROOT / _p))

import i5_fallback_ladder as fallback  # noqa: E402
import i5_model_ladder as ladder  # noqa: E402
import run_extraction as rx  # noqa: E402
from app.extraction import ExtractionError, ExtractionSettings  # noqa: E402
from app.extraction.openrouter import OpenRouterSettings  # noqa: E402
from app.extraction.routed import CircuitBreaker, RouteSettings, extract_menu_routed  # noqa: E402

MODEL = "google/gemini-3.8-flash"
PRICE = (0.75, 3.75)  # USD per 1M tokens (input, output), the list price on 2026-11-25
COST_LIMIT_USD = 1.0
EXTRA_PHOTOS = (("007_bokchun_02", "val_v1_1"), ("012_beck_04", "test_v1_1"))
RUN_1121 = REPO_ROOT / "ai" / "runs" / "2026-11-21_i5_row_pairing"
FLASH_LITE = RUN_1121 / "regression" / "v2"
EVAL_V2_1 = RUN_1121 / "regression_38flash_v2_1" / "google__gemini-3.8-flash" / "B"
FLASH_LITE_PRICE = (0.30, 2.50)  # list price used in report section 8.6; the records were made on the free key
KEYS = ("ok", "wrong", "missing", "name_only", "extra")


class ClosedGemini:
    """The Gemini API routes are not part of this run: refuse instead of calling."""

    class _Interactions:
        def create(self, **request):
            raise RuntimeError("the Gemini API routes are closed in this run")

    interactions = _Interactions()


def worst_case_call() -> float:
    return 2 * (30000 * PRICE[0] + 48000 * PRICE[1]) / 1e6


def whisky_rows(items: list[dict]) -> list[dict]:
    """The rows that are scored, as i5_model_ladder.parse_rows makes them."""
    return [{k: it[k] for k in ("raw_name", "price_krw", "pour_ml", "unit")} for it in items if it.get("category", "whisky") == "whisky"]


def spent(out: Path) -> float:
    return sum((json.loads(p.read_text(encoding="utf-8")).get("cost_usd") or 0) for p in out.glob("*.json") if p.name != "summary.json")


def run_photo(fixture: dict, data_dir: Path, route: RouteSettings, breaker: CircuitBreaker) -> dict:
    photo = fixture["photo"]
    path = data_dir / photo["photo_dir"] / photo["file"]
    cache = json.loads((data_dir / "ocr_cache" / f"{path.stem}__table-off.json").read_text(encoding="utf-8"))
    record = {"photo_id": fixture["photo_id"], "source_image": photo["file"]}
    t0 = time.perf_counter()
    try:
        result = extract_menu_routed(path.read_bytes(), rx.MIME_TYPES[path.suffix.lower()], rx.REPLAY_CLOVA, route, breaker,
                                     gemini_client=ClosedGemini(), ocr_client=rx.ReplayOcr(cache))
    except ExtractionError as error:
        meta = getattr(error, "meta", None) or {"route": getattr(error, "route", None)}
        record.update(error=f"{type(error).__name__}: {str(error)[:300]}", rows=None,
                      raw_text=getattr(error, "raw_text", None))
    else:
        meta = result["meta"]
        record.update(error=None, rows=whisky_rows(meta["rawOutput"]["items"]), items=len(result["items"]),
                      other_items=len(meta["otherItems"]))
    record["wall_ms"] = round((time.perf_counter() - t0) * 1000)
    record["cost_usd"] = meta.get("costUsd")
    record["meta"] = {**meta, "ocr": {k: v for k, v in (meta.get("ocr") or {}).items() if k != "lines"}}
    return record


def usage(records: list[dict], latency_key, cost_key) -> dict:
    latency = [latency_key(r) / 1000 for r in records]
    cost = [cost_key(r) for r in records]
    return {"photos": len(records), "latency_median_s": round(statistics.median(latency), 1),
            "latency_p95_s": round(fallback.percentile95(latency), 1), "latency_max_s": round(max(latency), 1),
            "cost_total": round(sum(cost), 4), "cost_per_photo": round(sum(cost) / len(cost), 4)}


def report(out: Path, stems: list[str], labels: dict) -> dict:
    sets = {"flash_lite": {}, "eval_v2_1": {}, "server": {}}
    for stem in stems:
        for name, path in (("flash_lite", FLASH_LITE / f"{stem}_r1.json"), ("eval_v2_1", EVAL_V2_1 / f"{stem}_r1.json"),
                           ("server", out / f"{stem}.json")):
            if path.exists():
                sets[name][stem] = json.loads(path.read_text(encoding="utf-8"))
    rows_of = {"flash_lite": lambda r: whisky_rows(json.loads(r["raw_text"])["items"]),
               "eval_v2_1": lambda r: r["rows"], "server": lambda r: r["rows"]}
    totals = {name: dict.fromkeys(KEYS, 0) | {"kinds": dict.fromkeys(ladder.KINDS, 0)} for name in sets}
    photos, same_rows = {}, 0
    print("| 사진 | 정답 칸 | flash-lite v2 (11/21) | 3.8 Flash v2.1 평가 스크립트 (11/21) | 3.8 Flash v2.1 서버 코드 (오늘) | 서버 코드 지연 | 청구액 |")
    print("|---|---|---|---|---|---|---|")
    for stem in stems:
        scores = {}
        for name, records in sets.items():
            rows = rows_of[name](records[stem]) if stem in records else None
            if rows is None:
                continue
            s = ladder.score_rows(labels[stem], rows)
            scores[name] = s
            for key in KEYS:
                totals[name][key] += s[key]
            for kind in ladder.KINDS:
                totals[name]["kinds"][kind] += s["kinds"][kind]
        server = sets["server"].get(stem)
        if server and server["rows"] is not None and stem in sets["eval_v2_1"]:
            same_rows += server["rows"] == sets["eval_v2_1"][stem]["rows"]
        cell = lambda s: "–" if s is None else f"{s['ok']}/{s['wrong']}/{s['missing']}/{s['name_only']}" + (f" +{s['extra']}" if s["extra"] else "")
        note = "–" if server is None else ("실패: " + server["error"] if server["error"] else f"{server['meta']['latencyMs'] / 1000:.1f}초")
        cost = "–" if server is None or server["cost_usd"] is None else f"${server['cost_usd']:.4f}"
        print(f"| {stem} | {sum(ladder.score.price_checked(g) for g in labels[stem])} | {cell(scores.get('flash_lite'))} | "
              f"{cell(scores.get('eval_v2_1'))} | {cell(scores.get('server'))} | {note} | {cost} |")
        photos[stem] = scores
    done = [r for r in sets["server"].values() if r["error"] is None]
    summary = {"photos": photos, "totals": totals, "same_rows_as_eval": same_rows, "usage": {}}
    if sets["flash_lite"]:
        summary["usage"]["flash_lite"] = usage(
            list(sets["flash_lite"].values()), lambda r: r["latency_ms"],
            lambda r: (r["input_tokens"] * FLASH_LITE_PRICE[0] + (r["output_tokens"] + (r["thought_tokens"] or 0)) * FLASH_LITE_PRICE[1]) / 1e6)
    if sets["eval_v2_1"]:
        summary["usage"]["eval_v2_1"] = usage(list(sets["eval_v2_1"].values()), lambda r: r["latency_ms"], lambda r: r["cost_usd"])
    if done:
        summary["usage"]["server"] = usage(done, lambda r: r["meta"]["latencyMs"], lambda r: r["cost_usd"] or 0)
        summary["routes"] = sorted({(r["meta"]["route"]["stage"], r["meta"]["route"]["model"], str(r["meta"]["route"]["provider"])) for r in done})
        summary["truncated_attempts"] = sum(r["meta"]["truncatedAttempts"] for r in done)
        summary["attempts"] = sum(r["meta"]["attempts"] for r in done)
    summary["failed"] = {stem: r["error"] for stem, r in sets["server"].items() if r["error"]}
    print("\ntotals:", json.dumps(totals, ensure_ascii=False))
    print("usage:", json.dumps(summary["usage"], ensure_ascii=False))
    print("server routes:", summary.get("routes"), "| truncated attempts:", summary.get("truncated_attempts"),
          "| calls:", summary.get("attempts"), "| photos with the same scored rows as the 11/21 eval run:", same_rows,
          "| failed:", summary["failed"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_bytes(json.dumps(summary, ensure_ascii=False, indent=1).encode("utf-8"))
    return summary


def main(argv=None) -> int:
    from dotenv import dotenv_values
    from extract import data_dir as default_data_dir
    import i5_row_pairing
    import p46_extract
    import regression
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--data-dir", type=Path)
    ap.add_argument("--check", action="store_true", help="check the inputs; no API call")
    ap.add_argument("--report", action="store_true", help="score the records; no API call")
    ap.add_argument("--only", nargs="+", metavar="STEM")
    args = ap.parse_args(argv)
    data_dir = args.data_dir or default_data_dir()
    ladder.FIXTURES = i5_row_pairing.known_photos(data_dir)
    ladder.PHOTOS = tuple((Path(fx["photo"]["file"]).stem, "regression") for fx in regression.load_fixtures()) + EXTRA_PHOTOS
    stems = [stem for stem, _ in ladder.PHOTOS]
    labels = ladder.load_labels()
    if args.report:
        report(args.out, stems, labels)
        return 0
    problems = p46_extract.check_inputs([ladder.FIXTURES[stem] for stem in stems], data_dir)
    if problems:
        raise SystemExit("\n".join(problems))
    todo = [stem for stem in stems if (not args.only or stem in args.only) and not (args.out / f"{stem}.json").exists()]
    print(f"photos {len(stems)}, priced label items {sum(ladder.score.price_checked(g) for s in stems for g in labels[s])}; "
          f"calls to make {len(todo)}; one call costs at most ${worst_case_call():.3f}, limit ${COST_LIMIT_USD}")
    if args.check:
        return 0
    key = (dotenv_values(REPO_ROOT / ".env").get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set in the repo .env")
    closed = ExtractionSettings(api_key="closed", model="closed", thinking_level="medium", max_attempts=1)
    route = RouteSettings(openrouter=OpenRouterSettings(api_key=key, model=MODEL), direct=closed, lite=closed)
    breaker = CircuitBreaker(route.breaker_failures, route.breaker_cooldown_s)
    args.out.mkdir(parents=True, exist_ok=True)
    for n, stem in enumerate(todo):
        cost = spent(args.out)
        if cost + worst_case_call() > COST_LIMIT_USD:
            print(f"stopped before {stem}: the records cost ${cost:.3f}, one more call can cost ${worst_case_call():.3f}")
            return 1
        if n:
            time.sleep(ladder.MIN_INTERVAL_S)
        record = run_photo(ladder.FIXTURES[stem], data_dir, route, breaker)
        (args.out / f"{stem}.json").write_bytes(json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"))
        meta = record["meta"]
        print(f"{stem} {'FAILED ' + record['error'] if record['error'] else 'rows ' + str(len(record['rows']))} "
              f"stage {(meta.get('route') or {}).get('stage')} model {meta.get('model')} {meta.get('latencyMs')}ms "
              f"out {meta.get('outputTokens')} thought {meta.get('thoughtTokens')} ${record['cost_usd']}", flush=True)
        if record["error"]:
            print("stopped at the first failed photo")
            return 1
    report(args.out, stems, labels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
