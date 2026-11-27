"""I5-P43: three imports at the same time through the server's extraction code, with real calls.

    python ai/eval/i5_concurrent_imports_check.py --out ai/runs/2026-11-26_i5_a2_p43/concurrent --check
    python ai/eval/i5_concurrent_imports_check.py --out ai/runs/2026-11-26_i5_a2_p43/concurrent

Three "imports" of two photos each run in three threads, as three menu imports do in the API
process: inside an import the photos are read one after another, and the imports share one
circuit breaker. Each photo goes through `extract_menu_routed` (MENU_EXTRACTOR=openrouter's
function), google/gemini-3.8-flash, prompt v2.1, CLOVA from the cache. There is no database here:
this checks the extraction calls, not the import rows.

As in i5_server_route_regression.py, no fallback models are sent and the Gemini API routes are
closed. One more difference, for the spending limit only: `max_tokens` is 16,000 instead of
48,000, so that six calls cannot cost more than COST_LIMIT_USD even if every one is cut and asked
for again (the six photos needed 2,700 to 5,800 output tokens on 2026-11-25). The script refuses to
start when that bound does not hold or when the output folder already has records.

It reports, per call, when it started and ended (seconds from the start of the run), how many
calls were in flight together, each import's time next to the sum of its two calls, and the
score of every photo (i5_model_ladder.score_rows) next to the 2026-11-25 run of the same photos
one at a time (ai/runs/2026-11-25_i5_p19_server_route).

The API key is read from the repo .env and is never printed or written.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in ("ai/regression", "ai/eval", "ai/extract", "backend"):
    sys.path.insert(0, str(REPO_ROOT / _p))

import i5_model_ladder as ladder  # noqa: E402
import i5_server_route_regression as single  # noqa: E402
from app.extraction import ExtractionSettings  # noqa: E402
from app.extraction.openrouter import OpenRouterSettings  # noqa: E402
from app.extraction.routed import CircuitBreaker, RouteSettings  # noqa: E402

IMPORTS = (("A", ("010_sui_05", "009_odbi_04")), ("B", ("008_seorosang_01", "007_bokchun_03")),
           ("C", ("010_sui_02", "010_sui_04")))
MAX_TOKENS = 16000
COST_LIMIT_USD = 1.0
ONE_AT_A_TIME = REPO_ROOT / "ai" / "runs" / "2026-11-25_i5_p19_server_route"


def worst_case_total() -> float:
    calls = sum(len(stems) for _, stems in IMPORTS)
    return calls * 2 * (30000 * single.PRICE[0] + MAX_TOKENS * single.PRICE[1]) / 1e6


def in_flight_peak(spans: list[tuple[float, float]]) -> int:
    """The most calls that were open at the same moment."""
    events = sorted([(start, 1) for start, _ in spans] + [(end, -1) for _, end in spans], key=lambda e: (e[0], e[1]))
    peak = now = 0
    for _, step in events:
        now += step
        peak = max(peak, now)
    return peak


def main(argv=None) -> int:
    from dotenv import dotenv_values
    from extract import data_dir as default_data_dir
    import i5_row_pairing
    import p46_extract
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--data-dir", type=Path)
    ap.add_argument("--check", action="store_true", help="check the inputs and the spending bound; no API call")
    args = ap.parse_args(argv)
    data_dir = args.data_dir or default_data_dir()
    stems = [stem for _, group in IMPORTS for stem in group]
    ladder.FIXTURES = i5_row_pairing.known_photos(data_dir)
    ladder.PHOTOS = tuple((stem, "regression") for stem in stems)
    labels = ladder.load_labels()
    problems = p46_extract.check_inputs([ladder.FIXTURES[stem] for stem in stems], data_dir)
    if worst_case_total() > COST_LIMIT_USD:
        problems.append(f"the calls can cost ${worst_case_total():.2f}, over the limit ${COST_LIMIT_USD}")
    if args.out.exists() and any(args.out.glob("*.json")):
        problems.append(f"{args.out} already has records; this run is made once")
    if problems:
        raise SystemExit("\n".join(problems))
    print(f"imports {len(IMPORTS)}, photos {len(stems)}, output cap {MAX_TOKENS}; "
          f"the calls cost at most ${worst_case_total():.2f} in all, limit ${COST_LIMIT_USD}")
    if args.check:
        return 0
    key = (dotenv_values(REPO_ROOT / ".env").get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set in the repo .env")
    closed = ExtractionSettings(api_key="closed", model="closed", thinking_level="medium", max_attempts=1)
    route = RouteSettings(openrouter=OpenRouterSettings(api_key=key, model=single.MODEL, max_tokens=MAX_TOKENS),
                          direct=closed, lite=closed)
    breaker = CircuitBreaker(route.breaker_failures, route.breaker_cooldown_s)
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    done: dict[str, dict] = {}

    def run_import(name: str, group: tuple[str, ...]) -> None:
        for stem in group:  # one after another, as menu_import_processing._extract_all does
            started = time.perf_counter() - t0
            record = single.run_photo(ladder.FIXTURES[stem], data_dir, route, breaker)
            record.update({"import": name, "started_s": round(started, 1), "ended_s": round(time.perf_counter() - t0, 1)})
            (args.out / f"{stem}.json").write_bytes(json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"))
            done[stem] = record
            if record["error"]:
                return  # a failed photo fails its import

    threads = [threading.Thread(target=run_import, args=item, name=f"import-{item[0]}") for item in IMPORTS]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - t0

    print("\n| 등록 | 사진 | 시작 | 끝 | 걸린 시간 | 11/25 한 장씩 돌렸을 때 | 맞음/틀림/누락/이름만 | 11/25 | 청구액 |")
    print("|---|---|---|---|---|---|---|---|---|")
    summary = {"wall_s": round(wall, 1), "imports": {}, "photos": {}}
    for name, group in IMPORTS:
        for stem in group:
            rec = done.get(stem)
            before = json.loads((ONE_AT_A_TIME / f"{stem}.json").read_text(encoding="utf-8"))
            b = ladder.score_rows(labels[stem], before["rows"])
            cell = lambda s: f"{s['ok']}/{s['wrong']}/{s['missing']}/{s['name_only']}" + (f" +{s['extra']}" if s["extra"] else "")
            if rec is None:
                print(f"| {name} | {stem} | – | – | 실행 안 됨 (앞 사진 실패) | {before['meta']['latencyMs'] / 1000:.1f}초 | – | {cell(b)} | – |")
                continue
            if rec["error"]:
                print(f"| {name} | {stem} | {rec['started_s']} | {rec['ended_s']} | 실패: {rec['error']} | – | – | {cell(b)} | – |")
                continue
            s = ladder.score_rows(labels[stem], rec["rows"])
            summary["photos"][stem] = {"import": name, "started_s": rec["started_s"], "ended_s": rec["ended_s"],
                                       "latency_s": rec["meta"]["latencyMs"] / 1000, "attempts": rec["meta"]["attempts"],
                                       "truncated": rec["meta"]["truncatedAttempts"], "cost_usd": rec["cost_usd"],
                                       "score": {k: s[k] for k in single.KEYS}, "same_rows_as_one_at_a_time": rec["rows"] == before["rows"],
                                       "one_at_a_time_latency_s": before["meta"]["latencyMs"] / 1000, "route": rec["meta"]["route"]}
            print(f"| {name} | {stem} | {rec['started_s']}초 | {rec['ended_s']}초 | {rec['ended_s'] - rec['started_s']:.1f}초 | "
                  f"{before['meta']['latencyMs'] / 1000:.1f}초 | {cell(s)} | {cell(b)} | ${rec['cost_usd']:.4f} |")
        ended = [done[stem]["ended_s"] for stem in group if stem in done]
        summary["imports"][name] = {"ended_s": max(ended) if ended else None, "photos_done": len(ended)}
    spans = [(p["started_s"], p["ended_s"]) for p in summary["photos"].values()]
    summary["in_flight_peak"] = in_flight_peak(spans) if spans else 0
    summary["sum_of_calls_s"] = round(sum(end - start for start, end in spans), 1)
    summary["cost_usd"] = round(sum(p["cost_usd"] or 0 for p in summary["photos"].values()), 4)
    summary["failed"] = {stem: rec["error"] for stem, rec in done.items() if rec["error"]}
    print(f"\nwall {summary['wall_s']}s; sum of the calls {summary['sum_of_calls_s']}s; most calls in flight together "
          f"{summary['in_flight_peak']}; cost ${summary['cost_usd']}; imports {summary['imports']}; failed {summary['failed']}")
    (args.out / "summary.json").write_bytes(json.dumps(summary, ensure_ascii=False, indent=1).encode("utf-8"))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
