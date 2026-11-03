"""Build the I3 demo data: catalog additions + menu seeds for the 8 I3 test bars.

Same rules as build_menu_seeds_demo.py (the I2 demo menus), applied to the human-reviewed I3 gold:

- Inputs (read only): eval/labels_i3_v1.json, eval/match_gold_i3_v1.json,
  ai/catalog/catalog_v2_service.json, ai/catalog/bars_v3.json.
- Catalog additions (ai/catalog/catalog_v2_service_i3_additions.json): the gold's `new_products`
  (the products the frozen evaluation adds for `--catalog full`, ai/eval/i3_match_eval.py), with the
  same fields: display name, brand, age, edition, and the standard English name as the only alias;
  a new brand gets its English name as the only alias. IDs follow the catalog rule (uuid5 with the
  catalog namespace, `brand:<key>`, `product:<key>`, `balias:...`, `palias:...`), not the
  evaluation's in-memory ids, so a later catalog version that adds the same key keeps the id.
- Menus: one board entry per catalog product per bar (bar_menu_items is unique per bar+product).
  unknown / non_whisky lines are skipped. A `both:` line (one menu line naming two or three
  products at one price, e.g. "Wild Turkey 81 / 101") gives each of its products the line's
  options. Options: 잔/병 with the label's pour_ml and price; a line with a null price adds no option.
  IDs are uuid5 with the demo-menu namespace of build_menu_seeds_demo.py, so re-running produces the
  same rows.
- Output: menu seeds of bars in bars_v3.json `bars` go to ai/catalog/menu_seed_<key>_demo_v1.json
  (loaded by the Seed catalog workflow, demo-menus-*). Bars in `pending_bars` (coordinates not
  confirmed, so the bar cannot be loaded) go to ai/catalog/pending_i3/, which that glob does not
  match. Move a bar from `pending_bars` to `bars` once its coordinates are confirmed and run again.

    cd backend && uv run --no-sync python ../ai/catalog/build_menu_seeds_demo_i3.py

(The backend environment is only needed for app.core.normalize, used for the alias checks.)
"""
import collections
import json
import re
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CATALOG_DIR = REPO / "ai" / "catalog"
sys.path.insert(0, str(REPO / "backend"))
from app.core.normalize import normalize  # noqa: E402

CATALOG_NS = uuid.UUID("6b1a1f4e-19b0-4c7a-9a7e-b0771e3a0019")  # catalog v1/v2 ids (README section 8)
MENU_NS = uuid.UUID("6f1e2c3a-9b7d-4e21-8a5c-0d4b2e1f7a90")  # build_menu_seeds_demo.py
LABEL = {"glass": "잔", "bottle": "병", None: None}
ADDITIONS = CATALOG_DIR / "catalog_v2_service_i3_additions.json"
PENDING_DIR = CATALOG_DIR / "pending_i3"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def refs(gold: str) -> list[str]:
    """match_eval.gold_refs: catalog keys of a gold value, `new:` prefix kept."""
    return gold.removeprefix("both:").split("|")


service = load(CATALOG_DIR / "catalog_v2_service.json")
gold = load(REPO / "eval" / "match_gold_i3_v1.json")
labels = load(REPO / "eval" / "labels_i3_v1.json")
bars_file = load(CATALOG_DIR / "bars_v3.json")
bars_by_label = {b["label_bar_name"]: (b, True) for b in bars_file["bars"]}
bars_by_label.update({b["label_bar_name"]: (b, False) for b in bars_file["pending_bars"]})

# ---- catalog additions --------------------------------------------------------------------

brand_by_key = {b["key"]: b for b in service["brands"]}
product_keys = {p["key"] for p in service["products"]}
canonical_names = {b["canonical_name"].casefold(): b["key"] for b in service["brands"]}
brand_alias_owner = collections.defaultdict(set)
for b in service["brands"]:
    for a in b["aliases"]:
        brand_alias_owner[normalize(a["alias_text"])].add(b["key"])
product_alias_owner = collections.defaultdict(set)
for p in service["products"]:
    for a in p["aliases"]:
        product_alias_owner[normalize(a["alias_text"])].add(p["key"])

# bars (label names) where each new product is on the menu, in label order
product_bars = collections.defaultdict(list)
for photo in gold["photos"]:
    for item in photo["items"]:
        for ref in refs(item["gold"]):
            if ref.startswith("new:") and photo["bar"] not in product_bars[ref[4:]]:
                product_bars[ref[4:]].append(photo["bar"])
