# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, A3). Review pending.
"""Build ai/catalog/catalog_v2_draft.json: catalog_v1_draft + the match gold's new products.

    python ai/catalog/build_catalog_v2.py

- Start: catalog_v1_draft as is (ids, aliases, sources unchanged).
- Products: every `new_products` entry of eval/match_gold_v1_1.json, except non-whisky
  (NON_WHISKY). A brand missing from v1 is created from the gold `brand` name.
- Aliases: the standard English name (`standard`); the menu line names linked to the product
  in the held-out bars' gold (labels v1.1 names, `menu:<bar>`); POST_TEST_ALIASES of
  match_gold_test_draft.py (`menu:미라보`). `both:`, `unknown`, `non_whisky` lines add no alias
  (a `both:` line still counts its bar in the products' `sources`).
- Products get `sources` (the `menu:<bar>` tags of the bars that list it) and `first_seen`
  (the first such bar). Evaluation-only fields; the loader ignores them.
- ids: UUIDv5 with the v1 namespace: `brand:<key>`, `balias:<brand key>:<text>`,
  `product:<key>`, `palias:<product key>:<text>`.

- Stage 3 (after human review of the final gold): eval/match_gold_final_v1.json new products
  (`sources` menu:수이 / menu:오드비) and the two bars' printed names as aliases (`menu:<bar>`),
  on new and existing products alike. An existing alias text only gets the source added.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))
from match_gold_test_draft import POST_TEST_ALIASES  # noqa: E402

V1 = REPO_ROOT / "ai" / "catalog" / "catalog_v1_draft.json"
GOLD = REPO_ROOT / "eval" / "match_gold_v1_1.json"
FINAL_GOLD = REPO_ROOT / "eval" / "match_gold_final_v1.json"
LABELS = REPO_ROOT / "eval" / "labels_heldout_v1_1.json"
OUT = REPO_ROOT / "ai" / "catalog" / "catalog_v2_draft.json"

NS = uuid.UUID("6b1a1f4e-19b0-4c7a-9a7e-b0771e3a0019")
# Bars in the order their menus were first labeled; first_seen is the earliest.
BAR_ORDER = ["위스키복춘", "서로상", "P5온라인", "미라보", "Beck", "포레스트", "오드비", "수이"]
# Gold new products that are not whisky (catalog rule: non-whisky is not registered).
NON_WHISKY = {"jack-daniels-apple": "whiskey liqueur (Jack Daniel's Tennessee Apple, 35% ABV)"}
BILINGUAL_SEPARATOR = "/"
# Annotation after the name on the Odbi event lines ("몰트맨 ... / 행사"): not part of the name.
EVENT_SUFFIX = re.compile(r"\s*/\s*(?:한정파\s*)?행사$")
HANGUL = re.compile("[가-힣]")


def uid(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def brand_key(name: str) -> str:
    """'Maker's Mark' -> makers_mark, 'Gordon & MacPhail' -> gordon_macphail (v1 key style)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower().replace("'", "")).strip("_")


def lang(text: str) -> str:
    return "ko" if HANGUL.search(text) else "en"


def menu_names(raw_name: str) -> list[str]:
    """Alias texts for one printed line: the parts of a 'Korean / English' line, else the line.
    An event annotation ("/ 행사") is dropped first."""
    raw_name = EVENT_SUFFIX.sub("", raw_name)
    parts = [p.strip() for p in raw_name.split(BILINGUAL_SEPARATOR)]
    return [p for p in parts if p] if len(parts) > 1 else [raw_name.strip()]


def add_alias(product: dict, text: str, source: str) -> bool:
    """Add `text` with `source`; an existing alias with the same text gets the source. True if new."""
    for a in product["aliases"]:
        if a["alias_text"] == text:
            if source not in a["sources"]:
                a["sources"] = sorted(a["sources"] + [source])
            return False
    product["aliases"].append({"id": uid(f"palias:{product['key']}:{text}"), "alias_text": text,
                               "language_code": lang(text), "sources": [source], "is_searchable": True})
    return True


def set_bar_fields(product: dict, bars: set[str]) -> None:
    product["sources"] = [f"menu:{b}" for b in BAR_ORDER if b in bars]
    product["first_seen"] = next((b for b in BAR_ORDER if b in bars), None)


def gold_refs(gold: str) -> list[str]:
    return gold.removeprefix("both:").split("|")


