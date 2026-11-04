"""Add the Korean aliases of i3_additions_ko_aliases.json to catalog_v2_service_i3_additions.json.

The 61 products and 30 new brands of the I3 additions shipped with their English names only, so a
customer searching in Korean ("휘슬피그", "닛카 프론티어") found nothing. This adds Korean brand and
product aliases, with the catalog id rule (uuid5, catalog namespace, `balias:<brand key>:<text>`,
`palias:<product key>:<text>`), and stops when an alias normalizes like an alias of another brand or
product (the same check as build_menu_seeds_demo_i3.py). Re-running adds nothing new.

    cd backend && uv run python ../ai/catalog/add_ko_aliases_i3.py [--check]

(The backend environment is only needed for app.core.normalize.)
"""

import argparse
import collections
import json
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CATALOG_DIR = REPO / "ai" / "catalog"
sys.path.insert(0, str(REPO / "backend"))
from app.core.normalize import normalize  # noqa: E402

CATALOG_NS = uuid.UUID("6b1a1f4e-19b0-4c7a-9a7e-b0771e3a0019")  # catalog v1/v2 ids (README section 8)
BASE = CATALOG_DIR / "catalog_v2_service.json"
ADDITIONS = CATALOG_DIR / "catalog_v2_service_i3_additions.json"
KO = CATALOG_DIR / "i3_additions_ko_aliases.json"
GENERATED = "generated:claude-2026-11-04"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report only, do not write")
    args = parser.parse_args()
    base, additions, ko = load(BASE), load(ADDITIONS), load(KO)

    brand_owner, product_owner = collections.defaultdict(set), collections.defaultdict(set)
    for b in base["brands"] + additions["brands"]:
        for a in b["aliases"]:
            brand_owner[normalize(a["alias_text"])].add(b["key"])
    for p in base["products"] + additions["products"]:
        for a in p["aliases"]:
            product_owner[normalize(a["alias_text"])].add(p["key"])

    problems, added_b, added_p = [], 0, 0
    brands = {b["key"]: b for b in additions["brands"]}
    for key, texts in ko["brands"].items():
        brand = brands.get(key)
        if brand is None:
            problems.append(f"brand {key!r} is not a new brand of the additions")
            continue
        for text in texts:
            n = normalize(text)
            if n in {normalize(a["alias_text"]) for a in brand["aliases"]}:
                continue
            if brand_owner[n] - {key}:
                problems.append(f"brand alias {text!r} ({key}) normalizes like brand(s) {sorted(brand_owner[n] - {key})}")
                continue
            brand["aliases"].append({"id": str(uuid.uuid5(CATALOG_NS, f"balias:{key}:{text}")), "alias_text": text,
                                     "language_code": "ko", "sources": [GENERATED]})
            brand_owner[n].add(key)
            added_b += 1

    products = {p["key"]: p for p in additions["products"]}
    for key, entry in ko["products"].items():
        product = products.get(key)
        if product is None:
            problems.append(f"product {key!r} is not in the additions")
            continue
        sources = product.get("first_seen")
        for kind in ("menu", "generated"):
            for text in entry.get(kind, []):
                n = normalize(text)
                if n in {normalize(a["alias_text"]) for a in product["aliases"]}:
                    continue
                if product_owner[n] - {key}:
                    problems.append(f"product alias {text!r} ({key}) normalizes like product(s) "
                                    f"{sorted(product_owner[n] - {key})}")
                    continue
                if brand_owner[n]:
                    problems.append(f"product alias {text!r} ({key}) equals brand alias of {sorted(brand_owner[n])}: "
                                    "brand search answers it first, leave it out")
                    continue
                src = [f"menu:{sources}"] if kind == "menu" and sources else [GENERATED]
                product["aliases"].append({"id": str(uuid.uuid5(CATALOG_NS, f"palias:{key}:{text}")),
                                           "alias_text": text, "language_code": "ko", "sources": src,
                                           "is_searchable": True})
                product_owner[n].add(key)
                added_p += 1

    missing = [p["key"] for p in additions["products"]
               if not any(a.get("language_code") == "ko" for a in p["aliases"])]
    print(f"added {added_b} brand aliases, {added_p} product aliases; products still without a Korean alias: {missing}")
    for line in problems:
        print("PROBLEM", line)
    if problems:
        return 1
    if not args.check:
        notes = additions.setdefault("notes", [])
        note = ("2026-11-04: Korean brand and product aliases added from i3_additions_ko_aliases.json "
                "(add_ko_aliases_i3.py): menu spellings of the I3 test bars and usual transliterations.")
        if note not in notes:
            notes.append(note)
        ADDITIONS.write_text(json.dumps(additions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
