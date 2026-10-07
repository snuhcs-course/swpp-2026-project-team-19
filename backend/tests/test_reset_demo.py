"""reset_demo.py brings a rehearsed database back to the state right after seeding."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.normalize import normalize
from app.models import (
    Bar,
    BarMenuItem,
    Brand,
    BrandAlias,
    LineType,
    MenuBoard,
    MenuBoardEntry,
    MenuEntryOption,
    MenuImport,
    Product,
    ProductAlias,
)
from app.services.menu_review_validation import load_items, pending_changes
from scripts import seed_catalog, seed_menu
from scripts.reset_demo import CATALOG_DIR, Seeds, delete_photos, plan, reset
from tests.factories import make_bar

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"
SEED_FILES = [CATALOG_DIR / name for name in ("catalog_v1_draft.json", "bars_v1.json", "menu_seed_seorosang_v1.json")]

pytestmark = pytest.mark.skipif(
    not all(path.exists() for path in SEED_FILES), reason="ai/catalog seed is not checked out"
)


@pytest.fixture
def seeds():
    return Seeds.load(*SEED_FILES[:2], [SEED_FILES[2]])


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


def snapshot(session):
    """Every row seeding writes, without timestamps."""

    def rows(*columns):
        return sorted(tuple(row) for row in session.execute(select(*columns)))

    return {
        "bars": rows(Bar.id, Bar.name, Bar.address, Bar.status),
        "brands": rows(Brand.id, Brand.canonical_name),
        "brand aliases": rows(BrandAlias.id, BrandAlias.brand_id, BrandAlias.normalized_alias),
        "products": rows(Product.id, Product.display_name, Product.is_active, Product.created_from_extracted_item_id),
        "product aliases": rows(ProductAlias.id, ProductAlias.product_id, ProductAlias.normalized_alias),
        "bar menu items": rows(BarMenuItem.id, BarMenuItem.bar_id, BarMenuItem.product_id),
        "boards": rows(MenuBoard.id, MenuBoard.bar_id, MenuBoard.last_import_id),
        "entries": rows(MenuBoardEntry.id, MenuBoardEntry.bar_menu_item_id, MenuBoardEntry.display_name),
        "options": rows(MenuEntryOption.id, MenuEntryOption.price_krw, MenuEntryOption.source_extracted_option_id),
        "imports": rows(MenuImport.id),
    }


def seed_fresh(session, seeds):
    conn = session.connection()
    seed_catalog.seed(conn, seeds.catalog, seeds.bars)
    for menu in seeds.menus:
        seed_menu.seed(conn, menu)
    session.expire_all()


def upload(client, bar_id, headers, filename="sample.jpg"):
    response = client.post(
        f"/api/bars/{bar_id}/menu-imports",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        data={"mode": "full_replace"},
        files=[("images", (filename, JPEG, "image/jpeg"))],
    )
    assert response.status_code == 202, response.text
    return response.json()["menuImportId"]


def rehearse(client, session, operator, seeds):
    """What a rehearsal leaves: an applied import that created a brand and product and
    replaced the Seorosang menu, a failed import at another bar, an alias added to a seed
    product, an edited seed product, and a bar that is not in the seed."""
    bar_ids = {b["key"]: UUID(b["id"]) for b in seeds.bars["bars"]}
    seorosang, bokchun = bar_ids["seorosang"], bar_ids["whisky-bokchun"]
    import_id = upload(client, seorosang, operator)
    session.expire_all()
    menu_import = session.get(MenuImport, import_id)
    items = load_items(session, menu_import)
    created = next(i for i in items if i.raw_text.startswith("Unknown Distillery"))
    body = {
        "reviewVersion": 1,
        "itemDecisions": [
            {"action": "confirm_non_product", "extractedItemId": str(i.id), "finalLineType": i.extracted_line_type.value}
            if i.extracted_line_type != LineType.PRODUCT
            else {
                "action": "create_product",
                "extractedItemId": str(i.id),
                "finalLineType": "product",
                "brand": {"type": "new", "canonicalName": "Unknown Distillery"},
                "product": {"displayName": "Unknown Distillery 25", "ageYears": 25},
            }
            if i.id == created.id
            else {"action": "reject", "extractedItemId": str(i.id), "finalLineType": "product"}
            for i in items
        ],
        "changeDecisions": [
            {
                "changeId": str(c.id),
                "decision": "apply" if c.extracted_item_id in (None, created.id) else "ignore",
            }
            for c in pending_changes(session, menu_import)
        ],
    }
    response = client.post(f"/api/menu-imports/{import_id}/review-and-apply", json=body, headers=operator)
    assert response.status_code == 200, response.text
    upload(client, bokchun, operator, filename="fail.jpg")

    product = session.scalars(select(Product).order_by(Product.display_name)).first()
    session.add(ProductAlias(product_id=product.id, alias_text="리허설 별칭", normalized_alias=normalize("리허설 별칭")))
    product.is_active = False
    make_bar(session, "Rehearsal Bar")
    session.flush()


def test_reset_restores_the_freshly_seeded_state(client, db_session, image_storage, operator, seeds):
    seed_fresh(db_session, seeds)
    fresh = snapshot(db_session)
    rehearse(client, db_session, operator, seeds)
    db_session.expire_all()
    assert snapshot(db_session) != fresh
    stored = [p for p in image_storage.root.rglob("*") if p.is_file()]
    assert len(stored) == 2

    keys = reset(db_session, seeds)
    db_session.flush()

    assert snapshot(db_session) == fresh
    assert [description for description, rows in plan(db_session, seeds) if rows] == [
        "menu boards",
        "menu board entries",
        "bar menu items",
    ]
    # Bars without a seed menu have no board.
    assert db_session.scalar(select(func.count()).select_from(MenuBoard)) == 1
    assert sorted(keys) == sorted(str(p.relative_to(image_storage.root)) for p in stored)
    assert delete_photos(image_storage, keys) == []
    assert not any(p.is_file() for p in image_storage.root.rglob("*"))


def test_plan_counts_without_changing_anything(client, db_session, image_storage, operator, seeds):
    seed_fresh(db_session, seeds)
    rehearse(client, db_session, operator, seeds)
    db_session.expire_all()
    before = snapshot(db_session)

    counts = dict(plan(db_session, seeds))

    assert snapshot(db_session) == before
    assert counts["menu imports (all statuses)"] == 2
    assert counts["menu photos"] == 2
    assert counts["brands not in the seed"] == 1
    assert counts["products not in the seed"] == 1
    assert counts["bars not in the seed"] == 1
    # The created product's own aliases and the one added to a seed product.
    assert counts["product aliases not in the seed"] >= 2


def test_reset_of_a_fresh_database_changes_nothing(db_session, seeds):
    seed_fresh(db_session, seeds)
    fresh = snapshot(db_session)

    assert reset(db_session, seeds) == []
    db_session.flush()

    assert snapshot(db_session) == fresh


def test_photos_that_cannot_be_deleted_are_reported(image_storage):
    class Stuck:
        def delete(self, key):
            raise OSError("bucket unreachable")

    assert delete_photos(Stuck(), ["menus/a/page-1.jpg"]) == ["menus/a/page-1.jpg"]
