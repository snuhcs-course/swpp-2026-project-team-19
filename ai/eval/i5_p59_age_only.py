"""Brand + age only lines ("글렌모렌지 14년") and what the matcher gives them (I5-P59 1c). API 0 calls.

    python ai/eval/i5_p59_age_only.py RESULT.json [RESULT.json ...] [--md out.md]

RESULT.json is an i3_match_eval.py result (its catalog is rebuilt from the recorded arguments: set,
catalog, the rules checkout's catalog file). A line is "brand + age only" when, for the whole name or
one side of "A / B" or a parenthesis variant, the brand rules find a brand and nothing but an age is
left (linking_guards.incomplete_name reads lines the same way). For each such line: how many products
of that brand have that age, the result in the file (rules section), and whether the line is a 1c case
(exactly one product of that age) that does not get that product as its first candidate. A line confirmed
to the one product of that age although it is an edition is marked too ("confirmed_edition"): it stays
confirmed, as incompleteName leaves a brand with no sibling of that age.
"""

import argparse
import importlib
import json
import sys
from pathlib import Path

import i3_match_eval as h


def age_only_readings(name: str, catalog, staged, guards) -> list[tuple[list, int]]:
    """(brand ids, age) for each reading of `name` that is a brand and an age and nothing else."""
    if staged.BILINGUAL_SEPARATOR in name:
        names = [side.strip() for side in name.split(staged.BILINGUAL_SEPARATOR) if side.strip()]
    else:
        names = [name, *staged._parenthesis_variants(name)]
    out = []
    for variant in names:
        found = staged._find_brand(variant, catalog)
        if found is None:
            continue
        brand_ids, _, rest = found
        age, tokens = staged._split_age(rest)
        aliases = [a for a, b in catalog.list_normalized_brand_aliases() if b in brand_ids]
        if age is not None and not staged._without_brand(tokens, aliases):
            out.append((brand_ids, age))
    return out


def scan(result: dict, be, bar_catalogs: dict) -> list[dict]:
    staged = sys.modules["app.matching.staged"]
    guards = importlib.import_module("app.matching.linking_guards")
    rows = []
    for row in result["rules"]["rows"]:
        bc = bar_catalogs[row["bar"]]
        readings = age_only_readings(row["name"], bc.catalog, staged, guards)
        if not readings:
            continue
        brand_ids, age = readings[0]
        products = [bc.catalog.get_product(pid) for b in brand_ids for pid in bc.catalog.get_brand_product_ids(b)]
        same = sorted((p for p in products if p.age_years == age), key=lambda p: p.display_name)
        same_age = [p.display_name for p in same]
        first = row["cands"].split(" || ")[0] if row["cands"] else ""
        # 1c: the one product of that age is offered first. A confirmation stays as it is: an alias or the
        # S2b default product, and with no sibling of that age incompleteName keeps it too
        offered = bool(same_age) and first == same_age[0]
        gap = len(same) == 1 and not offered
        confirmed_edition = row["status"] == "exact_match" and len(same) == 1 and guards._has_edition(same[0])
        rows.append({"photo_id": row["photo_id"], "name": row["name"], "gold": row["gold"], "age": age,
                     "same_age": same_age, "status": row["status"], "outcome": row["outcome"], "cands": row["cands"],
                     "one_product_not_offered": gap, "confirmed_edition": confirmed_edition})
    return rows


def catalogs_for(result: dict, be, catalog_file: Path | None = None) -> dict:
    """The bar catalogs of the run, rebuilt from today's files (the result records only the file name)."""
    path = catalog_file or h.REPO_ROOT / "ai" / "catalog" / result["catalog_file"]
    seed = json.loads(path.read_text(encoding="utf-8"))
    if result["catalog"] == "ops":
        seed = h.with_additions(seed, json.loads((h.REPO_ROOT / h.ADDITIONS_FILE).read_text(encoding="utf-8")))
    new = None
    if result["catalog"] == "full":
        new = json.loads(h.I3_GOLD.read_text(encoding="utf-8")).get("new_products")
    variant = "service" if result["catalog"] == "ops" else result["catalog"]
    bars = sorted({r["bar"] for r in result["rules"]["rows"]})
    return {bar: h.build_catalog(be, bar, variant, seed, new) for bar in bars}


def to_md(name: str, rows: list[dict]) -> str:
    gaps = sum(r["one_product_not_offered"] for r in rows)
    one = sum(len(r["same_age"]) == 1 for r in rows)
    out = [f"## {name}: 브랜드 + 연수만 적힌 줄 {len(rows)} (그 연수 상품이 하나 {one}, 그중 후보로 안 나온 줄 {gaps})", "",
           "| 사진 | 줄 | 정답 | 연수 | 그 연수 상품 | 결과 | 후보 | 1c 대상인데 후보 없음 | 에디션 확정 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['photo_id']} | {r['name']} | {r['gold']} | {r['age']} | {len(r['same_age'])}: "
                   f"{', '.join(r['same_age'])[:70]} | {r['status']} / {r['outcome']} | {r['cands'][:70]} | "
                   f"{'**예**' if r['one_product_not_offered'] else ''} | {'예' if r['confirmed_edition'] else ''} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("results", nargs="+", type=Path)
    ap.add_argument("--md", type=Path)
    ap.add_argument("--catalog-file", type=Path, help="default: ai/catalog/<the file the result names>")
    args = ap.parse_args(argv)
    be = h.Backend(h.REPO_ROOT)
    out, md = {}, []
    for path in args.results:
        result = json.loads(path.read_text(encoding="utf-8"))
        out[path.name] = scan(result, be, catalogs_for(result, be, args.catalog_file))
        md.append(to_md(path.name, out[path.name]))
    if args.md:
        args.md.write_text("\n".join(md), encoding="utf-8", newline="\n")
    print("\n".join(md))
    return out


if __name__ == "__main__":
    main()