def build() -> tuple[dict, dict]:
    v1 = json.loads(V1.read_text(encoding="utf-8"))
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    final = json.loads(FINAL_GOLD.read_text(encoding="utf-8"))
    heldout_bars = {p["bar"] for p in json.loads(LABELS.read_text(encoding="utf-8"))["photos"]}
    cat = copy.deepcopy(v1)
    brands = {b["key"]: b for b in cat["brands"]}
    products = {p["key"]: p for p in cat["products"]}
    stats = {"excluded": dict(NON_WHISKY), "menu_lines_skipped": {}, "post_test_aliases": 0}

    # Bars per product: v1 menu alias sources, then the gold links.
    bars: dict[str, set[str]] = {k: {s.removeprefix("menu:") for a in p["aliases"] for s in a["sources"]
                                     if s.startswith("menu:")} for k, p in products.items()}

    def add_products(new_products: dict, stage: str) -> None:
        st = stats.setdefault(stage, {"new_brands": [], "new_products": 0, "menu_aliases_new": 0,
                                      "menu_aliases_merged": 0})
        for key, np_ in new_products.items():
            if key in NON_WHISKY:
                continue
            assert key not in products, key
            raw = np_["brand"].replace("-", "_")
            bkey = raw if raw in brands else brand_key(np_["brand"])
            if bkey not in brands:
                name = np_["brand"]
                brands[bkey] = {"id": uid(f"brand:{bkey}"), "key": bkey, "canonical_name": name,
                                "aliases": [{"id": uid(f"balias:{bkey}:{name}"), "alias_text": name,
                                             "language_code": lang(name), "sources": ["standard"]}]}
                cat["brands"].append(brands[bkey])
                st["new_brands"].append(bkey)
            p = {"id": uid(f"product:{key}"), "key": key, "brand_id": brands[bkey]["id"], "brand_key": bkey,
                 "category": "whisky", "display_name": np_["display_name"], "age_years": np_["age_years"],
                 "edition_name": np_["edition_name"], "abv": None, "aliases": []}
            add_alias(p, np_["display_name"], "standard")
            products[key] = p
            cat["products"].append(p)
            bars[key] = set()
            st["new_products"] += 1

    def add_menu_aliases(photos: list[dict], stage: str) -> None:
        st = stats[stage]
        for photo in photos:
            for item in photo["items"]:
                g = item["gold"]
                if g in ("unknown", "non_whisky") or g.startswith("both:"):
                    stats["menu_lines_skipped"][item["raw_name"]] = g
                    for ref in gold_refs(g) if g.startswith("both:") else []:
                        bars[ref.removeprefix("new:")].add(photo["bar"])  # listed at the bar, but no alias
                    continue
                key = g.removeprefix("new:")
                if key in NON_WHISKY:
                    stats["menu_lines_skipped"][item["raw_name"]] = f"non-whisky product {key}"
                    continue
                bars[key].add(photo["bar"])
                for text in menu_names(item["raw_name"]):
                    if add_alias(products[key], text, f"menu:{photo['bar']}"):
                        st["menu_aliases_new"] += 1
                    else:
                        st["menu_aliases_merged"] += 1

    # Stage 1 (core): match gold v1.1 new products, held-out bar menus, POST_TEST_ALIASES.
    add_products(gold["new_products"], "core")
    add_menu_aliases([p for p in gold["photos"] if p["bar"] in heldout_bars], "core")
    for key, texts in POST_TEST_ALIASES.items():
        bars[key].add("미라보")
        for text in texts:
            stats["post_test_aliases"] += add_alias(products[key], text, "menu:미라보")

    # Stage 3 (final): Sui / Odbi gold (after human review). Their aliases are menu:수이 / menu:오드비,
    # removed again in the evaluation snapshot (export_snapshot.py).
    add_products(final["new_products"], "final")
    add_menu_aliases(final["photos"], "final")

    for key, p in products.items():
        set_bar_fields(p, bars[key])

    cat["version"] = "catalog_v2_draft"
    cat["created"] = "2026-10-14"
    cat["based_on"] = ("catalog_v1_draft + eval/match_gold_v1_1.json new_products + menu names of the held-out "
                       "bars (labels v1.1: 미라보, Beck, 포레스트) + POST_TEST_ALIASES (match_gold_test_draft.py) + "
                       "eval/match_gold_final_v1.json new_products and menu names (수이, 오드비)")
    cat["notes"] = v1["notes"] + [
        "products[].sources / first_seen are evaluation-only fields: the bars whose menu lists the product, "
        "and the first of them. The loader ignores them.",
        "Menu aliases are the printed line names (labels v1.1, labels_final_v1); a 'Korean / English' line gives "
        "one alias per part; the Odbi event note ' / 행사' is not part of the alias.",
        "menu:수이 / menu:오드비 aliases are the final (P47) bars' own spellings: catalog_v2_eval_5bars.json drops "
        "aliases whose only sources are these two.",
    ]
    cat["excluded_non_whisky"] = {**v1["excluded_non_whisky"], **NON_WHISKY}
    # Keep the v1 key order with the new eval-only fields after `aliases`.
    for p in cat["products"]:
        p_sorted = {k: p[k] for k in ["id", "key", "brand_id", "brand_key", "category", "display_name",
                                      "age_years", "edition_name", "abv", "sources", "first_seen", "aliases"]}
        p.clear()
        p.update(p_sorted)
    return cat, stats


def main() -> None:
    cat, stats = build()
    OUT.write_bytes((json.dumps(cat, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    n_pa = sum(len(p["aliases"]) for p in cat["products"])
    n_ba = sum(len(b["aliases"]) for b in cat["brands"])
    print(f"wrote {OUT.relative_to(REPO_ROOT)}: brands {len(cat['brands'])}, brand aliases {n_ba}, "
          f"products {len(cat['products'])}, product aliases {n_pa}")
    for stage in ("core", "final"):
        st = stats[stage]
        print(f"  {stage}: new brands {len(st['new_brands'])}, new products {st['new_products']}, "
              f"menu aliases new {st['menu_aliases_new']}, merged into existing text {st['menu_aliases_merged']}")
    print(f"  POST_TEST_ALIASES new {stats['post_test_aliases']}; excluded non-whisky: {stats['excluded']}")
    print(f"menu lines without aliases: {len(stats['menu_lines_skipped'])}")
    for name, why in stats["menu_lines_skipped"].items():
        print(f"  {name}: {why}")


if __name__ == "__main__":
    main()
