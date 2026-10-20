# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-19). Reviewed by Jinwoo Park.
"""Build menu seed files (scripts/seed_menu.py format) from human-reviewed labels + match gold.

One board entry per catalog product per bar (bar_menu_items is unique per bar+product).
Lines whose gold is unknown / non_whisky, or whose product is not in the service catalog, are skipped.
Options: 잔/병 with the label's pour_ml and price; lines with a null price add no option.
IDs are uuid5 so re-running produces the same rows.
"""
import json, uuid, collections, sys, os

# Inputs (copy next to this script): eval/labels_v1_1.json, eval/labels_heldout_v1_1.json, eval/labels_final_v1.json,
# eval/match_gold_v1_1.json, eval/match_gold_final_v1.json (branch i2-p47), catalog_v2_service.json as catalog.json,
# bars_v2.json as bars.json. Output: out/menu_seed_<bar>_demo_v1.json
HERE = os.path.dirname(os.path.abspath(__file__))
NS = uuid.UUID("6f1e2c3a-9b7d-4e21-8a5c-0d4b2e1f7a90")
LABEL = {"glass": "잔", "bottle": "병", None: None}

def load(n):
    return json.load(open(os.path.join(HERE, n), encoding="utf-8"))

catalog = load("catalog.json")
prod_by_key = {p["key"]: p for p in catalog["products"]}
bars = {b["name"]: b for b in (load("bars.json") if isinstance(load("bars.json"), list) else load("bars.json")["bars"])}

SOURCES = [  # (labels file, gold file)
    ("labels_v1_1.json", "match_gold_v1_1.json"),
    ("labels_heldout_v1_1.json", "match_gold_v1_1.json"),
    ("labels_final_v1.json", "match_gold_final_v1.json"),
]
TARGET = {"위스키복춘": "위스키복춘", "미라보": "미라보", "수이": "수이", "오드비": "오드비"}

gold_photos = {}
for _, g in SOURCES:
    for ph in load(g)["photos"]:
        gold_photos[ph["photo_id"]] = ph["items"]

per_bar = collections.OrderedDict()
report = collections.defaultdict(collections.Counter)
problems = []
for lf, _ in SOURCES:
    for ph in load(lf)["photos"]:
        pid = ph["photo_id"]
        bar_label = pid.split("_")[1]
        if bar_label not in TARGET:
            continue
        bar = TARGET[bar_label]
        gitems = gold_photos[pid]
        litems = ph["items"]
        if len(gitems) != len(litems):
            problems.append(f"{pid}: label {len(litems)} vs gold {len(gitems)}")
            continue
        for li, gi in zip(litems, gitems):
            if (li["raw_name"], li["unit"]) != (gi["raw_name"], gi["unit"]):
                problems.append(f"{pid}: mismatch {li['raw_name']!r} vs {gi['raw_name']!r}")
                continue
            g = gi["gold"]
            report[bar]["lines"] += 1
            if g in ("unknown", "non_whisky"):
                report[bar]["skip_" + g] += 1
                continue
            key = g.split(":", 1)[1] if g.startswith("new:") else g
            p = prod_by_key.get(key)
            if p is None:
                report[bar]["skip_not_in_catalog"] += 1
                problems.append(f"{bar}: product key {key} not in catalog ({li['raw_name']})")
                continue
            entries = per_bar.setdefault(bar, collections.OrderedDict())
            e = entries.setdefault(p["id"], {"product": p, "names": [], "options": []})
            if li["raw_name"] not in e["names"]:
                e["names"].append(li["raw_name"])
            if li["price_krw"] is not None:
                opt = (LABEL[li["unit"]], li["pour_ml"], li["price_krw"])
                if opt not in e["options"]:
                    e["options"].append(opt)
                else:
                    report[bar]["dup_option"] += 1
            else:
                report[bar]["null_price_line"] += 1

out_files = []
for bar_name, entries in per_bar.items():
    bar = bars[bar_name]
    bid = bar["id"]
    menu_entries = []
    for order, (prod_id, e) in enumerate(entries.items(), start=1):
        # glass before bottle, then smaller pour first
        opts = sorted(e["options"], key=lambda o: (0 if o[0] == "잔" else 1, o[1] or 0))
        name = e["names"][0]
        if len(name) > 200:
            name = name[:200]
        menu_entries.append({
            "product_id": prod_id,
            "product_key": e["product"]["key"],
            "display_name": name,
            "options": [
                {"option_label": lab, "pour_ml": pour, "price_krw": price, "sort_order": i,
                 "id": str(uuid.uuid5(NS, f"{bid}|{prod_id}|opt|{lab}|{pour}|{price}|{i}"))}
                for i, (lab, pour, price) in enumerate(opts, start=1)
            ],
            "sort_order": order,
            "bar_menu_item_id": str(uuid.uuid5(NS, f"{bid}|{prod_id}|item")),
            "menu_board_entry_id": str(uuid.uuid5(NS, f"{bid}|{prod_id}|entry")),
        })
        report[bar_name]["entries"] += 1
        report[bar_name]["options"] += len(opts)
        if len(e["names"]) > 1:
            report[bar_name]["entries_with_2plus_names"] += 1
    seed = {
        "version": "menu_seed_demo_v1",
        "menu_board_id": str(uuid.uuid5(NS, f"{bid}|board")),
        "bar_id": bid,
        "bar_key": bar["key"],
        "purpose": "Demo (2026-10-19): pre-published menu from human-reviewed labels so customer search works. Not pipeline output.",
        "source": "labels (v1.1 / heldout v1.1 / final v1) + match gold (v1.1 / final v1); unknown and non_whisky lines skipped",
        "entries": menu_entries,
    }
    fn = os.path.join(HERE, "out", f"menu_seed_{bar['key']}_demo_v1.json")
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    json.dump(seed, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out_files.append(fn)

for bar, c in report.items():
    print(bar, dict(c))
print("problems:", len(problems))
for p in problems[:30]:
    print("  ", p)
for f in out_files:
    print(f)
