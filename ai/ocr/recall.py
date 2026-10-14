# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, P12). Reviewed by Jinwoo Park.
"""Stage 1: how much of the label text exists in the OCR output (ai/docs/p12_plan.md).

    python ai/ocr/recall.py --set val
    python ai/ocr/recall.py --set test --e1 ai/runs/2026-10-13_test_v2_A2

Name recall (exact / approximate / one-line) and price recall (multiset) per
photo, per bar and overall. Only presence is checked, not which price goes with
which name. With --e1, the same measure is applied to the E1 Vision LLM outputs
(their raw_name / price_krw as the "text"), averaged over runs.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
from score import RUN_FILE, load_bars, load_labels, load_photo_map, normalize, price_checked  # noqa: E402

TOKEN_SPLIT = re.compile(r"[\s/()\[\]]+")
PRICE_PIECE_SPLIT = re.compile(r"[\s/|~]+")
PRICE_TOKEN = re.compile(r"[₩\\]?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(원|k|K)?")
APPROX_MIN_LEN = 3  # non-digit part shorter than this: exact only


# ---------- names ----------

def name_candidates(raw_name: str) -> list[list[str]]:
    """Token lists for the whole name and each slash part (like score.candidates)."""
    parts = [raw_name] + (raw_name.split("/") if "/" in raw_name else [])
    out = []
    for p in parts:
        toks = [t for t in (normalize(x) for x in TOKEN_SPLIT.split(p)) if t]
        if toks and toks not in out:
            out.append(toks)
    return out


def substring_distance(pattern: str, text: str) -> int:
    """Smallest edit distance between `pattern` and any substring of `text` (Sellers)."""
    if not pattern:
        return 0
    prev = [0] * (len(text) + 1)
    for i, pc in enumerate(pattern, 1):
        cur = [i] + [0] * len(text)
        for j, tc in enumerate(text, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (pc != tc))
        prev = cur
    return min(prev)


class Text:
    """Normalized photo text S, its digit-free copy, and normalized lines."""

    def __init__(self, pieces: list[str], lines: list[str] | None = None):
        self.s = "".join(normalize(p) for p in pieces)
        self.s_nodigit = re.sub(r"\d+", "", self.s)
        self.lines = [normalize(x) for x in (lines if lines is not None else pieces)]
        self._approx: dict[str, bool] = {}

    def token_exact(self, tok: str) -> bool:
        return tok in self.s

    def token_approx(self, tok: str) -> bool:
        if tok in self.s:
            return True
        if tok not in self._approx:
            rest = re.sub(r"\d+", "", tok)
            ok = (all(d in self.s for d in re.findall(r"\d+", tok))
                  and len(rest) >= APPROX_MIN_LEN
                  and substring_distance(rest, self.s_nodigit) <= 1)
            self._approx[tok] = ok
        return self._approx[tok]

    def name_found(self, raw_name: str, approx: bool) -> bool:
        check = self.token_approx if approx else self.token_exact
        return any(all(check(t) for t in toks) for toks in name_candidates(raw_name))

    def name_in_one_line(self, raw_name: str) -> bool:
        whole = ["".join(toks) for toks in name_candidates(raw_name)]
        return any(w in line for w in whole for line in self.lines)


# ---------- prices ----------

def price_values(text: str) -> list[set[int]]:
    """Candidate KRW values for each price-like piece of one OCR field."""
    out = []
    for piece in PRICE_PIECE_SPLIT.split(text.strip()):
        m = PRICE_TOKEN.fullmatch(piece)
        if not m:
            continue
        v = float(m[1].replace(",", "") + (m[2] or ""))
        if m[3] in ("k", "K"):
            v *= 1000
        out.append({int(v)} if v >= 1000 else {round(v * 1000), round(v * 10000)})
    return [s for s in out if all(x > 0 for x in s)]


def price_matches(prices: list[int], tokens: list[set[int]]) -> int:
    """Maximum 1:1 matching of label prices to OCR price tokens (Kuhn)."""
    owner: dict[int, int] = {}

    def augment(pi: int, seen: set[int]) -> bool:
        for ti, vals in enumerate(tokens):
            if prices[pi] in vals and ti not in seen:
                seen.add(ti)
                if ti not in owner or augment(owner[ti], seen):
                    owner[ti] = pi
                    return True
        return False

    return sum(augment(pi, set()) for pi in range(len(prices)))


# ---------- scoring ----------

def recall_photo(gt: list[dict], text: Text, price_tokens: list[set[int]], photo_id: str = "") -> dict:
    exact = [text.name_found(g["raw_name"], approx=False) for g in gt]
    approx = [text.name_found(g["raw_name"], approx=True) for g in gt]
    one_line = [text.name_in_one_line(g["raw_name"]) for g in gt]
    prices = [g["price_krw"] for g in gt if price_checked(g)]
    # dedupe same-name items (glass/bottle rows share a name) for the missed list
    missed = list(dict.fromkeys(g["raw_name"] for g, ok in zip(gt, approx) if not ok))
    return {
        "photo_id": photo_id,
        "n_items": len(gt),
        "name_exact": sum(exact),
        "name_approx": sum(approx),
        "name_one_line": sum(one_line),
        "n_priced": len(prices),
        "price_found": price_matches(prices, price_tokens),
        "missed_names": missed,
    }


def totals(photos: list[dict]) -> dict:
    s = defaultdict(int)
    for p in photos:
        for k in ("n_items", "name_exact", "name_approx", "name_one_line", "n_priced", "price_found"):
            s[k] += p[k]
    n, np_ = s["n_items"], s["n_priced"]
    return {**s,
            "name_exact_recall": s["name_exact"] / n if n else None,
            "name_approx_recall": s["name_approx"] / n if n else None,
            "name_one_line_recall": s["name_one_line"] / n if n else None,
            "price_recall": s["price_found"] / np_ if np_ else None}


def by_bar(photos: list[dict], bars: dict[str, str]) -> dict[str, dict]:
    groups = defaultdict(list)
    for p in photos:
        groups[bars[p["photo_id"]]].append(p)
    return {b: totals(ps) for b, ps in sorted(groups.items())}


def ocr_inputs(response: dict) -> tuple[Text, list[set[int]]]:
    from lines import build_lines, field_texts
    fields = field_texts(response)
    text = Text(fields, [line.text for line in build_lines(response)])
    tokens = [v for f in fields for v in price_values(f)]
    return text, tokens


def e1_inputs(items: list[dict]) -> tuple[Text, list[set[int]]]:
    names = [it["raw_name"] for it in items]
    return Text(names), [{it["price_krw"]} for it in items if it.get("price_krw")]


def recall_ocr(labels: dict, stem_to_id: dict, bars: dict, variant: str = "off") -> dict:
    from clova import load_cached
    photos, missing = [], []
    for stem, pid in sorted(stem_to_id.items(), key=lambda kv: kv[1]):
        rec = load_cached(stem, variant)
        if rec is None:
            missing.append(stem)
            continue
        text, tokens = ocr_inputs(rec["response"])
        photos.append(recall_photo(labels[pid], text, tokens, pid))
    return {"source": f"clova table-{variant}", "missing_cache": missing,
            "total": totals(photos), "per_bar": by_bar(photos, bars), "photos": photos}


def recall_e1(run_dir: Path, labels: dict, stem_to_id: dict, bars: dict) -> dict:
    by_run: dict[int, list[dict]] = defaultdict(list)
    for f in sorted(run_dir.glob("*_r*.json")):
        m = RUN_FILE.match(f.name)
        if not m or m["stem"] not in stem_to_id:
            continue
        pid = stem_to_id[m["stem"]]
        out = json.loads(f.read_text(encoding="utf-8")).get("output") or {"items": []}
        text, tokens = e1_inputs(out["items"])
        by_run[int(m["run"])].append(recall_photo(labels[pid], text, tokens, pid))
    runs = {r: {"total": totals(ps), "per_bar": by_bar(ps, bars)} for r, ps in sorted(by_run.items())}

    def mean(get):
        vals = [get(r) for r in runs.values()]
        vals = [v for v in vals if v is not None]
        return statistics.mean(vals) if vals else None

    keys = ("name_exact_recall", "name_approx_recall", "name_one_line_recall", "price_recall")
    bar_names = sorted({b for r in runs.values() for b in r["per_bar"]})
    return {"source": f"E1 {run_dir.name}", "n_runs": len(runs),
            "total": {k: mean(lambda r, k=k: r["total"][k]) for k in keys},
            "per_bar": {b: {k: mean(lambda r, k=k, b=b: r["per_bar"][b][k]) for k in keys}
                        for b in bar_names},
            "runs": runs}


def fmt(v):
    return "-" if v is None else f"{v:.3f}"


def main() -> None:
    from extract import data_dir

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", dest="label_set", choices=["val", "test"], default="val")
    parser.add_argument("--variant", default="off", choices=["off", "on"])
    parser.add_argument("--e1", type=Path, help="E1 run directory to measure the same way")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    labels = load_labels(args.label_set)
    bars = load_bars(args.label_set)
    stem_to_id = load_photo_map(data_dir(), args.label_set)
    result = {"label_set": args.label_set, "clova": recall_ocr(labels, stem_to_id, bars, args.variant)}
    if args.e1:
        result["e1"] = recall_e1(args.e1, labels, stem_to_id, bars)

    out = REPO_ROOT / "ai" / "runs" / f"{args.date}_p12_clova" / f"recall_{args.label_set}_table-{args.variant}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    c = result["clova"]
    if c["missing_cache"]:
        print(f"missing OCR cache: {c['missing_cache']}")
    print(f"| 사진 | 항목 | 이름 완전 | 이름 근사 | 한 줄 | 가격 |\n| --- | --- | --- | --- | --- | --- |")
    for p in c["photos"]:
        n, np_ = p["n_items"], p["n_priced"]
        r = lambda k, d: fmt(p[k] / d if d else None)  # noqa: E731
        print(f"| {p['photo_id']} | {n} | {r('name_exact', n)} | {r('name_approx', n)} | "
              f"{r('name_one_line', n)} | {r('price_found', np_)} |")
    for bar, t in c["per_bar"].items():
        print(f"| [바] {bar} | {t['n_items']} | {fmt(t['name_exact_recall'])} | {fmt(t['name_approx_recall'])} | "
              f"{fmt(t['name_one_line_recall'])} | {fmt(t['price_recall'])} |")
    t = c["total"]
    print(f"| **전체 CLOVA** | {t['n_items']} | {fmt(t['name_exact_recall'])} | {fmt(t['name_approx_recall'])} | "
          f"{fmt(t['name_one_line_recall'])} | {fmt(t['price_recall'])} |")
    if args.e1:
        e = result["e1"]["total"]
        print(f"| E1 대조 ({result['e1']['n_runs']}회 평균) | | {fmt(e['name_exact_recall'])} | "
              f"{fmt(e['name_approx_recall'])} | {fmt(e['name_one_line_recall'])} | {fmt(e['price_recall'])} |")
    print(f"\nwrote {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