used = set(product_bars)
problems = []
if set(gold["new_products"]) != used:
    problems.append(f"new_products not referenced: {sorted(set(gold['new_products']) - used)}; "
                    f"referenced but undefined: {sorted(used - set(gold['new_products']))}")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


new_brands: dict[str, dict] = {}
new_products = []
for key, np in sorted(gold["new_products"].items()):
    if key in product_keys:
        problems.append(f"new product {key} is already in the service catalog")
        continue
    brand = brand_by_key.get(np["brand"].replace("-", "_"))  # i3_match_eval.build_catalog does the same lookup
    if brand is None:
        bkey = slug(np["brand_name"])
        if bkey in brand_by_key:
            problems.append(f"{key}: new brand key {bkey} is an existing brand")
        if np["brand_name"].casefold() in canonical_names:
            problems.append(f"{key}: brand name {np['brand_name']!r} is brand {canonical_names[np['brand_name'].casefold()]}")
        brand = new_brands.get(bkey)
        if brand is None:
            text = np["brand_name"]
            owners = brand_alias_owner.get(normalize(text), set())
            if owners:
                problems.append(f"new brand alias {text!r} normalizes like brand(s) {sorted(owners)}")
            brand = new_brands[bkey] = {
                "id": str(uuid.uuid5(CATALOG_NS, f"brand:{bkey}")),
                "key": bkey,
                "canonical_name": text,
                "aliases": [{"id": str(uuid.uuid5(CATALOG_NS, f"balias:{bkey}:{text}")), "alias_text": text,
                             "language_code": "en", "sources": ["standard"]}],
            }
    text = np["display_name"]
    owners = product_alias_owner.get(normalize(text), set())
    if owners:
        problems.append(f"new product alias {text!r} normalizes like product(s) {sorted(owners)}")
    new_products.append({
        "id": str(uuid.uuid5(CATALOG_NS, f"product:{key}")),
        "key": key,
        "brand_id": brand["id"],
        "brand_key": brand["key"],
        "category": "whisky",
        "display_name": text,
        "age_years": np["age_years"],
        "edition_name": np["edition_name"],
        "abv": None,
        "sources": [f"menu:{bar}" for bar in product_bars[key]],
        "first_seen": product_bars[key][0],
        "aliases": [{"id": str(uuid.uuid5(CATALOG_NS, f"palias:{key}:{text}")), "alias_text": text,
                     "language_code": "en", "sources": ["standard"], "is_searchable": True}],
    })

additions = {
    "version": "catalog_v2_service_i3_additions_v1",
    "created": "2026-11-03",
    "based_on": "eval/match_gold_i3_v1.json new_products (the products ai/eval/i3_match_eval.py adds for --catalog full)",
    "purpose": "Demo (I3 heuristic evaluation): products of the 8 I3 test bars that catalog_v2_service.json lacks, "
               "so their demo menus can be loaded. Loaded together with catalog_v2_service.json by "
               "backend/scripts/seed_catalog.py. Not used by any evaluation.",
    "notes": [
        "Fields as in catalog_v2_service.json. Aliases: the standard English name only (as the evaluation's full "
        "catalog); no Korean or menu spellings, so customer search finds these products by their English name.",
        "Products of an existing brand point at that brand's id; brands below are new.",
        "IDs: uuid5 with the catalog namespace (README section 8): brand:<key>, balias:<brand key>:<text>, "
        "product:<key>, palias:<product key>:<text>.",
        "Generated by ai/catalog/build_menu_seeds_demo_i3.py.",
    ],
    "brands": list(new_brands.values()),
    "products": new_products,
}
dump(ADDITIONS, additions)
prod_by_key = {p["key"]: p for p in service["products"] + new_products}

# ---- menus --------------------------------------------------------------------------------

