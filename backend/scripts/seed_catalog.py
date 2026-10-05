"""Load the pilot bars and the product catalog seed (ai/catalog/) into the database.

Brands, products, and bars are upserted by id, so re-running after editing the JSON
updates changed rows. Aliases get `normalized_alias` from the shared `normalize()` and
are inserted with ON CONFLICT DO NOTHING: rows whose id already exists, or that
normalize to a value the same brand or product already has, are skipped.
Rows removed from the JSON are not deleted. Everything runs in one transaction.

    cd backend
    uv run --env-file .env alembic upgrade head
    uv run --env-file .env python scripts/seed_catalog.py
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Connection, Table, literal_column, or_
from sqlalchemy.dialects.postgresql import insert

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.normalize import normalize  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.models import Bar, Brand, BrandAlias, Product, ProductAlias  # noqa: E402

CATALOG_DIR = BACKEND_DIR.parent / "ai" / "catalog"


def upsert(conn: Connection, table: Table, rows: list[dict]) -> tuple[int, int]:
    """Insert rows or update them by id when a value differs. Returns (inserted, updated)."""
    if not rows:
        return 0, 0
    stmt = insert(table).values(rows)
    columns = [name for name in rows[0] if name != "id"]
    changed = or_(*(table.c[name].is_distinct_from(stmt.excluded[name]) for name in columns))
    set_ = {name: stmt.excluded[name] for name in columns}
    if "updated_at" in table.c:
        set_["updated_at"] = literal_column("now()")
    # xmax is 0 only for rows this statement inserted rather than updated.
    stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=set_, where=changed).returning(
        literal_column("xmax = 0")
    )
    results = conn.execute(stmt).scalars().all()
    inserted = sum(results)
    return inserted, len(results) - inserted


def insert_aliases(conn: Connection, table: Table, rows: list[dict]) -> int:
    """Insert alias rows, skipping any that hit a unique constraint. Returns the inserted count."""
    if not rows:
        return 0
    stmt = insert(table).values(rows).on_conflict_do_nothing().returning(table.c.id)
    return len(conn.execute(stmt).all())


def alias_rows(owner_column: str, owner_id: str, aliases: list[dict], extra: tuple[str, ...] = ()) -> list[dict]:
    rows = []
    for alias in aliases:
        normalized = normalize(alias["alias_text"])
        if not normalized:
            continue
        row = {
            "id": alias["id"],
            owner_column: owner_id,
            "alias_text": alias["alias_text"],
            "normalized_alias": normalized,
            "language_code": alias.get("language_code"),
        }
        row.update({name: alias[name] for name in extra if name in alias})
        rows.append(row)
    return rows


def seed(conn: Connection, catalog: dict, bars: dict) -> None:
    brands = [{"id": b["id"], "canonical_name": b["canonical_name"]} for b in catalog["brands"]]
    products = [
        {
            "id": p["id"],
            "brand_id": p["brand_id"],
            "category": p["category"],
            "display_name": p["display_name"],
            "age_years": p["age_years"],
            "edition_name": p["edition_name"],
            "abv": p["abv"],
            "is_active": p.get("is_active", True),
        }
        for p in catalog["products"]
    ]
    bar_rows = [
        {
            "id": b["id"],
            "name": b["name"],
            "address": b["address"],
            # str() keeps the JSON digits exact for NUMERIC(9, 6).
            "latitude": Decimal(str(b["latitude"])),
            "longitude": Decimal(str(b["longitude"])),
            "phone": b["phone"],
            "status": b["status"],
        }
        for b in bars["bars"]
    ]
    brand_aliases = [
        row for b in catalog["brands"] for row in alias_rows("brand_id", b["id"], b["aliases"])
    ]
    product_aliases = [
        row
        for p in catalog["products"]
        for row in alias_rows("product_id", p["id"], p["aliases"], extra=("is_searchable",))
    ]

    for name, table, rows in (
        ("bars", Bar.__table__, bar_rows),
        ("brands", Brand.__table__, brands),
        ("products", Product.__table__, products),
    ):
        inserted, updated = upsert(conn, table, rows)
        print(f"{name:<16} {len(rows):>4} in seed, inserted {inserted}, updated {updated}")
    for name, table, rows in (
        ("brand_aliases", BrandAlias.__table__, brand_aliases),
        ("product_aliases", ProductAlias.__table__, product_aliases),
    ):
        inserted = insert_aliases(conn, table, rows)
        print(f"{name:<16} {len(rows):>4} in seed, inserted {inserted}, skipped {len(rows) - inserted}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_v1_draft.json")
    parser.add_argument("--bars", type=Path, default=CATALOG_DIR / "bars_v1.json")
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    bars = json.loads(args.bars.read_text(encoding="utf-8"))
    print(f"catalog: {args.catalog.name} ({catalog['version']})  bars: {args.bars.name} ({bars['version']})")

    with get_engine().begin() as conn:
        seed(conn, catalog, bars)


if __name__ == "__main__":
    main()
