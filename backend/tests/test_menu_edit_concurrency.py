"""Two manual adds for two bars at the same time, both creating the same new brand (spec 3.14.3, 9.5).

The bars' row locks do not order requests for different bars, so only the catalog checks inside
SERIALIZABLE transactions keep the brand single. Unlike the other API tests, these requests run on
their own connections and really commit, so that they can overlap; the rows are deleted afterwards.
"""

import threading

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import Brand
from app.schemas.menu import BarMenuResponse
from app.schemas.menu_edit import MenuItemAddRequest
from app.services import menu_edit, serializable
from app.services.menu_review_catalog import _CatalogWriter
from tests.auth_support import TEMPORARY_OPERATOR
from tests.factories import make_bar

BRAND = "Concurrent Distillery"

CLEANUP = [
    "DELETE FROM menu_entry_options WHERE menu_board_entry_id IN (SELECT e.id FROM menu_board_entries e "
    "JOIN menu_boards b ON b.id = e.menu_board_id WHERE b.bar_id = ANY(:bars))",
    "DELETE FROM menu_board_entries WHERE menu_board_id IN (SELECT id FROM menu_boards WHERE bar_id = ANY(:bars))",
    "DELETE FROM menu_boards WHERE bar_id = ANY(:bars)",
    "DELETE FROM bar_menu_items WHERE bar_id = ANY(:bars)",
    "DELETE FROM product_aliases WHERE product_id IN (SELECT p.id FROM products p "
    "JOIN brands b ON b.id = p.brand_id WHERE b.canonical_name = :brand)",
    "DELETE FROM products WHERE brand_id IN (SELECT id FROM brands WHERE canonical_name = :brand)",
    "DELETE FROM brand_aliases WHERE brand_id IN (SELECT id FROM brands WHERE canonical_name = :brand)",
    "DELETE FROM brands WHERE canonical_name = :brand",
    "DELETE FROM bars WHERE id = ANY(:bars)",
]


@pytest.fixture
def two_bars(db_engine):
    """Two committed bars without a menu; everything the test creates for them is deleted afterwards."""
    with Session(db_engine) as session:
        bars = [make_bar(session, f"Concurrent Bar {n}") for n in (1, 2)]
        session.commit()
        bar_ids = [bar.id for bar in bars]
    try:
        yield bar_ids
    finally:
        with db_engine.begin() as conn:
            for statement in CLEANUP:
                conn.execute(text(statement), {"bars": bar_ids, "brand": BRAND})


def test_two_bars_adding_the_same_new_brand_create_it_once(db_engine, two_bars, monkeypatch):
    # Both requests look the brand up and find nothing before either creates it.
    both_looked = threading.Barrier(2, timeout=10)
    first_lookup = threading.local()
    real_find = _CatalogWriter._find_brand

    def find_then_wait(self, decision):
        found = real_find(self, decision)
        if not getattr(first_lookup, "done", False):
            first_lookup.done = True
            both_looked.wait()
        return found

    monkeypatch.setattr(_CatalogWriter, "_find_brand", find_then_wait)
    monkeypatch.setattr(serializable, "sleep", lambda seconds: None)
    body = MenuItemAddRequest.model_validate(
        {
            "menuVersion": None,
            "newProduct": {"brand": {"type": "new", "canonicalName": BRAND}, "product": {"displayName": "Concurrent 12"}},
            "options": [{"priceKrw": 15000}],
        }
    )
    serializable_engine = db_engine.execution_options(isolation_level="SERIALIZABLE")
    outcomes = {}

    def add(bar_id):
        try:
            outcomes[bar_id] = menu_edit.add_menu_item(
                lambda: Session(serializable_engine), TEMPORARY_OPERATOR, bar_id, body
            )
        except Exception as error:  # noqa: BLE001 - recorded for the assertions below
            outcomes[bar_id] = error

    threads = [threading.Thread(target=add, args=(bar_id,)) for bar_id in two_bars]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    added = [o for o in outcomes.values() if isinstance(o, BarMenuResponse)]
    refused = [o for o in outcomes.values() if isinstance(o, ApiError)]
    assert (len(added), len(refused)) == (1, 1), outcomes
    assert [item.brandName for item in added[0].items] == [BRAND]
    # The later request ran again, saw the committed brand, and was told to pick it.
    assert (refused[0].status_code, refused[0].code) == (409, "DUPLICATE_BRAND_FOUND")
    assert refused[0].details["existingBrand"]["canonicalName"] == BRAND
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Brand).where(Brand.canonical_name == BRAND)) == 1
