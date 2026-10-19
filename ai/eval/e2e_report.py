# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, E2E). Reviewed by Jinwoo Park.
"""Numbers for ai/runs/<date>_e2e/README.md (ai/docs/e2e_plan.md). No API calls.

    python ai/eval/e2e_report.py --e2e ai/runs/2026-10-14_e2e > ai/runs/2026-10-14_e2e/report_numbers.json

Extraction table (E1 / CLOVA+LLM / hybrid, test, labels v1.1), source_lines accuracy and the
missed-output check of the hybrid run, and the end-to-end matching table from e2e_match.py
outputs in <e2e>/match/. Run directories of other tasks are only read (their scores.json is
not rewritten).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "ocr"))

from score import (RUN_FILE, levenshtein, load_bars, load_labels, load_photo_map, match_photo,  # noqa: E402
                   normalize, price_checked, score_photo, score_run_dir)

SOURCES = {
    "E1": REPO_ROOT / "ai" / "runs" / "2026-10-13_test_v2_A2",
    "CLOVA+LLM": REPO_ROOT / "ai" / "runs" / "2026-10-14_p12_clova" / "test_v3_parse",
}
CLYNELISH = "크라이넬리시 14년"
LINE = re.compile(r"^(L\d{3,}) \[(\d+),(\d+),(\d+),(\d+)\] ?(.*)$")


def records(run_dir: Path, stem_to_id: dict) -> dict[int, dict[str, dict]]:
    out: dict[int, dict[str, dict]] = {}
    for f in sorted(run_dir.glob("*_r*.json")):
        m = RUN_FILE.match(f.name)
        if m and m["stem"] in stem_to_id:
            out.setdefault(int(m["run"]), {})[stem_to_id[m["stem"]]] = json.loads(f.read_text(encoding="utf-8"))
    return out


def extraction_table(run_dirs: dict, labels, stem_to_id, bars) -> dict:
    table = {}
    for name, run_dir in run_dirs.items():
        sc = score_run_dir(run_dir, labels, stem_to_id, bars=bars)
        recs = records(run_dir, stem_to_id)
        per_run = {}
        for r, run in sc["runs"].items():
            photos = {p["photo_id"]: p for p in run["photos"]}
            b4 = photos["012_Beck_04"]
            forest = "013_포레스트_01"
            gt = labels[forest]
            out = (recs[r][forest].get("output") or {"items": []})["items"]
            pairs, _, _ = match_photo(gt, out)
            gi = next(i for i, g in enumerate(gt) if g["raw_name"] == CLYNELISH)
            hit = [out[oi] for g, oi, _ in pairs if g == gi]
            gem = [rec.get("latency_ms") for rec in recs[r].values() if rec.get("latency_ms")]
            ocr = [rec.get("ocr_latency_ms") for rec in recs[r].values() if rec.get("ocr_latency_ms")]
            per_run[r] = {
                "item_accuracy": run["total"]["item_accuracy"], "price_accuracy": run["total"]["price_accuracy"],
                "f1_strict": run["total"]["f1_strict"], "fp": run["total"]["fp"], "fn": run["total"]["fn"],
                "beck_04": b4["correct"] / (b4["n_gt"] + b4["fp"]),
                "clynelish": {"out": hit[0]["raw_name"] if hit else None,
                              "price": hit[0]["price_krw"] if hit else None,
                              "correct": bool(hit) and hit[0]["price_krw"] == gt[gi]["price_krw"]
                              and hit[0]["raw_name"].replace(" ", "") == CLYNELISH.replace(" ", ""),
                              "near": [it["raw_name"] for it in out if "크라이" in it["raw_name"]]},
                "gemini_latency_s": statistics.mean(gem) / 1000 if gem else None,
                "ocr_latency_s": statistics.mean(ocr) / 1000 if ocr else 0.0,
                "tokens": {k: statistics.mean(rec.get(k) or 0 for rec in recs[r].values())
                           for k in ("input_tokens", "output_tokens", "thought_tokens")},
            }
        table[name] = {"runs": per_run, "summary": sc["summary"], "per_photo": sc["per_photo_accuracy"],
                       "per_bar": sc["per_bar_accuracy"]}
    return table


# ---------- source_lines ----------

def parse_lines(user_text: str) -> dict[str, dict]:
    out = {}
    for row in user_text.splitlines():
        m = LINE.match(row)
        if m:
            out[m[1]] = {"box": tuple(int(m[i]) for i in range(2, 6)), "text": m[6]}
    return out


def fuzzy_in(p: str, t: str) -> bool:
    """p is inside t with at most max(1, 10% of len(p)) edits (approximate substring)."""
    if not p:
        return False
    k = max(1, round(0.1 * len(p)))
    prev = [0] * (len(t) + 1)
    for i, cp in enumerate(p, 1):
        cur = [i]
        for j, ct in enumerate(t, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cp != ct)))
        prev = cur
    return min(prev) <= k


def name_part(text: str) -> str:
    from hybrid import price_like
    return normalize(" ".join(tok for tok in text.split() if not price_like(tok)))


def price_values(text: str) -> set[int]:
    vals = set()
    for tok in re.findall(r"\d[\d,.]*\d|\d", text):
        cands = []
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", tok):
            cands.append(float(re.sub(r"[.,]", "", tok)))
        try:
            cands.append(float(tok.replace(",", "")))
        except ValueError:
            pass
        for c in cands:
            for mult in (1, 1000, 10000):
                vals.add(round(c * mult))
    return vals


def source_accuracy(run_dir: Path, labels, stem_to_id, run: int = 1) -> dict:
    counts = {"pairs": 0, "name_cited": 0, "name_precise": 0, "name_full": 0,
              "priced": 0, "price_cited": 0, "price_number": 0, "price_row": 0}
    examples = {"name_not_full": [], "price_wrong": []}
    for pid, rec in records(run_dir, stem_to_id)[run].items():
        lines = parse_lines(rec["user_text"])
        gt, out = labels[pid], rec["output"]["items"]
        pairs, _, _ = match_photo(gt, out)
        for gi, oi, _ in pairs:
            g, o = gt[gi], out[oi]
            src = o["source_lines"]
            counts["pairs"] += 1
            label = normalize(g["raw_name"])
            names = [lines[i] for i in src["name"] if i in lines]
            if names:
                counts["name_cited"] += 1
                # each line as printed, or with price tokens dropped (a price on the same OCR line)
                precise = all(fuzzy_in(normalize(ln["text"]), label) or fuzzy_in(name_part(ln["text"]), label)
                              for ln in names)
                k = max(1, round(0.1 * len(label)))
                orders = (names, sorted(names, key=lambda ln: (ln["box"][1], ln["box"][0])))
                joined = ["".join(f(ln["text"]) for ln in order) for order in orders for f in (normalize, name_part)]
                full = precise and min(levenshtein(j, label) for j in joined) <= k
                counts["name_precise"] += precise
                counts["name_full"] += full
                if not full and len(examples["name_not_full"]) < 15:
                    examples["name_not_full"].append({"photo": pid, "label": g["raw_name"], "out": o["raw_name"],
                                                      "cited": [ln["text"] for ln in names]})
            if price_checked(g):
                counts["priced"] += 1
                plines = [(i, lines[i]) for i in src["price"] if i in lines]
                counts["price_cited"] += bool(plines)
                ok = [ln for _, ln in plines if g["price_krw"] in price_values(ln["text"])]
                counts["price_number"] += bool(ok)
                row = False
                if ok and names:
                    last = lines[src["name"][-1]] if src["name"][-1] in lines else names[-1]
                    h = last["box"][3] - last["box"][1] or 1
                    cy = (last["box"][1] + last["box"][3]) / 2
                    row = any(abs((ln["box"][1] + ln["box"][3]) / 2 - cy) <= 1.5 * h for ln in ok)
                counts["price_row"] += row
                if not row and len(examples["price_wrong"]) < 15:
                    examples["price_wrong"].append({"photo": pid, "label": g["raw_name"], "price": g["price_krw"],
                                                    "cited": [ln["text"] for _, ln in plines], "number_ok": bool(ok)})
    rates = {
        "name_precise": counts["name_precise"] / counts["pairs"], "name_full": counts["name_full"] / counts["pairs"],
        "price_number": counts["price_number"] / counts["priced"], "price_row": counts["price_row"] / counts["priced"],
    }
    return {"counts": counts, "rates": rates, "examples": examples}


def missed_check(run_dir: Path, labels, stem_to_id) -> list[dict]:
    rows = []
    for r, recs in sorted(records(run_dir, stem_to_id).items()):
        for pid, rec in sorted(recs.items()):
            sc = rec.get("source_check") or {}
            s = score_photo(labels[pid], (rec.get("output") or {"items": []})["items"], pid)
            lines = parse_lines(rec.get("user_text", ""))
            rows.append({"run": r, "photo": pid, "items": s["n_out"], "labels": s["n_gt"], "fn": s["fn"],
                         "uncited": sc.get("uncited_price_lines"), "price_lines": sc.get("price_like_lines"),
                         "flag": sc.get("flag_missing"), "real_miss": s["fn"] >= 0.3 * s["n_gt"] if s["n_gt"] else False,
                         "uncited_text": [lines[i]["text"] for i in sc.get("uncited", []) if i in lines][:12]})
    return rows


# ---------- matching ----------

def match_table(e2e: Path) -> dict:
    out = {}
    for f in sorted((e2e / "match").glob("*.json")):
        if f.name.endswith(".paired_gold.json"):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        rows = {}
        for r in d["results"]:
            pp = list(r["per_photo"].values())
            cr = r["confirm_recommended_by_source"]
            rows[f"{r['matcher']}/{r['condition']}"] = {
                "lines": r["lines"], "top1": r["known_top1"], "e2e_top1": r["e2e_top1"]["top1"],
                "fm": r["false_merge_rate"], **r["owner_burden_totals"],
                "rule": f"{cr['rule']['correct']}/{cr['rule']['n']}", "llm": f"{cr['llm']['correct']}/{cr['llm']['n']}",
                "accept_err": r["accept_error_rate"],
                "a_per_photo": statistics.mean(x["a"] for x in pp),
                "bcd_per_photo": statistics.mean(x["bcd"] for x in pp),
                "unpaired_unconfirmed_per_photo": statistics.mean(x["unpaired_unconfirmed"] for x in pp),
                "missed_per_photo": statistics.mean(x["missed"] for x in pp),
                "unpaired": (r["unpaired"] or {}).get("counts"),
            }
        out[f.stem] = {"counts": d["counts"], "llm": d["llm"], "rows": rows,
                       "unpaired_title": unpaired_title(d)}
    return out


def unpaired_title(d: dict) -> dict:
    """Unpaired lines whose name is the end of a missed gold line of the same photo (title missing)
    or contains it (title added): the brand-title pattern of P11/P12."""
    n = title = 0
    examples = []
    for pid, p in d["lines"].items():
        missed = [g for g in p["gold_lines"] if not g["extracted"]]
        for r in p["lines"]:
            if r["gold"] is not None:
                continue
            n += 1
            x = normalize(r["name"])
            hit = next((g for g in missed if normalize(g["name"]).endswith(x) or x.endswith(normalize(g["name"]))
                        or (len(x) >= 4 and x in normalize(g["name"]))), None)
            if hit:
                title += 1
                if len(examples) < 8:
                    examples.append({"photo": pid, "extracted": r["name"], "gold_line": hit["name"]})
    return {"unpaired": n, "title_pattern": title, "examples": examples}


def main() -> None:
    from extract import data_dir
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--e2e", type=Path, required=True)
    args = parser.parse_args()
    labels = load_labels("test_v1_1")
    bars = load_bars("test_v1_1")
    stem_to_id = load_photo_map(data_dir(), "test")
    hybrid_dir = args.e2e / "hybrid_test_v1"
    out = {
        "extraction": extraction_table({**SOURCES, "hybrid": hybrid_dir}, labels, stem_to_id, bars),
        "source_lines": {r: source_accuracy(hybrid_dir, labels, stem_to_id, r) for r in (1, 2, 3)},
        "missed_check": missed_check(hybrid_dir, labels, stem_to_id),
        "matching": match_table(args.e2e),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
