# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, A3). Review pending.
"""Snapshots of catalog_v2_draft.json (same format as catalog_v1_draft, README section 2 mapping).

    python ai/catalog/export_snapshot.py                   # service + eval snapshots
    python ai/catalog/export_snapshot.py --drop-products   # also the eval snapshot without final-only products

- catalog_v2_service.json: the whole catalog, for the backend load request.
- catalog_v2_eval_5bars.json: for the P47 evaluation (C1 style: the gold product is always in the DB).
  Products of 수이·오드비 stay; aliases whose sources are only menu:수이 / menu:오드비 are removed
  (the bars' own spellings). An alias with another source too is kept.
- --drop-products: catalog_v2_eval_5bars_drop_products.json, the eval snapshot that also drops the
  products seen only at 수이·오드비 (sources only menu:수이 / menu:오드비) and the brands left with
  no product by that. For the new-product test. Off by default.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1].parent
CATALOG_DIR = REPO_ROOT / "ai" / "catalog"
SRC = CATALOG_DIR / "catalog_v2_draft.json"
FINAL_SOURCES = {"menu:수이", "menu:오드비"}


def only_final(sources: list[str]) -> bool:
    return bool(sources) and set(sources) <= FINAL_SOURCES


def eval_snapshot(cat: dict, drop_products: bool) -> tuple[dict, dict]:
    out = copy.deepcopy(cat)
    stats = {"aliases_removed": 0, "products_removed": 0, "brands_removed": 0}
    if drop_products:
        dropped = [p for p in out["products"] if only_final(p.get("sources", []))]
        stats["products_removed"] = len(dropped)
        out["products"] = [p for p in out["products"] if not only_final(p.get("sources", []))]
        used = {p["brand_id"] for p in out["products"]}
        emptied = {p["brand_id"] for p in dropped} - used
        stats["brands_removed"] = len(emptied)
        out["brands"] = [b for b in out["brands"] if b["id"] not in emptied]
    for p in out["products"]:
        kept = [a for a in p["aliases"] if not only_final(a.get("sources", []))]
        stats["aliases_removed"] += len(p["aliases"]) - len(kept)
        p["aliases"] = kept
    return out, stats


def write(cat: dict, name: str, version: str, note: str) -> Path:
    cat = {**cat, "version": version}
    cat["notes"] = cat["notes"] + [note]
    path = CATALOG_DIR / name
    path.write_bytes((json.dumps(cat, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return path


def counts(cat: dict) -> str:
    return (f"brands {len(cat['brands'])}, brand aliases {sum(len(b['aliases']) for b in cat['brands'])}, "
            f"products {len(cat['products'])}, product aliases {sum(len(p['aliases']) for p in cat['products'])}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop-products", action="store_true", help="also write the eval snapshot without "
                    "the products seen only at 수이·오드비")
    args = ap.parse_args()
    cat = json.loads(SRC.read_text(encoding="utf-8"))

    p = write(cat, "catalog_v2_service.json", "catalog_v2_service",
              "Service snapshot: the whole catalog_v2_draft (load request).")
    print(f"wrote {p.name}: {counts(cat)}")

    ev, st = eval_snapshot(cat, drop_products=False)
    p = write(ev, "catalog_v2_eval_5bars.json", "catalog_v2_eval_5bars",
              "P47 evaluation snapshot: aliases whose only sources are menu:수이 / menu:오드비 removed; "
              "products kept (C1 style).")
    print(f"wrote {p.name}: {counts(ev)} (aliases removed {st['aliases_removed']})")

    if args.drop_products:
        ev, st = eval_snapshot(cat, drop_products=True)
        p = write(ev, "catalog_v2_eval_5bars_drop_products.json", "catalog_v2_eval_5bars_drop_products",
                  "New-product test snapshot: as catalog_v2_eval_5bars, and products seen only at 수이·오드비 "
                  "(plus brands left without products) removed.")
        print(f"wrote {p.name}: {counts(ev)} (aliases removed {st['aliases_removed']}, "
              f"products removed {st['products_removed']}, brands removed {st['brands_removed']})")


if __name__ == "__main__":
    main()
