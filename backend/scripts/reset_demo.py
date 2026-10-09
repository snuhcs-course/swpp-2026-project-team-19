# AI-generated with ChatGPT (Haeul Yang, 2026-10-07, PR #20). Reviewed by Haeul Yang.
"""Reset the database to the state right after seeding, e.g. after rehearsing the demo.

What a rehearsal leaves behind is removed:
- every menu import, applied ones included, with all its rows and its photos;
- every menu board and bar menu item;
- every bar, brand, product, and alias whose id is not in the seed files, such as the
  products and aliases created while reviewing.

Then the seeds are loaded again: `seed_catalog.py` (bars, brands, products, aliases; seed
rows edited since get their seed values back) and `seed_menu.py` (the Seorosang menu).
Bars without a seed menu are left without a menu. Users are kept.

The database work runs in one transaction. Photos are deleted after the commit, so a reset
that fails midway changes nothing and never leaves rows pointing at missing photos.
Run it while nobody is uploading: an import that is still being processed would fail.

Without `--apply` it only shows what would be deleted.

    cd backend
    uv run --env-file .env python scripts/reset_demo.py
    uv run --env-file .env python scripts/reset_demo.py --apply
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.storage import ImageStorage  # noqa: E402
from app.api.deps import get_image_storage  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.models import (  # noqa: E402
    Bar,
    BarMenuItem,
    Brand,
    BrandAlias,
    MenuBoard,
    MenuBoardEntry,
    MenuEntryOption,
    MenuImage,
    MenuImport,
    Product,
    ProductAlias,
)
from scripts import seed_catalog, seed_menu  # noqa: E402
from scripts.reset_menu_imports import delete_import_rows  # noqa: E402

CATALOG_DIR = BACKEND_DIR.parent / "ai" / "catalog"


@dataclass(frozen=True)
class Seeds:
    catalog: dict
    bars: dict
    menus: list[dict]

    @classmethod
    def load(cls, catalog: Path, bars: Path, menus: list[Path]) -> "Seeds":
        def read(path: Path) -> dict:
            return json.loads(path.read_text(encoding="utf-8"))

        return cls(read(catalog), read(bars), [read(menu) for menu in menus])

    def ids(self) -> dict[type, set[UUID]]:
        """Seeded ids per model; any other row was created after seeding."""
        brands, products = self.catalog["brands"], self.catalog["products"]
        return {
            Bar: {UUID(b["id"]) for b in self.bars["bars"]},
            Brand: {UUID(b["id"]) for b in brands},
            BrandAlias: {UUID(a["id"]) for b in brands for a in b["aliases"]},
            Product: {UUID(p["id"]) for p in products},
            ProductAlias: {UUID(a["id"]) for p in products for a in p["aliases"]},
        }


# Rows not in the seed, children before parents (the order they are deleted in).
NOT_SEEDED = (ProductAlias, Product, BrandAlias, Brand, Bar)
NAMES = {
    ProductAlias: "product aliases",
    Product: "products",
    BrandAlias: "brand aliases",
    Brand: "brands",
    Bar: "bars",
}


def plan(session: Session, seeds: Seeds) -> list[tuple[str, int]]:
    """What a reset would delete, as (description, row count)."""
    ids = seeds.ids()

    def count(model, *where) -> int:
        return session.scalar(select(func.count()).select_from(model).where(*where))

    return [
        ("menu imports (all statuses)", count(MenuImport)),
        ("menu photos", count(MenuImage)),
        ("menu boards", count(MenuBoard)),
        ("menu board entries", count(MenuBoardEntry)),
        ("bar menu items", count(BarMenuItem)),
        *((f"{NAMES[model]} not in the seed", count(model, model.id.not_in(ids[model]))) for model in NOT_SEEDED),
    ]


def reset(session: Session, seeds: Seeds) -> list[str]:
    """Delete what seeding did not create and load the seeds again, without committing.
    Returns the storage keys of the deleted photos; delete the files after the commit."""
    ids = seeds.ids()
    session.execute(delete(MenuEntryOption))
    session.execute(delete(MenuBoardEntry))
    session.execute(delete(MenuBoard))
    # Products created while reviewing point at the extracted line they came from.
    session.execute(update(Product).values(created_from_extracted_item_id=None))
    keys = delete_import_rows(session, list(session.scalars(select(MenuImport.id))))
    # After the imports: their proposed changes refer to bar menu items.
    session.execute(delete(BarMenuItem))
    for model in NOT_SEEDED:
        session.execute(delete(model).where(model.id.not_in(ids[model])))

    conn = session.connection()
    seed_catalog.seed(conn, seeds.catalog, seeds.bars)
    for menu in seeds.menus:
        seed_menu.seed(conn, menu)
    session.expire_all()
    return keys


def delete_photos(storage: ImageStorage, keys: list[str]) -> list[str]:
    """Delete the photo files; returns the keys that could not be deleted."""
    failed = []
    for key in keys:
        try:
            storage.delete(key)
        except Exception as error:  # an orphaned file only wastes space; report it and go on
            print(f"could not delete photo {key}: {error}")
            failed.append(key)
    return failed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=CATALOG_DIR / "catalog_v1_draft.json")
    parser.add_argument("--bars", type=Path, default=CATALOG_DIR / "bars_v1.json")
    parser.add_argument(
        "--menu", type=Path, action="append", help="seed menu to restore (repeatable; default: the Seorosang menu)"
    )
    parser.add_argument("--apply", action="store_true", help="reset (default: show what would be deleted)")
    args = parser.parse_args()

    seeds = Seeds.load(args.catalog, args.bars, args.menu or [CATALOG_DIR / "menu_seed_seorosang_v1.json"])
    engine = get_engine()
    print(f"database: {engine.url.database} on {engine.url.host}")
    with Session(engine) as session:
        for description, rows in plan(session, seeds):
            print(f"  {description:<32} {rows:>5}")
        if not args.apply:
            print("\ndry run: nothing changed. Re-run with --apply to reset.")
            return
        print()
        keys = reset(session, seeds)
        session.commit()
    failed = delete_photos(get_image_storage(), keys)
    print(f"\nreset done: deleted {len(keys) - len(failed)} of {len(keys)} photo(s)")


if __name__ == "__main__":
    main()
