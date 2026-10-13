# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13). Reviewed by Jinwoo Park.
"""Evaluate product matching on labeled menu lines (eval_plan.md, 매칭 평가).

    python ai/eval/match_eval.py                       # dev split, matcher M0, both catalog conditions
    python ai/eval/match_eval.py --matcher M0 --json out.json

Input is the gold menu line name (layer-1 label), so only matching is measured.
For each bar the catalog drops aliases whose sources are only that bar's own menu
("menu:<bar>"): the product may be known, but this bar's spelling is new.

Catalog conditions
  C0  catalog_v1_draft as is. Products marked new:* are absent -> expected unmatched.
  C1  C0 + every new:* product, with its standard English name as the only alias
      ("product is in the DB, this menu's spelling is not").

Outcome per line (glass/bottle rows of one line count once)
  correct        exact_match to the gold product; for both: (one line, two products)
                 a multi result with exactly the two gold products
  partial        both: line, exact_match to only one of its two products
  ambiguous_ok   ambiguous, gold among the candidates -> owner picks
  ambiguous_bad  ambiguous, gold not among the candidates
  unmatched      no candidate (correct outcome when gold is absent from the catalog)
  false_merge    exact_match (or a multi result) naming a product that is not gold,
                 or naming anything when the gold is absent / non_whisky
  overconfident  exact_match or multi for an "unknown" line (menu too short to tell)
Owner burden = lines per photo that are not confirmed (exact_match or multi): the
owner has to choose or create.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.matching.memory_catalog import InMemoryCatalog  # noqa: E402
from app.matching.resolve import resolve_product  # noqa: E402
from app.matching.staged import resolve_product_staged  # noqa: E402
from app.matching.types import ExtractedProduct, ProductInfo  # noqa: E402

GOLD = REPO_ROOT / "eval" / "match_gold_v1.json"
SEED = REPO_ROOT / "ai" / "catalog" / "catalog_v1_draft.json"
NEW_NS = uuid.UUID("6f1d3f0e-6c8a-4d5e-9b1a-2b7c3d4e5f60")
BURDEN_LIMIT = 5  # 진우 기준: 메뉴판 1장당 업주가 골라야 하는 항목 5개 미만
OUTCOMES = ("correct", "partial", "ambiguous_ok", "ambiguous_bad", "unmatched", "false_merge", "overconfident")
CONFIRMED = ("exact_match", "multi")

MATCHERS = {
    "M0": resolve_product,  # I1: normalize + exact alias, " / " bilingual split
    "S1": lambda item, catalog: resolve_product_staged(item, catalog, {"S1"}),  # + parentheses, two products
}


def load_catalog(bar: str, condition: str, new_products: dict) -> tuple[InMemoryCatalog, dict[str, uuid.UUID]]:
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    key_to_id = {p["key"]: uuid.UUID(p["id"]) for p in seed["products"]}
    brand_ids = {b["key"]: uuid.UUID(b["id"]) for b in seed["brands"]}
    own = {f"menu:{bar}"}
    products, aliases = [], []
    for row in seed["products"]:
        pid = uuid.UUID(row["id"])
        products.append(ProductInfo(pid, row["display_name"], row.get("age_years"), row.get("edition_name"),
                                    uuid.UUID(row["brand_id"])))
        aliases += [(pid, a["alias_text"]) for a in row["aliases"] if not set(a.get("sources", [])) <= own]
    for key, p in new_products.items():
        pid = uuid.uuid5(NEW_NS, key)
        key_to_id[f"new:{key}"] = pid
        if condition == "C1":
            # brand: an existing brand key, or a new brand's English name
            brand_id = brand_ids.get(p["brand"]) or uuid.uuid5(NEW_NS, f"brand:{p['brand']}")
            products.append(ProductInfo(pid, p["display_name"], p["age_years"], p["edition_name"], brand_id))
            aliases.append((pid, p["display_name"]))
    return InMemoryCatalog(products, aliases), key_to_id


def gold_refs(gold: str) -> list[str]:
    return gold.removeprefix("both:").split("|")


def judge(gold: str, r, key_to_id: dict, in_catalog) -> str:
    """`r` is a ResolutionResult; a "multi" result lists its products in `r.parts`."""
    status = r.status
    if gold == "unknown":
        return "overconfident" if status in CONFIRMED else ("unmatched" if status == "unmatched" else "ambiguous_ok")
    both = gold.startswith("both:")
    ids = {key_to_id[g] for g in gold_refs(gold) if g in key_to_id and in_catalog(g)}
    if status == "unmatched":
        return "unmatched"
    if status == "multi":
        named = {p.proposed_product_id for p in r.parts}
        if not named <= ids:
            return "false_merge"
        return "correct" if both and len(ids) == 2 and named == ids else "partial"
    if status == "exact_match":
        if r.proposed_product_id not in ids:
            return "false_merge"
        return "partial" if both else "correct"
    return "ambiguous_ok" if ids & {c.product_id for c in r.candidates} else "ambiguous_bad"


def evaluate(matcher: str, condition: str, split: str) -> dict:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    resolve = MATCHERS[matcher]
    by_bar: dict[str, Counter] = defaultdict(Counter)
    by_kind: dict[str, Counter] = defaultdict(Counter)
    burden: dict[str, int] = {}
    errors = []
    catalogs = {}
    for photo in gold["photos"]:
        if photo["split"] != split:
            continue
        bar = photo["bar"]
        if bar not in catalogs:
            catalogs[bar] = load_catalog(bar, condition, gold["new_products"])
        catalog, key_to_id = catalogs[bar]

        def in_catalog(g: str) -> bool:
            return not g.startswith("new:") or condition == "C1"

        seen = {}
        for item in photo["items"]:
            seen.setdefault(item["raw_name"], item["gold"])
        burden[photo["photo_id"]] = 0
        for name, g in seen.items():
            r = resolve(ExtractedProduct(product_name=name), catalog)
            outcome = judge(g, r, key_to_id, in_catalog)
            kind = ("non_whisky" if g == "non_whisky" else "unknown" if g == "unknown"
                    else "known" if all(in_catalog(x) for x in gold_refs(g)) else "absent")
            by_bar[bar][outcome] += 1
            by_kind[kind][outcome] += 1
            if r.status not in CONFIRMED:
                burden[photo["photo_id"]] += 1
            if outcome not in ("correct",) and not (kind in ("absent", "non_whisky") and outcome == "unmatched"):
                errors.append({"photo_id": photo["photo_id"], "name": name, "gold": g, "kind": kind,
                               "outcome": outcome, "status": r.status})
    lines = sum(sum(c.values()) for c in by_bar.values())
    fm = sum(c["false_merge"] + c["overconfident"] for c in by_bar.values())
    known = by_kind["known"]
    return {
        "matcher": matcher, "condition": condition, "split": split, "lines": lines,
        "known_top1": known["correct"] / sum(known.values()) if known else None,
        "false_merge_rate": fm / lines if lines else None,
        "by_kind": {k: dict(v) for k, v in by_kind.items()},
        "by_bar": {k: dict(v) for k, v in by_bar.items()},
        "owner_burden": burden,
        "photos_under_limit": sum(b < BURDEN_LIMIT for b in burden.values()) / len(burden) if burden else None,
        "errors": errors,
    }


def print_result(r: dict) -> None:
    print(f"\n== {r['matcher']} / {r['condition']} / {r['split']}  ({r['lines']} lines)")
    kt = f"{r['known_top1']:.3f}" if r["known_top1"] is not None else "-"
    print(f"  known top-1 {kt}   false merge rate {r['false_merge_rate']:.3f}   "
          f"photos with owner burden < {BURDEN_LIMIT}: {r['photos_under_limit']:.2f}")
    print("  " + "kind".ljust(12) + "".join(o.rjust(15) for o in OUTCOMES))
    for k, c in sorted(r["by_kind"].items()):
        print("  " + k.ljust(12) + "".join(str(c.get(o, 0)).rjust(15) for o in OUTCOMES))
    for bar, c in sorted(r["by_bar"].items()):
        print("  [bar] " + bar.ljust(6) + "".join(str(c.get(o, 0)).rjust(15) for o in OUTCOMES))
    print("  owner burden per photo: " + ", ".join(f"{k} {v}" for k, v in r["owner_burden"].items()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--matcher", nargs="+", default=list(MATCHERS), choices=list(MATCHERS))
    parser.add_argument("--condition", nargs="+", default=["C0", "C1"], choices=["C0", "C1"])
    parser.add_argument("--split", default="dev", choices=["dev", "test"])
    parser.add_argument("--json", type=Path, help="write all results (with error lists) here")
    args = parser.parse_args()
    results = [evaluate(m, c, args.split) for m in args.matcher for c in args.condition]
    for r in results:
        print_result(r)
    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
