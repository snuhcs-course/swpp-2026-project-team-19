# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9). Reviewed by Haeul Yang.
"""Reset a bar's current menu board to a seed file (default: the Seorosang demo menu).

The bar and every product in the menu must already exist, so run `seed_catalog.py` first.
Running this replaces the bar's board entries and options with the seed contents and sets
`published_at` to now, so it also restores the menu after testing uploads or publishing.
Bar menu items are reused by (bar_id, product_id) and never deleted. Everything runs in
one transaction.

    cd backend
    uv run --env-file .env python scripts/seed_catalog.py
    uv run --env-file .env python scripts/seed_menu.py
"""

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import Connection, delete, func, select
from sqlalchemy.dialects.postgresql import insert

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import get_engine  # noqa: E402
from app.models import Bar, BarMenuItem, MenuBoard, MenuBoardEntry, MenuEntryOption, Product  # noqa: E402

CATALOG_DIR = BACKEND_DIR.parent / "ai" / "catalog"

bars = Bar.__table__
products = Product.__table__
bar_menu_items = BarMenuItem.__table__
menu_boards = MenuBoard.__table__
entries_table = MenuBoardEntry.__table__
options_table = MenuEntryOption.__table__


def check_references(conn: Connection, menu: dict) -> None:
    if conn.execute(select(bars.c.id).where(bars.c.id == menu["bar_id"])).first() is None:
        raise SystemExit(f"Bar {menu['bar_key']} ({menu['bar_id']}) is missing. Run scripts/seed_catalog.py first.")
    product_ids = {UUID(entry["product_id"]) for entry in menu["entries"]}
    found = set(conn.execute(select(products.c.id).where(products.c.id.in_(product_ids))).scalars())
    missing = sorted(entry["product_key"] for entry in menu["entries"] if UUID(entry["product_id"]) not in found)
    if missing:
        raise SystemExit(f"Products missing from the catalog: {', '.join(missing)}. Run scripts/seed_catalog.py first.")


def bar_menu_item_ids(conn: Connection, bar_id: str, entries: list[dict]) -> dict[UUID, UUID]:
    """Map product_id to the bar's menu item id, creating items that do not exist yet."""
    rows = [{"id": e["bar_menu_item_id"], "bar_id": bar_id, "product_id": e["product_id"]} for e in entries]
    # A menu item published later may already hold (bar_id, product_id) under another id.
    conn.execute(
        insert(bar_menu_items).values(rows).on_conflict_do_nothing(index_elements=["bar_id", "product_id"])
    )
    query = select(bar_menu_items.c.product_id, bar_menu_items.c.id).where(bar_menu_items.c.bar_id == bar_id)
    return dict(conn.execute(query).all())


def reset_board(conn: Connection, menu: dict) -> UUID:
    stmt = insert(menu_boards).values(
        id=menu["menu_board_id"], bar_id=menu["bar_id"], last_import_id=None, published_at=func.now()
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["bar_id"],
        set_={"last_import_id": None, "published_at": func.now()},
    ).returning(menu_boards.c.id)
    board_id = conn.execute(stmt).scalar_one()

    entry_ids = select(entries_table.c.id).where(entries_table.c.menu_board_id == board_id)
    conn.execute(delete(options_table).where(options_table.c.menu_board_entry_id.in_(entry_ids)))
    conn.execute(delete(entries_table).where(entries_table.c.menu_board_id == board_id))
    return board_id


def seed(conn: Connection, menu: dict) -> None:
    check_references(conn, menu)
    item_ids = bar_menu_item_ids(conn, menu["bar_id"], menu["entries"])
    board_id = reset_board(conn, menu)

    entry_rows = [
        {
            "id": e["menu_board_entry_id"],
            "menu_board_id": board_id,
            "bar_menu_item_id": item_ids[UUID(e["product_id"])],
            "display_name": e["display_name"],
            "sort_order": e["sort_order"],
        }
        for e in menu["entries"]
    ]
    option_rows = [
        {
            "id": o["id"],
            "menu_board_entry_id": e["menu_board_entry_id"],
            "option_label": o["option_label"],
            "pour_ml": o["pour_ml"],
            "price_krw": o["price_krw"],
            "sort_order": o["sort_order"],
        }
        for e in menu["entries"]
        for o in e["options"]
    ]
    conn.execute(insert(entries_table).values(entry_rows))
    conn.execute(insert(options_table).values(option_rows))
    print(f"menu board {board_id} for {menu['bar_key']}: {len(entry_rows)} entries, {len(option_rows)} options")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--menu", type=Path, default=CATALOG_DIR / "menu_seed_seorosang_v1.json")
    args = parser.parse_args()

    menu = json.loads(args.menu.read_text(encoding="utf-8"))
    print(f"menu: {args.menu.name} ({menu['version']})")
    with get_engine().begin() as conn:
        seed(conn, menu)


if __name__ == "__main__":
    main()
