"""Catalog-made matching cases: one bottle in Korean and English, and its ages and editions (I4-P19).

    python ai/regression/name_cases.py      # counts and every violation

For each catalog product that has an age, the brand's Korean and English names are combined with
the age in the ways menus write it ("글렌피딕 12년", "Glenfiddich 12y", "Glenfiddich 12 Years",
"Glenfiddich 12") and with the product's edition. Each name goes through the rule matcher
(S1+S2+S2b+S3) against the seed catalog. Nothing here is labeled by hand: what must hold follows
from how the name was made.

  false merge   a confirmed name got another brand, another age, another edition than the one
                written, or an edition when none was written and the plain bottling exists
  false split   the Korean and the English name of one bottle were confirmed as different products
  lost          a name that is not confirmed does not have its product among the candidates
  absent age    the brand has no product of that age (7, 13, 19, 23) and the name is confirmed anyway

Separately it counts the confirmed names that say less than their product: only a brand, or a
brand and an age that several products share. Those are what the incomplete-name guard
(app.matching.linking_guards, off in menu import) would hand to a person.
"""

from __future__ import annotations

import collections
import re
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "regression"))

import regression  # noqa: E402

HANGUL = re.compile("[가-힣]")
ABSENT_AGES = (7, 13, 19, 23)


def brand_names(brand: dict) -> dict[str, str]:
    """{"ko": first Korean alias, "en": first other alias or the canonical name}; a missing script is left out."""
    ko = [a["alias_text"] for a in brand["aliases"] if HANGUL.search(a["alias_text"])]
    en = [a["alias_text"] for a in brand["aliases"] if not HANGUL.search(a["alias_text"])]
    names = {"en": en[0] if en else brand["canonical_name"]}
    if ko:
        names["ko"] = ko[0]
    return names


def spellings(brand_text: str, age: int, edition: str | None, lang: str) -> list[str]:
    ages = [f"{age}년"] if lang == "ko" else [f"{age}y", f"{age} Years", f"{age}"]
    return [f"{brand_text} {a}" + (f" {edition}" if edition else "") for a in ages]


def run(seed: dict | None = None) -> dict:
    """{"counts": {...}, "violations": {kind: [..]}, "incomplete": {kind: [..]}}."""
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.matching.linking_guards import incomplete_name

    seed = seed or regression.load_seed()
    be = regression.harness.Backend(REPO_ROOT)
    catalog = regression.harness.build_catalog(be, "", "service", seed).catalog
    products = {uuid.UUID(p["id"]): p for p in seed["products"]}
    by_brand = collections.defaultdict(list)
    for p in seed["products"]:
        by_brand[p["brand_id"]].append(p)
    counts, violations, incomplete = collections.Counter(), collections.defaultdict(list), collections.defaultdict(list)

    def confirmed(name):
        r = be.resolve(name, catalog)
        return r, (products[r.proposed_product_id] if r.status == "exact_match" else None)

    for brand in seed["brands"]:
        names = brand_names(brand)
        by_age = collections.defaultdict(list)
        for p in by_brand[brand["id"]]:
            if p["age_years"] is not None:
                by_age[p["age_years"]].append(p)
        for age, same_age in by_age.items():
            plain = [p for p in same_age if not p["edition_name"]]
            for p in same_age:
                got_by_lang = {}
                for lang, brand_text in names.items():
                    for name in spellings(brand_text, age, p["edition_name"], lang):
                        counts["names"] += 1
                        r, got = confirmed(name)
                        if got is None:
                            counts["not_confirmed"] += 1
                            if uuid.UUID(p["id"]) not in [c.product_id for c in r.candidates]:
                                violations["lost"].append((name, p["display_name"]))
                            continue
                        counts["confirmed"] += 1
                        got_by_lang.setdefault(lang, set()).add(got["id"])
                        if got["brand_id"] != brand["id"] or got["age_years"] != age:
                            violations["false_merge"].append((name, got["display_name"], "brand or age"))
                        elif p["edition_name"] and got["id"] != p["id"]:
                            violations["false_merge"].append((name, got["display_name"], "edition"))
                        elif not p["edition_name"] and got["id"] != p["id"]:
                            violations["false_merge"].append((name, got["display_name"], "edition not written"))
                if len(got_by_lang) == 2 and got_by_lang["ko"] != got_by_lang["en"]:
                    violations["false_split"].append((p["display_name"], sorted(got_by_lang["ko"] ^ got_by_lang["en"])))
            if len(same_age) > 1 and not plain:  # brand + age alone cannot say which edition
                for lang, brand_text in names.items():
                    name = spellings(brand_text, age, None, lang)[0]
                    _, got = confirmed(name)
                    counts["age_shared_names"] += 1
                    if got is not None:
                        incomplete["age_only"].append((name, got["display_name"]))
        for lang, brand_text in names.items():
            for age in ABSENT_AGES:
                if by_age and age not in by_age:
                    counts["absent_age_names"] += 1
                    _, got = confirmed(spellings(brand_text, age, None, lang)[0])
                    if got is not None:
                        violations["absent_age"].append((brand_text, age, got["display_name"]))
        for alias in brand["aliases"]:  # the brand written alone
            counts["brand_alone_names"] += 1
            r, got = confirmed(alias["alias_text"])
            if got is not None and incomplete_name(alias["alias_text"], catalog.get_product(r.proposed_product_id), catalog):
                incomplete["brand_only"].append((alias["alias_text"], got["display_name"]))
    return {"counts": dict(counts), "violations": {k: v for k, v in violations.items()},
            "incomplete": {k: v for k, v in incomplete.items()}}


def main() -> int:
    result = run()
    print(result["counts"])
    for kind, rows in result["violations"].items():
        print(f"VIOLATION {kind}: {len(rows)}")
        for row in rows:
            print("  ", row)
    for kind, rows in result["incomplete"].items():
        print(f"confirmed although the name is incomplete ({kind}): {len(rows)}")
        for row in rows:
            print("  ", row)
    return 1 if result["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