per_bar = collections.OrderedDict()
report = collections.defaultdict(collections.Counter)
gold_photos = {p["photo_id"]: p for p in gold["photos"]}
for photo in labels["photos"]:
    pid = photo["photo_id"]
    gphoto = gold_photos[pid]
    if photo["bar"] not in bars_by_label:
        problems.append(f"{pid}: bar {photo['bar']!r} not in bars_v3.json")
        continue
    bar, _ = bars_by_label[photo["bar"]]
    litems, gitems = photo["items"], gphoto["items"]
    if len(litems) != len(gitems):
        problems.append(f"{pid}: label {len(litems)} vs gold {len(gitems)}")
        continue
    for li, gi in zip(litems, gitems):
        if (li["raw_name"], li["unit"]) != (gi["raw_name"], gi["unit"]):
            problems.append(f"{pid}: mismatch {li['raw_name']!r} vs {gi['raw_name']!r}")
            continue
        g = gi["gold"]
        report[bar["key"]]["lines"] += 1
        if g in ("unknown", "non_whisky"):
            report[bar["key"]]["skip_" + g] += 1
            continue
        keys = [r.removeprefix("new:") for r in refs(g)]
        if g.startswith("both:"):
            report[bar["key"]]["both_lines"] += 1
        if any(k.startswith("new:") for k in refs(g)):
            report[bar["key"]]["new_product_lines"] += 1
        if li["price_krw"] is None:
            report[bar["key"]]["null_price_line"] += 1
        for key in keys:
            p = prod_by_key.get(key)
            if p is None:
                report[bar["key"]]["skip_not_in_catalog"] += 1
                problems.append(f"{bar['key']}: product key {key} not in catalog ({li['raw_name']})")
                continue
            entries = per_bar.setdefault(bar["key"], collections.OrderedDict())
            e = entries.setdefault(p["id"], {"product": p, "names": [], "options": []})
            if li["raw_name"] not in e["names"]:
                e["names"].append(li["raw_name"])
            if li["price_krw"] is not None:
                opt = (LABEL[li["unit"]], li["pour_ml"], li["price_krw"])
                if opt not in e["options"]:
                    e["options"].append(opt)
                else:
                    report[bar["key"]]["dup_option"] += 1

written = []
bar_by_key = {b["key"]: (b, loadable) for b, loadable in bars_by_label.values()}
for bar_key, entries in per_bar.items():
    bar, loadable = bar_by_key[bar_key]
    bid = bar["id"]
    menu_entries = []
    for order, (prod_id, e) in enumerate(entries.items(), start=1):
        # glass before bottle, then smaller pour first (as build_menu_seeds_demo.py)
        opts = sorted(e["options"], key=lambda o: (0 if o[0] == "잔" else 1, o[1] or 0))
        name = e["names"][0][:200]
        menu_entries.append({
            "product_id": prod_id,
            "product_key": e["product"]["key"],
            "display_name": name,
            "options": [
                {"option_label": lab, "pour_ml": pour, "price_krw": price, "sort_order": i,
                 "id": str(uuid.uuid5(MENU_NS, f"{bid}|{prod_id}|opt|{lab}|{pour}|{price}|{i}"))}
                for i, (lab, pour, price) in enumerate(opts, start=1)
            ],
            "sort_order": order,
            "bar_menu_item_id": str(uuid.uuid5(MENU_NS, f"{bid}|{prod_id}|item")),
            "menu_board_entry_id": str(uuid.uuid5(MENU_NS, f"{bid}|{prod_id}|entry")),
        })
        report[bar_key]["entries"] += 1
        report[bar_key]["options"] += len(opts)
        if not opts:
            report[bar_key]["entries_without_option"] += 1
        if e["product"]["key"] in {p["key"] for p in new_products}:
            report[bar_key]["entries_new_product"] += 1
    seed = {
        "version": "menu_seed_demo_v1",
        "menu_board_id": str(uuid.uuid5(MENU_NS, f"{bid}|board")),
        "bar_id": bid,
        "bar_key": bar["key"],
        "purpose": "Demo (2026-11-03, I3 heuristic evaluation): pre-published menu from human-reviewed labels so "
                   "customer search works. Not pipeline output.",
        "source": "eval/labels_i3_v1.json + eval/match_gold_i3_v1.json; unknown and non_whisky lines skipped; "
                  "both: lines give each named product the line's options; new: products from "
                  "catalog_v2_service_i3_additions.json",
        "entries": menu_entries,
    }
    out = (CATALOG_DIR if loadable else PENDING_DIR) / f"menu_seed_{bar['key']}_demo_v1.json"
    dump(out, seed)
    written.append(out)

print(f"additions: {len(new_brands)} new brands, {len(new_products)} new products -> {ADDITIONS.relative_to(REPO)}")
for bar_key, c in report.items():
    print(bar_key, dict(c))
print("problems:", len(problems))
for p in problems:
    print("  ", p)
for f in written:
    print(f.relative_to(REPO))
sys.exit(1 if problems else 0)
