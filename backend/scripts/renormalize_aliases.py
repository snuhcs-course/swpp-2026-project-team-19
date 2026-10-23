"""Recompute `normalized_alias` for every brand and product alias with the current `normalize()`.

Run this when the normalization rules in `app/core/normalize.py` change (matching flow
doc, section 7). Without `--apply` it only reports what would change.

For each alias the new value is `normalize(alias_text)`. Aliases of the same brand or
product that now normalize to the same value keep one row (searchable first, then the
one whose value is unchanged, then the oldest) and the others are deleted, as the
(owner, normalized_alias) unique constraint requires. Aliases that normalize to an
empty string are deleted. Values that become shared by different brands or products
are reported, since they turn exact matches into ambiguous ones.

Aliases skipped by the seed because they collided under the old rules are not in the
database, so re-run `scripts/seed_catalog.py` afterwards to add any that are now distinct.

    cd backend
    uv run --env-file .env python scripts/renormalize_aliases.py           # dry run
    uv run --env-file .env python scripts/renormalize_aliases.py --apply
    uv run --env-file .env python scripts/seed_catalog.py
"""

import argparse
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import Connection, Table, bindparam, delete, literal, select, update

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.normalize import normalize  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.models import Brand, BrandAlias, Product, ProductAlias  # noqa: E402


@dataclass(frozen=True)
class AliasRow:
    id: UUID
    owner_id: UUID
    alias_text: str
    normalized_alias: str
    created_at: datetime
    is_searchable: bool = True


@dataclass
class Plan:
    total: int = 0
    updates: dict[UUID, str] = field(default_factory=dict)
    # (deleted row, the row kept for the same owner and value); kept is None for empty values.
    deletes: list[tuple[AliasRow, AliasRow | None]] = field(default_factory=list)
    # value -> owners, for values shared by several owners after but not before.
    newly_shared: dict[str, set[UUID]] = field(default_factory=dict)


def owners_by_value(pairs: Iterable[tuple[UUID, str]]) -> dict[str, set[UUID]]:
    owners: dict[str, set[UUID]] = defaultdict(set)
    for owner_id, value in pairs:
        owners[value].add(owner_id)
    return owners


def plan_renormalization(rows: list[AliasRow], normalize_fn: Callable[[str], str] = normalize) -> Plan:
    plan = Plan(total=len(rows))
    groups: dict[tuple[UUID, str], list[AliasRow]] = defaultdict(list)
    for row in rows:
        new_value = normalize_fn(row.alias_text)
        if not new_value:
            plan.deletes.append((row, None))
            continue
        groups[(row.owner_id, new_value)].append(row)

    kept: list[tuple[UUID, str]] = []
    for (owner_id, new_value), members in groups.items():
        members.sort(
            key=lambda r: (not r.is_searchable, r.normalized_alias != new_value, r.created_at, str(r.id))
        )
        keep, *duplicates = members
        if keep.normalized_alias != new_value:
            plan.updates[keep.id] = new_value
        plan.deletes.extend((row, keep) for row in duplicates)
        kept.append((owner_id, new_value))

    before = owners_by_value((row.owner_id, row.normalized_alias) for row in rows)
    for value, owners in owners_by_value(kept).items():
        if len(owners) > 1 and len(before.get(value, ())) < len(owners):
            plan.newly_shared[value] = owners
    return plan


def load_rows(conn: Connection, table: Table, owner_column: str) -> list[AliasRow]:
    searchable = table.c.is_searchable if "is_searchable" in table.c else literal(True)
    query = select(
        table.c.id,
        table.c[owner_column],
        table.c.alias_text,
        table.c.normalized_alias,
        table.c.created_at,
        searchable,
    )
    return [AliasRow(*row) for row in conn.execute(query)]


def apply_plan(conn: Connection, table: Table, plan: Plan) -> None:
    if plan.deletes:
        conn.execute(delete(table).where(table.c.id.in_([row.id for row, _ in plan.deletes])))
    if not plan.updates:
        return
    stmt = update(table).where(table.c.id == bindparam("row_id")).values(normalized_alias=bindparam("value"))
    # Unique checks run per row, so two aliases swapping values would collide mid-update.
    # Park the rows on placeholders first; "~" never survives normalize().
    conn.execute(stmt, [{"row_id": row_id, "value": f"~{row_id}"} for row_id in plan.updates])
    conn.execute(stmt, [{"row_id": row_id, "value": value} for row_id, value in plan.updates.items()])


def report(name: str, plan: Plan, display_names: dict[UUID, str]) -> None:
    print(
        f"{name}: {plan.total} rows, update {len(plan.updates)}, delete {len(plan.deletes)}, "
        f"newly shared values {len(plan.newly_shared)}"
    )
    for row, keep in plan.deletes:
        reason = f"same value as {keep.alias_text!r}" if keep else "normalizes to empty"
        print(f"  delete {row.alias_text!r} ({display_names.get(row.owner_id, row.owner_id)}): {reason}")
    for value, owners in sorted(plan.newly_shared.items()):
        names = ", ".join(sorted(display_names.get(owner, str(owner)) for owner in owners))
        print(f"  newly shared {value!r}: {names}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args()

    targets = (
        ("brand_aliases", BrandAlias.__table__, "brand_id", Brand.__table__.c.canonical_name),
        ("product_aliases", ProductAlias.__table__, "product_id", Product.__table__.c.display_name),
    )
    # One transaction for both tables; it is committed only with --apply.
    with get_engine().connect() as conn:
        for name, table, owner_column, label in targets:
            display_names = dict(conn.execute(select(label.table.c.id, label)).all())
            plan = plan_renormalization(load_rows(conn, table, owner_column))
            report(name, plan, display_names)
            if args.apply:
                apply_plan(conn, table, plan)
        if args.apply:
            conn.commit()
            print("\napplied. Re-run scripts/seed_catalog.py to add aliases that are now distinct.")
        else:
            print("\ndry run: nothing written. Re-run with --apply.")


if __name__ == "__main__":
    main()
