"""Menu requests that overlap on real connections.

- Two manual adds for two bars, both creating the same new brand (spec 3.14.3, 9.5): the bars' row
  locks do not order requests for different bars, so only the catalog checks inside SERIALIZABLE
  transactions keep the brand single.
- A delete that waited for the bar lock while a sold-out mark committed (spec 3.14.8): the delete
  read from an older snapshot, and must still leave the item on sale.

Unlike the other API tests, these requests run on their own connections and really commit, so that
they can overlap; the rows are deleted afterwards.
"""

import threading
import time

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import BarMenuItem, Brand
from app.schemas.menu import BarMenuResponse
from app.schemas.menu_edit import MenuItemAddRequest
from app.services import menu_edit, serializable
from app.services.menu_review_catalog import _CatalogWriter
from tests.auth_support import TEMPORARY_OPERATOR
from tests.factories import make_bar, make_brand, make_product, publish_menu

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
        cleanup(db_engine, bar_ids)


def cleanup(db_engine, bar_ids) -> None:
    with db_engine.begin() as conn:
        for statement in CLEANUP:
            conn.execute(text(statement), {"bars": bar_ids, "brand": BRAND})


@pytest.fixture
def sold_bar(db_engine):
    """A committed bar whose menu, at version 1, has one item on sale: (bar id, bar menu item id)."""
    with Session(db_engine) as session:
        bar = make_bar(session, "Concurrent Bar 1")
        product = make_product(session, make_brand(session, BRAND), "Concurrent 12")
        publish_menu(session, bar, [(product, "Concurrent 12", [(None, 30, 15000)])])
        item_id = session.scalar(select(BarMenuItem.id).where(BarMenuItem.bar_id == bar.id))
        session.commit()
        bar_id = bar.id
    try:
        yield bar_id, item_id
    finally:
        cleanup(db_engine, [bar_id])


def wait_until_a_request_waits_for_a_lock(db_engine) -> None:
    deadline = time.monotonic() + 10
    with db_engine.connect() as conn:
        while time.monotonic() < deadline:
            waiting = conn.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            )
            if waiting:
                return
            conn.rollback()
            time.sleep(0.02)
    raise AssertionError("the request never waited for the bar lock")


def test_a_delete_that_waited_for_a_sold_out_mark_puts_the_item_back_on_sale(
    db_engine, sold_bar, monkeypatch
):
    bar_id, item_id = sold_bar
    attempts = []
    real_delete = menu_edit._delete_once

    def counted(*args):
        attempts.append(1)
        return real_delete(*args)

    monkeypatch.setattr(menu_edit, "_delete_once", counted)
    monkeypatch.setattr(serializable, "sleep", lambda seconds: None)
    serializable_engine = db_engine.execution_options(isolation_level="SERIALIZABLE")
    outcome = []

    def delete():
        try:
            outcome.append(
                menu_edit.delete_menu_item(
                    lambda: Session(serializable_engine), TEMPORARY_OPERATOR, bar_id, str(item_id), 1, base_url=""
                )
            )
        except Exception as error:  # noqa: BLE001 - recorded for the assertions below
            outcome.append(error)

    # The sold-out mark holds the bar lock, as 3.14.8 does, while the delete starts and waits for it.
    with db_engine.connect() as mark:
        mark.execute(text("SELECT id FROM bars WHERE id = :id FOR UPDATE"), {"id": bar_id})
        thread = threading.Thread(target=delete)
        thread.start()
        wait_until_a_request_waits_for_a_lock(db_engine)
        mark.execute(text("UPDATE bar_menu_items SET sold_out_at = now() WHERE id = :id"), {"id": item_id})
        mark.commit()
    thread.join(timeout=30)

    [result] = outcome
    assert isinstance(result, BarMenuResponse), result
    assert result.items == []
    # The first attempt did not see the mark; clearing it anyway failed it, and the retry saw the mark.
    assert len(attempts) == 2
    with Session(db_engine) as session:
        assert session.get(BarMenuItem, item_id).sold_out_at is None


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
            "newProduct": {
                "brand": {"type": "new", "canonicalName": BRAND},
                "product": {"displayName": "Concurrent 12"},
            },
            "options": [{"priceKrw": 15000}],
        }
    )
    serializable_engine = db_engine.execution_options(isolation_level="SERIALIZABLE")
    outcomes = {}

    def add(bar_id):
        try:
            outcomes[bar_id] = menu_edit.add_menu_item(
                lambda: Session(serializable_engine), TEMPORARY_OPERATOR, bar_id, body, base_url=""
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
