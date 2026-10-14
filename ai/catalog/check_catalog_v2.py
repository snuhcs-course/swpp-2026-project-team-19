# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, A3). Review pending.
"""Checks for a catalog JSON in the catalog_v1_draft format (v2 draft and its snapshots).

    python ai/catalog/check_catalog_v2.py [catalog.json ...]   # default: catalog_v2_draft.json

Normalization is the backend's shared function (backend/app/core/normalize.py), the one that
fills normalized_alias at load time. Reports, per catalog:
1. normalized aliases shared by different products (or different brands): must be 0; listed, not fixed
2. normalized duplicates inside one product / brand (skipped at load, ON CONFLICT DO NOTHING)
3. FK integrity and unique ids
4. ids regenerated from keys (UUIDv5, v1 namespace) are identical
5. aliases per source, products per bar (`sources`)
Exit code 1 if 1, 3 or 4 fails.
"""

from __future__ import annotations

import json
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
from app.core.normalize import normalize  # noqa: E402

NS = uuid.UUID("6b1a1f4e-19b0-4c7a-9a7e-b0771e3a0019")
DEFAULT = REPO_ROOT / "ai" / "catalog" / "catalog_v2_draft.json"


def uid(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def shared_aliases(owners: list[dict]) -> list[tuple[str, list[tuple[str, str]]]]:
    """Normalized aliases used by more than one owner: [(normalized, [(owner key, alias text)])]."""
    by_norm: dict[str, dict[str, str]] = defaultdict(dict)
    for o in owners:
        for a in o["aliases"]:
            by_norm[normalize(a["alias_text"])].setdefault(o["key"], a["alias_text"])
    return [(n, sorted(keys.items())) for n, keys in sorted(by_norm.items()) if len(keys) > 1]


def inner_duplicates(owners: list[dict]) -> int:
    return sum(len(o["aliases"]) - len({normalize(a["alias_text"]) for a in o["aliases"]}) for o in owners)


def check(path: Path) -> dict:
    cat = json.loads(path.read_text(encoding="utf-8"))
    brands, products = cat["brands"], cat["products"]
    brand_ids = {b["id"] for b in brands}
    brand_by_key = {b["key"]: b for b in brands}
    errors: list[str] = []

    empty = [(o["key"], a["alias_text"]) for o in brands + products for a in o["aliases"]
             if not normalize(a["alias_text"])]
    if empty:
        errors.append(f"aliases that normalize to an empty string: {empty}")

    ids = [b["id"] for b in brands] + [p["id"] for p in products] + \
          [a["id"] for o in brands + products for a in o["aliases"]]
    dup_ids = [i for i, n in Counter(ids).items() if n > 1]
    if dup_ids:
        errors.append(f"duplicate ids: {dup_ids}")
    for key_list, what in (([b["key"] for b in brands], "brand"), ([p["key"] for p in products], "product")):
        dup = [k for k, n in Counter(key_list).items() if n > 1]
        if dup:
            errors.append(f"duplicate {what} keys: {dup}")
    fk = [p["key"] for p in products if p["brand_id"] not in brand_ids
          or brand_by_key.get(p["brand_key"], {}).get("id") != p["brand_id"]]
    if fk:
        errors.append(f"products with a broken brand FK: {fk}")
    no_alias = [o["key"] for o in brands + products if not o["aliases"]]

    regen = []
    for b in brands:
        regen += [b["key"]] if uid(f"brand:{b['key']}") != b["id"] else []
        regen += [f"{b['key']}:{a['alias_text']}" for a in b["aliases"]
                  if uid(f"balias:{b['key']}:{a['alias_text']}") != a["id"]]
    for p in products:
        regen += [p["key"]] if uid(f"product:{p['key']}") != p["id"] else []
        regen += [f"{p['key']}:{a['alias_text']}" for a in p["aliases"]
                  if uid(f"palias:{p['key']}:{a['alias_text']}") != a["id"]]
    if regen:
        errors.append(f"ids that differ when regenerated: {regen}")

    product_conflicts = shared_aliases(products)
    brand_conflicts = shared_aliases(brands)
    sources = Counter(s for p in products for a in p["aliases"] for s in a.get("sources", []))
    brand_sources = Counter(s for b in brands for a in b["aliases"] for s in a.get("sources", []))
    per_bar = Counter(s for p in products for s in p.get("sources", []))
    return {
        "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "counts": {"brands": len(brands), "brand_aliases": sum(len(b["aliases"]) for b in brands),
                   "products": len(products), "product_aliases": sum(len(p["aliases"]) for p in products)},
        "cross_product_alias_conflicts": product_conflicts,
        "cross_brand_alias_conflicts": brand_conflicts,
        "inner_duplicates": {"product": inner_duplicates(products), "brand": inner_duplicates(brands)},
        "integrity_errors": errors,
        "owners_without_alias": no_alias,
        "product_aliases_per_source": dict(sorted(sources.items())),
        "brand_aliases_per_source": dict(sorted(brand_sources.items())),
        "products_per_bar": dict(sorted(per_bar.items())),
    }


def main() -> None:
    paths = [Path(p).resolve() for p in sys.argv[1:]] or [DEFAULT]
    failed = False
    for path in paths:
        r = check(path)
        print(f"== {r['file']}")
        print(f"  counts: {r['counts']}")
        print(f"  cross-product alias conflicts: {len(r['cross_product_alias_conflicts'])}")
        for norm, owners in r["cross_product_alias_conflicts"]:
            print(f"    {norm}: " + "; ".join(f"{k} ({t})" for k, t in owners))
        print(f"  cross-brand alias conflicts: {len(r['cross_brand_alias_conflicts'])}")
        for norm, owners in r["cross_brand_alias_conflicts"]:
            print(f"    {norm}: " + "; ".join(f"{k} ({t})" for k, t in owners))
        print(f"  normalized duplicates inside one owner (skipped at load): {r['inner_duplicates']}")
        print(f"  integrity: {'OK' if not r['integrity_errors'] else r['integrity_errors']}")
        if r["owners_without_alias"]:
            print(f"  owners without alias: {r['owners_without_alias']}")
        print(f"  product aliases per source: {r['product_aliases_per_source']}")
        print(f"  brand aliases per source: {r['brand_aliases_per_source']}")
        print(f"  products per bar: {r['products_per_bar']}")
        failed |= bool(r["cross_product_alias_conflicts"] or r["integrity_errors"])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
