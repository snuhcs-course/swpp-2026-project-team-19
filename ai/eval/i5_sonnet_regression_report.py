"""I5-P19 follow-up E: claude-sonnet-5.5 on the 17 regression photos, next to gemini-3.8-flash. No API call.

    python ai/eval/i5_sonnet_regression_report.py --out ai/runs/2026-11-26_i5_p19_followup/regression_sonnet/summary.json

The Sonnet records were made with
    python ai/eval/i5_model_ladder.py --stage 3 --photos regression --conditions B --runs 1 \
        --prompt-b backend/app/extraction/hybrid_prompt_v2_1.md --max-tokens 48000 --cost-limit 1.6 --out <folder>
(condition B, hybrid prompt v2.1, reasoning medium: the request of report sections 10 and 11).
They are scored with i5_model_ladder.score_rows next to the gemini-3.8-flash records of the same
photos and prompt: the evaluation script's run 1 of 2026-11-21 (section 10) and the server code's
run of 2026-11-25. The 20 bottler-title lines of 011_mirabeau_02 are checked as in section 11
(i5_fallback_ladder.check_titles).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in ("ai/regression", "ai/eval", "ai/extract", "backend"):
    sys.path.insert(0, str(REPO_ROOT / _p))

import i5_fallback_ladder as fallback  # noqa: E402
import i5_model_ladder as ladder  # noqa: E402
import i5_server_route_regression as single  # noqa: E402

RUNS = REPO_ROOT / "ai" / "runs"
SONNET = RUNS / "2026-11-26_i5_p19_followup" / "regression_sonnet" / "anthropic__claude-sonnet-5.5" / "B"
SETS = (
    ("flash_eval", "3.8 Flash, 평가 스크립트 (11/21)", single.EVAL_V2_1, "{stem}_r1.json"),
    ("flash_server", "3.8 Flash, 서버 코드 (11/25)", RUNS / "2026-11-25_i5_p19_server_route", "{stem}.json"),
    ("sonnet", "Sonnet 5.5 (11/26)", SONNET, "{stem}_r1.json"),
)
KEYS = ("ok", "wrong", "missing", "name_only", "extra")


def usage_of(key: str, record: dict) -> dict:
    meta = record.get("meta") or record
    return {"latency_s": (meta.get("latencyMs") or meta.get("latency_ms")) / 1000,
            "cost": record.get("cost_usd") if key != "flash_server" else record["cost_usd"],
            "input": meta.get("inputTokens") or meta.get("input_tokens"),
            "output": meta.get("outputTokens") or meta.get("output_tokens"),
            "thought": meta.get("thoughtTokens") if "thoughtTokens" in meta else meta.get("thought_tokens"),
            "provider": meta["route"].get("provider") if isinstance(meta.get("route"), dict) else record.get("provider")}


def main(argv=None) -> int:
    from extract import data_dir as default_data_dir
    import i5_row_pairing
    import regression
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    ladder.FIXTURES = i5_row_pairing.known_photos(default_data_dir())
    ladder.PHOTOS = tuple((Path(fx["photo"]["file"]).stem, "regression") for fx in regression.load_fixtures()) + single.EXTRA_PHOTOS
    stems = [stem for stem, _ in ladder.PHOTOS]
    labels = ladder.load_labels()
    title_lines = fallback.title_lines()

    totals = {key: Counter() for key, *_ in SETS}
    usage = {key: [] for key, *_ in SETS}
    photos, wrong, titles = {}, [], {}
    print("| 사진 | 정답 칸 | " + " | ".join(name for _, name, *_ in SETS) + " | Sonnet 지연 | Sonnet 출력 (추론) | Sonnet 청구액 |")
    print("|---|---|" + "---|" * (len(SETS) + 3))
    for stem in stems:
        cells, row = [], {}
        for key, _, folder, pattern in SETS:
            path = folder / pattern.format(stem=stem)
            if not path.exists():
                cells.append("–")
                continue
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("rows") is None:
                cells.append("실패")
                totals[key]["failed"] += 1
                continue
            s = ladder.score_rows(labels[stem], record["rows"])
            row[key] = {k: s[k] for k in KEYS}
            totals[key].update({k: s[k] for k in KEYS})
            totals[key].update({f"kind_{k}": v for k, v in s["kinds"].items()})
            totals[key]["records"] += 1
            usage[key].append(usage_of(key, record))
            cells.append(f"{s['ok']}/{s['wrong']}/{s['missing']}/{s['name_only']}" + (f" +{s['extra']}" if s["extra"] else ""))
            if key == "sonnet":
                wrong += [{"photo": stem, **cell} for cell in s["wrong_cells"]]
                row["sonnet_usage"] = usage[key][-1]
            if stem == fallback.TITLE_PHOTO:
                checked = fallback.check_titles(labels[stem], record["rows"], title_lines)
                titles[key] = sum(not t["attached"] for t in checked)
        u = row.get("sonnet_usage")
        tail = "– | – | –" if u is None else f"{u['latency_s']:.1f}초 | {u['output']} ({u['thought']}) | ${u['cost']:.4f}"
        print(f"| {stem} | {sum(ladder.score.price_checked(g) for g in labels[stem])} | " + " | ".join(cells) + f" | {tail} |")
        photos[stem] = row

    summary = {"photos": photos, "totals": {k: dict(v) for k, v in totals.items()}, "titles_missing": titles,
               "sonnet_wrong_cells": wrong, "usage": {}}
    print()
    for key, name, *_ in SETS:
        rows = usage[key]
        if not rows:
            continue
        latency, cost = [r["latency_s"] for r in rows], [r["cost"] or 0 for r in rows]
        thought = [r["thought"] or 0 for r in rows]
        summary["usage"][key] = {
            "records": len(rows), "latency_median_s": round(statistics.median(latency), 1),
            "latency_p95_s": round(fallback.percentile95(latency), 1), "latency_max_s": round(max(latency), 1),
            "cost_total": round(sum(cost), 4), "cost_per_photo": round(sum(cost) / len(cost), 4),
            "input_mean": round(statistics.mean(r["input"] for r in rows)), "output_mean": round(statistics.mean(r["output"] for r in rows)),
            "thought_mean": round(statistics.mean(thought)), "records_without_reasoning": sum(1 for t in thought if not t),
            "providers": dict(Counter(str(r["provider"]) for r in rows))}
        print(f"{name}: totals {dict(totals[key])}; titles missing {titles.get(key)}; usage {summary['usage'][key]}")
    for cell in wrong:
        print("Sonnet wrong:", cell)
    if args.out:
        args.out.write_bytes(json.dumps(summary, ensure_ascii=False, indent=1).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
