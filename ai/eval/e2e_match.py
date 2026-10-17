# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, E2E; 2026-10-17, P47 final split). Reviewed by Jinwoo Park.
"""End-to-end matching: extraction output -> S1+S2b+S3 -> M3a (ai/docs/e2e_plan.md, 2절).

    python ai/eval/e2e_match.py --source label --split test \
        --m3-cache ai/runs/2026-10-14_m3/cache --cache-only --json <out>          # label input (baseline)
    python ai/eval/e2e_match.py --source ai/runs/2026-10-13_test_v2_A2 --run 1 --split test \
        --m3-cache ai/runs/<date>_e2e/m3_cache --json <out>                       # one extraction run
    python ai/eval/e2e_match.py ... --split dev --bars Beck                        # Beck (dev, supplementary)
    python ai/eval/e2e_match.py --source <hybrid final run dir> --split final         [--catalog drop_products] --m3-cache <dir> --json <out>                  # P47 (ai/docs/p47_plan.md)

Lines are the extracted raw_names of a photo in output order, glass/bottle items once.
Extracted items are paired with the label v1.1 items by score.py (unit-aware strict, then
lenient, then the unit-free re-pairing score.py uses for 잔·병 혼동); label item i has the
gold of match gold item i. A line paired with any label item takes the gold of the first
one (label order). Paired lines are scored with match_eval.evaluate (same definitions as
the M3 report); unpaired lines (no label item) are resolved the same way and only their
outcome kinds are counted; gold lines with no paired item are "missed".

The matching code, prompts and rules are the frozen M3a (commit 1ace927) and are only
imported. M3a gets one call per photo for the lines S1+S2b+S3 leaves unconfirmed in C0 or
C1; the call cap is 60 per run (gemini-3.1-flash-lite).

Split "final" (P47, ai/docs/p47_plan.md): 수이·오드비 photos, labels_final_v1, match_gold_final_v1
and a catalog v2 snapshot in place of catalog_v1_draft (match_eval.SEED is pointed at it; the
matching code is unchanged). The eval_5bars snapshot already holds the gold products (C1 style),
so the gold refs new:<key> that the snapshot holds are read as the catalog product <key> and only
C0 (the snapshot as is) is evaluated. With --catalog drop_products the products seen only at
수이·오드비 are absent; their refs stay new:<key> ("absent", expected unmatched).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))

import match_eval  # noqa: E402
from match_eval import (CONFIRMED, M3_BASE, MATCHERS, check_labels_v1_1, gold_refs, load_catalog,  # noqa: E402
                        product_meta, split_new_products)
from score import load_labels, load_photo_map, match_photo  # noqa: E402

from app.matching.types import ExtractedProduct  # noqa: E402  (backend on sys.path via match_eval)

GOLD = REPO_ROOT / "eval" / "match_gold_v1_1.json"
FINAL_GOLD = REPO_ROOT / "eval" / "match_gold_final_v1.json"
FINAL_CATALOGS = {"eval_5bars": REPO_ROOT / "ai" / "catalog" / "catalog_v2_eval_5bars.json",
                  "drop_products": REPO_ROOT / "ai" / "catalog" / "catalog_v2_eval_5bars_drop_products.json"}
M3_CALL_LIMIT = 60  # gemini-3.1-flash-lite calls per run (e2e_plan.md)
RUN_FILE = re.compile(r"^(?P<stem>.+)_r(?P<run>\d+)\.json$")


def load_run(run_dir: Path, run: int, label_set: str = "test") -> dict[str, list[dict]]:
    """photo_id -> extracted items of run `run` (failed / unparseable calls -> [])."""
    from extract import data_dir
    stem_to_id = load_photo_map(data_dir(), label_set)
    out = {}
    for f in sorted(run_dir.glob(f"*_r{run}.json")):
        m = RUN_FILE.match(f.name)
        if not m or m["stem"] not in stem_to_id:
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))
        out[stem_to_id[m["stem"]]] = (rec.get("output") or {"items": []})["items"]
    return out


def final_gold(catalog_path: Path) -> dict:
    """match_gold_final_v1 with the new:<key> refs the catalog snapshot holds read as <key>."""
    gold = json.loads(FINAL_GOLD.read_text(encoding="utf-8"))
    keys = {p["key"] for p in json.loads(catalog_path.read_text(encoding="utf-8"))["products"]}
    missing = set()

    def ref(r: str) -> str:
        key = r.removeprefix("new:")
        if r.startswith("new:"):
            return key if key in keys else r
        if key not in keys:
            missing.add(r)
        return r

    for photo in gold["photos"]:
        for item in photo["items"]:
            g = item["gold"]
            if g in ("unknown", "non_whisky"):
                continue
            item["gold"] = ("both:" if g.startswith("both:") else "") + "|".join(ref(r) for r in gold_refs(g))
    if missing:
        raise SystemExit(f"gold refs not in {catalog_path.name}: {sorted(missing)}")
    return gold


def check_labels_final(gold: dict, labels: dict[str, list[dict]]) -> None:
    """Same check as check_labels_v1_1, against labels_final_v1."""
    for photo in gold["photos"]:
        if [i["raw_name"] for i in photo["items"]] != [i["raw_name"] for i in labels[photo["photo_id"]]]:
            raise SystemExit(f"{photo['photo_id']}: gold names differ from labels_final_v1")


def pair_items(labels: list[dict], items: list[dict]) -> dict[int, int]:
    """out index -> label index (score.py pairing, plus its unit-free re-pairing)."""
    pairs, gt_left, out_left = match_photo(labels, items, lenient=True)
    confusion, _, _ = match_photo(labels, items, lenient=True, use_unit=False, gt_free=gt_left, out_free=out_left)
    return {oi: gi for gi, oi, _ in pairs + confusion}


def build_lines(gold: dict, labels: dict, extracted: dict, photo_ids: list[str]) -> dict:
    """Per photo: extracted lines, their gold (paired) or None (unpaired), and missed gold lines."""
    out = {}
    for photo in gold["photos"]:
        pid = photo["photo_id"]
        if pid not in photo_ids:
            continue
        items = extracted.get(pid, [])
        to_label = pair_items(labels[pid], items)
        lines: dict[str, list[int]] = {}
        for oi, it in enumerate(items):
            lines.setdefault(it["raw_name"], [])
            if oi in to_label:
                lines[it["raw_name"]].append(to_label[oi])
        gold_items = photo["items"]
        rows, conflicts, covered = [], 0, defaultdict(set)
        for name, label_idx in lines.items():
            label_idx = sorted(set(label_idx))
            golds = list(dict.fromkeys(gold_items[i]["gold"] for i in label_idx))
            conflicts += len(golds) > 1
            for i in label_idx:
                covered[gold_items[i]["raw_name"]].add(name)
            rows.append({"name": name, "gold": golds[0] if golds else None,
                         "gold_lines": list(dict.fromkeys(gold_items[i]["raw_name"] for i in label_idx))})
        gold_lines = list(dict.fromkeys(i["raw_name"] for i in gold_items))
        gold_of = {i["raw_name"]: i["gold"] for i in reversed(gold_items)}
        out[pid] = {"bar": photo["bar"], "split": photo["split"], "lines": rows, "conflicts": conflicts,
                    "gold_lines": [{"name": n, "gold": gold_of[n], "extracted": sorted(covered.get(n, ()))}
                                   for n in gold_lines],
                    "n_items": len(items), "n_paired_items": len(to_label)}
    return out


def make_engine(llm, gold: dict, photo_lines: dict, in_split: set[str], conditions=("C0", "C1")):
    from m3 import M3
    engine = M3(llm, {pid: [r["name"] for r in p["lines"]] for pid, p in photo_lines.items()}, product_meta(gold))
    catalogs = {}
    for pid, p in photo_lines.items():
        targets = set()
        for condition in conditions:
            key = (p["bar"], condition)
            if key not in catalogs:
                catalogs[key] = load_catalog(p["bar"], condition, gold["new_products"], in_split)[0]
            for r in p["lines"]:
                res = MATCHERS[M3_BASE](ExtractedProduct(product_name=r["name"]), catalogs[key])
                if res.status not in CONFIRMED:
                    targets.add(r["name"])
        engine.translate(pid, targets)
    return engine, catalogs


def unpaired_outcomes(photo_lines: dict, engine, catalogs, condition: str) -> dict:
    """Outcome kinds of unpaired lines (no gold): confirmed / confirm_recommended / candidates / unmatched."""
    counts, rows = Counter(), []
    per_photo = Counter()
    for pid, p in photo_lines.items():
        catalog = catalogs[(p["bar"], condition)]
        for r in p["lines"]:
            if r["gold"] is not None:
                continue
            base = MATCHERS[M3_BASE](ExtractedProduct(product_name=r["name"]), catalog)
            res = base if base.status in CONFIRMED else engine.resolve(pid, r["name"], catalog, base, "merge", False)[0]
            if res.status in CONFIRMED:
                kind = "confirmed"
            elif res.status == "unmatched":
                kind = "unmatched"
            elif res.candidates[0].evidence.get("confirmRecommended"):
                kind = "confirm_recommended"
            else:
                kind = "candidates"
            counts[kind] += 1
            per_photo[pid] += res.status not in CONFIRMED
            rank1 = res.candidates[0].product_id if res.candidates else res.proposed_product_id
            rows.append({"photo_id": pid, "name": r["name"], "kind": kind, "status": res.status,
                         "rank1": engine.products[rank1].display_name if rank1 in engine.products else None,
                         "method": res.candidates[0].method if res.candidates else None})
    return {"counts": dict(counts), "unconfirmed_per_photo": dict(per_photo), "lines": rows}


def e2e_top1(photo_lines: dict, result: dict, condition: str) -> dict:
    """Known-product gold lines whose some paired extracted line is exact-correct (missed lines fail)."""
    wrong = {(e["photo_id"], e["name"]): e["outcome"] for e in result["errors"]}
    known = correct = 0
    for pid, p in photo_lines.items():
        for g in p["gold_lines"]:
            refs = gold_refs(g["gold"])
            if g["gold"] in ("unknown", "non_whisky") or (condition == "C0" and any(x.startswith("new:") for x in refs)):
                continue
            known += 1
            correct += any((pid, name) not in wrong for name in g["extracted"])
    return {"known_gold_lines": known, "correct": correct, "top1": correct / known if known else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, help='"label" or an extraction run directory')
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--split", default="test", choices=["dev", "test", "final"])
    parser.add_argument("--catalog", default="eval_5bars", choices=sorted(FINAL_CATALOGS),
                        help="final split: catalog v2 snapshot")
    parser.add_argument("--bars", nargs="+", help="only these bars (e.g. Beck on dev)")
    parser.add_argument("--m3-cache", type=Path, required=True)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--limit", type=int, default=M3_CALL_LIMIT)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    from llm import CachedLLM
    if args.split == "final":
        match_eval.SEED = FINAL_CATALOGS[args.catalog]
        gold = final_gold(match_eval.SEED)
        labels = load_labels("final")
        check_labels_final(gold, labels)
        conditions = ("C0",)
    else:
        gold = json.loads(GOLD.read_text(encoding="utf-8"))
        check_labels_v1_1(gold)
        labels = {**load_labels("val_v1_1"), **load_labels("test_v1_1")}
        conditions = ("C0", "C1")
    photo_ids = [p["photo_id"] for p in gold["photos"]
                 if p["split"] == args.split and (not args.bars or p["bar"] in args.bars)]
    if args.source == "label":
        extracted = {pid: labels[pid] for pid in photo_ids}
    else:
        extracted = load_run(Path(args.source), args.run, "final" if args.split == "final" else "test")
        missing = [pid for pid in photo_ids if pid not in extracted]
        if missing:
            print(f"WARNING: no record for {missing} (scored as empty)")
    in_split = split_new_products(gold, args.split)  # catalog C1 = the split's new products, as in M3
    photo_lines = build_lines(gold, labels, extracted, photo_ids)

    llm = CachedLLM(args.m3_cache, cache_only=args.cache_only, limit=args.limit)
    engine, catalogs = make_engine(llm, gold, photo_lines, in_split, conditions)

    paired_gold = {"new_products": gold["new_products"], "photos": [
        {"photo_id": pid, "bar": p["bar"], "split": p["split"],
         "items": [{"raw_name": r["name"], "gold": r["gold"]} for r in p["lines"] if r["gold"] is not None]}
        for pid, p in photo_lines.items()]}
    tmp = (args.json or Path(args.m3_cache) / "_paired").with_suffix(".paired_gold.json")
    tmp.write_text(json.dumps(paired_gold, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    match_eval.split_new_products = lambda _gold, _split: in_split  # C1 catalog from the real gold, not the paired lines

    out = {"source": args.source, "run": args.run, "split": args.split, "bars": args.bars,
           "catalog": match_eval.SEED.relative_to(REPO_ROOT).as_posix(),
           "photos": photo_ids, "lines": {}, "results": []}
    for pid, p in photo_lines.items():
        out["lines"][pid] = p
    for matcher in (M3_BASE, "M3a"):
        for condition in conditions:
            r = match_eval.evaluate(matcher, condition, args.split, tmp, engine if matcher == "M3a" else None)
            r["e2e_top1"] = e2e_top1(photo_lines, r, condition)
            r["unpaired"] = unpaired_outcomes(photo_lines, engine, catalogs, condition) if matcher == "M3a" else None
            kinds = r["owner_burden_by_kind"]
            r["per_photo"] = {
                pid: {"a": kinds.get(pid, {}).get("confirm", 0),
                      "bcd": sum(kinds.get(pid, {}).get(k, 0) for k in ("choose", "register", "wrong")),
                      "unpaired_unconfirmed": (r["unpaired"] or {}).get("unconfirmed_per_photo", {}).get(pid, 0),
                      "missed": sum(not g["extracted"] for g in photo_lines[pid]["gold_lines"])}
                for pid in photo_lines}
            out["results"].append(r)
    out["counts"] = {
        "extracted_lines": sum(len(p["lines"]) for p in photo_lines.values()),
        "paired_lines": sum(r["gold"] is not None for p in photo_lines.values() for r in p["lines"]),
        "unpaired_lines": sum(r["gold"] is None for p in photo_lines.values() for r in p["lines"]),
        "gold_lines": sum(len(p["gold_lines"]) for p in photo_lines.values()),
        "missed_gold_lines": sum(not g["extracted"] for p in photo_lines.values() for g in p["gold_lines"]),
        "gold_conflicts": sum(p["conflicts"] for p in photo_lines.values()),
    }
    out["llm"] = llm.summary()
    out["m3_photos"] = engine.photo_records

    print(f"== {args.source} r{args.run} / {args.split} {args.bars or ''}: {out['counts']}")
    for r in out["results"]:
        pp = r["per_photo"].values()
        cr = r["confirm_recommended_by_source"]
        print(f"  {r['matcher']:10s} {r['condition']}  lines {r['lines']:3d}  top1 {r['known_top1'] or 0:.3f}  "
              f"e2e top1 {r['e2e_top1']['top1'] or 0:.3f}  FM {r['false_merge_rate']:.3f}  "
              f"burden {r['owner_burden_totals']}  rule {cr['rule']['correct']}/{cr['rule']['n']}  "
              f"llm {cr['llm']['correct']}/{cr['llm']['n']}  accept err {r['accept_error_rate']:.4f}  "
              f"per photo a {statistics.mean(x['a'] for x in pp):.1f} bcd {statistics.mean(x['bcd'] for x in pp):.1f}"
              + (f"  unpaired {r['unpaired']['counts']}" if r["unpaired"] else ""))
    print(f"LLM: {json.dumps(llm.summary(), ensure_ascii=False)}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8",
                             newline="\n")


if __name__ == "__main__":
    main()
