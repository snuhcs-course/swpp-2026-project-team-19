"""The menu board version, option discount, sold-out and confirmation columns (docs/schema_guide.md 7 and 12)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import MenuEntryOption
from tests.factories import make_bar, make_brand, make_product, make_user, publish_menu

STARTS = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)
ENDS = STARTS + timedelta(days=14)


def _option(db_session) -> MenuEntryOption:
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    board = publish_menu(db_session, make_bar(db_session), [(product, "글렌피딕 12년", [("잔", 30, 17000)])])
    db_session.refresh(board)
    return board.entries[0].options[0]


def test_existing_boards_start_at_version_one(db_session):
    """Insert with plain SQL so the column gets the database default, not the ORM's."""
    board_id = uuid4()
    db_session.execute(
        text("INSERT INTO menu_boards (id, bar_id, published_at) VALUES (:id, :bar, now())"),
        {"id": board_id, "bar": make_bar(db_session).id},
    )

    row = db_session.execute(
        text("SELECT version, confirmed_at, confirmed_by_user_id FROM menu_boards WHERE id = :id"), {"id": board_id}
    ).one()
    # Never confirmed yet.
    assert tuple(row) == (1, None, None)


def test_existing_items_are_on_sale(db_session):
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    item_id = uuid4()
    db_session.execute(
        text("INSERT INTO bar_menu_items (id, bar_id, product_id) VALUES (:id, :bar, :product)"),
        {"id": item_id, "bar": make_bar(db_session).id, "product": product.id},
    )

    sold_out_at = db_session.scalar(text("SELECT sold_out_at FROM bar_menu_items WHERE id = :id"), {"id": item_id})
    assert sold_out_at is None


def test_a_confirmation_records_an_existing_user(db_session):
    board = publish_menu(db_session, make_bar(db_session), [])

    board.confirmed_at, board.confirmed_by_user_id = STARTS, make_user(db_session).id
    db_session.flush()
    board.confirmed_by_user_id = uuid4()
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_board_version_is_positive(db_session):
    board = publish_menu(db_session, make_bar(db_session), [])

    board.version = 0
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_an_option_takes_a_complete_lower_discount(db_session):
    option = _option(db_session)

    option.discount_price_krw, option.discount_starts_at, option.discount_ends_at = 16999, STARTS, ENDS
    db_session.flush()


@pytest.mark.parametrize(
    "discount",
    [
        pytest.param((14000, None, None), id="price only"),
        pytest.param((14000, STARTS, None), id="no end"),
        pytest.param((None, STARTS, ENDS), id="no price"),
        pytest.param((17000, STARTS, ENDS), id="equal to the list price"),
        pytest.param((18000, STARTS, ENDS), id="above the list price"),
        pytest.param((0, STARTS, ENDS), id="zero"),
        pytest.param((14000, ENDS, STARTS), id="ends before it starts"),
        pytest.param((14000, STARTS, STARTS), id="ends when it starts"),
    ],
)
def test_check_constraints_reject_inconsistent_discounts(db_session, discount):
    option = _option(db_session)

    option.discount_price_krw, option.discount_starts_at, option.discount_ends_at = discount
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_catalog_rows_record_their_creator(db_session):
    user = make_user(db_session)
    brand = make_brand(db_session, "Deanston")
    product = make_product(db_session, brand, "Deanston Virgin Oak")
    assert (brand.created_by_user_id, product.created_by_user_id) == (None, None)

    brand.created_by_user_id = product.created_by_user_id = user.id
    db_session.flush()
    product.created_by_user_id = uuid4()
    with pytest.raises(IntegrityError):
        db_session.flush()
