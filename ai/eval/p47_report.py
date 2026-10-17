# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-17, P47). Reviewed by Jinwoo Park.
"""P47 numbers from the run outputs (ai/docs/p47_plan.md, 4절·5절). Reads files only, no API call.

    python ai/eval/p47_report.py ai/runs/2026-10-17_p47

Inputs in the run root: hybrid_final_v1/ (records + scores.json from score.py --set final),
e2e_hybrid_r1.json, e2e_label.json, e2e_hybrid_r1_drop_products.json, m3_cache/. Writes
report_numbers.json there. Everything is split by bar (수이, 오드비) and totalled. Matcher rows
are M3a (S1+S2b+S3, then M3a merge) on the catalog snapshot as is (C0).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))

from match_eval import gold_refs  # noqa: E402
from score import aggregate, load_bars  # noqa: E402

BARS = ("수이", "오드비")
# p47_plan.md 5절: known limitations, by gold product key (prefix) or menu name
LIMITS = {
    "age_null": ("카탈로그 연수 null (Knob Creek)", lambda g, n: "knob-creek" in gold_refs(g)),
    "age_inconsistent": ("연수 규칙 불일치 (Glenmorangie The Original)",
                         lambda g, n: "glenmorangie-original" in gold_refs(g)),
    "new_bottler": ("병입사 목록에 없는 새 독립병입사", lambda g, n: "SANSIBAR" in n or any(
        r.removeprefix("new:").startswith(p) for r in gold_refs(g)
        for p in ("nectar-", "maltman-", "eld-vatten-", "kimgwajang-", "jack-wiebers-", "aqua-vitae-",
                  "craft-bros-", "north-star-"))),
    "bottler_missing_menu": ("메뉴에 병입사 없는 Douglas Laing 병입",
                             lambda g, n: any(r.removeprefix("new:").startswith("dl-") for r in gold_refs(g))),
}


def pct(values: list[float], q: float) -> float:
    """Nearest-rank percentile."""
    s = sorted(values)
    return s[max(0, min(len(s) - 1, int(round(q / 100 * len(s) + 0.5)) - 1))]


def lat_stats(values: list[float]) -> dict:
    return {"n": len(values), "mean": statistics.mean(values), "p50": statistics.median(values),
            "p95": pct(values, 95)} if values else None


def m3a(e2e: dict) -> dict:
    return next(r for r in e2e["results"] if r["matcher"] == "M3a" and r["condition"] == "C0")


def matching(e2e: dict, photos_by_bar: dict) -> dict:
    r = m3a(e2e)
    wrong = {(e["photo_id"], e["name"]) for e in r["errors"]}
    out = {}
    for bar, pids in {**photos_by_bar, "전체": [p for v in photos_by_bar.values() for p in v]}.items():
        known = correct = known_p = correct_p = 0
        for pid in pids:
            p = e2e["lines"][pid]
            for g in p["gold_lines"]:
                if g["gold"] in ("unknown", "non_whisky") or any(x.startswith("new:") for x in gold_refs(g["gold"])):
                    continue
                known += 1
                correct += any((pid, n) not in wrong for n in g["extracted"])
            for line in p["lines"]:  # paired lines (Top-1 on paired lines, match_eval definition)
                g = line["gold"]
                if g is None or g in ("unknown", "non_whisky") or any(x.startswith("new:") for x in gold_refs(g)):
                    continue
                known_p += 1
                correct_p += (pid, line["name"]) not in wrong
        oc = Counter()
        for bname, c in r["by_bar"].items():
            if bar == "전체" or bname == bar:
                oc.update(c)
        lines = sum(oc.values())
        pp = [r["per_photo"][pid] for pid in pids]
        kinds = [r["owner_burden_by_kind"].get(pid, {}) for pid in pids]
        n = len(pids)
        per_photo = {k: sum(x.get(k, 0) for x in kinds) / n for k in ("confirm", "choose", "register", "wrong")}
        per_photo["missed"] = sum(x["missed"] for x in pp) / n
        per_photo["unpaired_unconfirmed"] = sum(x["unpaired_unconfirmed"] for x in pp) / n
        out[bar] = {
            "photos": n, "lines": lines, "outcomes": dict(oc),
            "known_gold_lines": known, "e2e_top1_correct": correct, "e2e_top1": correct / known if known else None,
            "paired_known": known_p, "paired_top1": correct_p / known_p if known_p else None,
            "false_merge": oc["false_merge"], "overconfident": oc["overconfident"],
            "false_merge_rate": (oc["false_merge"] + oc["overconfident"]) / lines if lines else None,
            "burden_totals": {k: sum(x.get(k, 0) for x in kinds) for k in ("confirm", "choose", "register", "wrong")},
            "missed_total": sum(x["missed"] for x in pp),
            "unpaired_unconfirmed_total": sum(x["unpaired_unconfirmed"] for x in pp),
            "per_photo": per_photo,
        }
    return out


def limit_rows(e2e: dict, label: dict) -> list[dict]:
    rows = []
    res = {name: {(e["photo_id"], e["name"]): e for e in m3a(d)["errors"]} for name, d in
           (("e2e", e2e), ("label", label))}
    m3_lines = {name: {(x["photo_id"], x["name"]): x for x in m3a(d)["m3_lines"]} for name, d in
                (("e2e", e2e), ("label", label))}
    for pid, p in e2e["lines"].items():
        for g in p["gold_lines"]:
            tags = [k for k, (_, f) in LIMITS.items() if f(g["gold"], g["name"])]
            if not tags:
                continue
            row = {"photo_id": pid, "gold_line": g["name"], "gold": g["gold"], "limits": tags,
                   "extracted_as": g["extracted"]}
            le = res["label"].get((pid, g["name"]))
            row["label_outcome"] = le["outcome"] if le else "correct"
            row["label_vetoes"] = (m3_lines["label"].get((pid, g["name"])) or {}).get("vetoes")
            if not g["extracted"]:
                row["e2e_outcome"] = "missed"
            else:
                outs = [res["e2e"].get((pid, n)) for n in g["extracted"]]
                row["e2e_outcome"] = ",".join(o["outcome"] if o else "correct" for o in outs)
                row["e2e_vetoes"] = [(m3_lines["e2e"].get((pid, n)) or {}).get("vetoes") for n in g["extracted"]]
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root
    bars = load_bars("final")
    photos_by_bar = {b: sorted(p for p, x in bars.items() if x == b) for b in BARS}

    # extraction (score.py output, r1)
    scores = json.loads((root / "hybrid_final_v1" / "scores.json").read_text(encoding="utf-8"))
    run1 = scores["runs"]["1"]
    extraction = {b: aggregate([p for p in run1["photos"] if bars[p["photo_id"]] == b]) for b in BARS}
    extraction["전체"] = run1["total"]

    e2e = json.loads((root / "e2e_hybrid_r1.json").read_text(encoding="utf-8"))
    label = json.loads((root / "e2e_label.json").read_text(encoding="utf-8"))
    drop = json.loads((root / "e2e_hybrid_r1_drop_products.json").read_text(encoding="utf-8"))

    # latency per photo: CLOVA (recorded in the cache) + hybrid Gemini + M3a (0 when not called)
    recs = {}
    for f in sorted((root / "hybrid_final_v1").glob("*_r1*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        recs[rec["source_image"]] = rec
    from score import load_photo_map
    sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
    from extract import data_dir
    id_of = {f"{stem}": pid for stem, pid in load_photo_map(data_dir(), "final").items()}
    m3_lat = {}
    for pid, info in e2e["m3_photos"].items():
        if info.get("called"):
            c = json.loads((root / "m3_cache" / f"{info['cache_key']}.json").read_text(encoding="utf-8"))
            m3_lat[pid] = c["meta"]["latency_ms"]
    latency = defaultdict(lambda: defaultdict(list))
    tokens = defaultdict(list)
    for name, rec in recs.items():
        pid = id_of[Path(name).stem]
        parts = {"clova": rec["ocr_latency_ms"], "gemini": rec.get("latency_ms"), "m3a": m3_lat.get(pid, 0)}
        for scope in (bars[pid], "전체"):
            for k, v in parts.items():
                if v is not None:
                    latency[scope][k].append(v / 1000)
            if rec.get("latency_ms") is not None:
                latency[scope]["total"].append(sum(parts.values()) / 1000)
        for k in ("input_tokens", "output_tokens", "thought_tokens"):
            if rec.get(k) is not None:
                tokens[k].append(rec[k])
    latency_out = {s: {k: lat_stats(v) for k, v in d.items()} for s, d in latency.items()}
    latency_out["m3a_called_only"] = lat_stats([v / 1000 for v in m3_lat.values()])

    drop_r = m3a(drop)
    out = {
        "extraction": extraction,
        "extraction_flags": {name: rec.get("source_check") for name, rec in recs.items()},
        "hybrid_attempts": {name: rec.get("attempts") for name, rec in recs.items()},
        "tokens_per_call_mean": {k: statistics.mean(v) for k, v in tokens.items()},
        "matching_e2e": matching(e2e, photos_by_bar),
        "matching_label": matching(label, photos_by_bar),
        "counts_e2e": e2e["counts"], "counts_label": label["counts"],
        "unpaired_e2e": m3a(e2e)["unpaired"],
        "confirm_recommended": {"e2e": m3a(e2e)["confirm_recommended_by_source"],
                                "label": m3a(label)["confirm_recommended_by_source"]},
        "accept_error_rate": {"e2e": m3a(e2e)["accept_error_rate"], "label": m3a(label)["accept_error_rate"]},
        "s1s3_only": {name: {k: v for k, v in next(r for r in d["results"] if r["matcher"] == "S1+S2b+S3").items()
                             if k in ("known_top1", "e2e_top1", "false_merge_rate", "owner_burden_totals")}
                      for name, d in (("e2e", e2e), ("label", label))},
        "latency_s": latency_out,
        "llm": {"e2e": e2e["llm"], "label": label["llm"], "drop_products": drop["llm"]},
        "drop_products": {"by_kind": drop_r["by_kind"], "by_bar": drop_r["by_bar"],
                          "matching": matching(drop, photos_by_bar),
                          "absent_lines": [e for e in drop_r["errors"] if e["kind"] == "absent"]},
        "known_limitations": limit_rows(e2e, label),
    }
    (root / "report_numbers.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str),
                                              encoding="utf-8", newline="\n")
    print(json.dumps({k: out[k] for k in ("extraction", "matching_e2e", "matching_label", "latency_s",
                                          "tokens_per_call_mean")}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
