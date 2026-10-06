from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models import BarMenuItem, ImportMode, MenuBoard, MenuChangeType
from app.schemas.menu_review import ReviewAndApplyRequest
from app.services.menu_publish import (
    BoardEntry,
    Proposal,
    PublishedOption,
    load_board,
    plan_publish,
    review_plan,
    write_board,
)
from app.services.menu_review_catalog import create_catalog_entries
from app.services.menu_review_validation import validate_review
from tests.factories import make_bar
from tests.review_support import make_glenfiddich, upload_sample_review, valid_body

FULL, PARTIAL = ImportMode.FULL_REPLACE, ImportMode.PARTIAL_UPDATE
A, B, C, D = (UUID(int=n) for n in range(1, 5))  # products


def opt(price, pour=30, label=None, source=None):
    return PublishedOption(label, pour, price, source)


def on_board(product, price, item=None):
    return BoardEntry(product, f"board {product.int}", (opt(price),), item or uuid4())


def proposal(product, price, item=None):
    return Proposal(item or uuid4(), product, f"menu {product.int}", (opt(price),))


def plan(proposals, current, mode=FULL, ignored=(), removals=()):
    return plan_publish(proposals, current, mode=mode, ignored_items=set(ignored), approved_removals=set(removals))


def products(result):
    return [e.product_id for e in result.entries]


def change_types(result):
    return [c.change_type for c in result.changes]


def test_add_update_and_unchanged():
    a, b = on_board(A, 10000), on_board(B, 20000)

    result = plan([proposal(C, 5000), proposal(A, 11000), proposal(B, 20000)], [a, b])

    assert products(result) == [C, A, B]
    assert change_types(result) == [MenuChangeType.ADD, MenuChangeType.UPDATE]
    # An unchanged entry is kept as it is, menu name included.
    assert result.entries[2] == b
    # An updated entry keeps its bar menu item.
    assert result.entries[1].bar_menu_item_id == a.bar_menu_item_id
    assert result.entries[1].display_name == "menu 1"


def test_only_approved_removals_leave_the_board():
    a, b, c = on_board(A, 1), on_board(B, 2), on_board(C, 3)

    result = plan([proposal(D, 4)], [a, b, c], removals={b.bar_menu_item_id})

    assert products(result) == [D, A, C]  # photo order first, kept entries after in board order
    assert result.changes[-1].change_type == MenuChangeType.REMOVE
    assert result.changes[-1].bar_menu_item_id == b.bar_menu_item_id


def test_a_removal_is_dropped_when_the_product_is_published_again():
    a = on_board(A, 1)

    result = plan([proposal(A, 1)], [a], removals={a.bar_menu_item_id})

    assert (products(result), result.changes) == ([A], [])


def test_picking_another_product_keeps_the_proposed_one():
    """Draft: update A from this line. The reviewer picked B instead and approved nothing else."""
    a = on_board(A, 1)

    result = plan([proposal(B, 1)], [a])

    assert products(result) == [B, A]
    assert change_types(result) == [MenuChangeType.ADD]


def test_ignored_items_are_not_published():
    a = on_board(A, 1)
    ignored = proposal(A, 2)

    result = plan([ignored, proposal(B, 3)], [a], ignored={ignored.extracted_item_id})

    assert products(result) == [B, A]
    assert result.entries[1] == a
    assert change_types(result) == [MenuChangeType.ADD]


def test_first_line_of_a_product_wins():
    first, second = proposal(A, 1), proposal(A, 2)

    result = plan([first, second], [])

    assert [e.options[0].price_krw for e in result.entries] == [1]
    assert result.changes[0].extracted_item_id == first.extracted_item_id


def test_partial_update_keeps_board_order_and_appends_adds():
    a, b, c = on_board(A, 1), on_board(B, 2), on_board(C, 3)

    result = plan([proposal(D, 4), proposal(B, 20)], [a, b, c], mode=PARTIAL)

    assert products(result) == [A, B, C, D]
    assert result.entries[1].options[0].price_krw == 20
    assert change_types(result) == [MenuChangeType.ADD, MenuChangeType.UPDATE]


def test_option_order_counts_as_a_change():
    current = BoardEntry(A, "a", (opt(1, pour=15), opt(2, pour=30)), uuid4())
    reordered = Proposal(uuid4(), A, "a", (opt(2, pour=30), opt(1, pour=15)))

    assert change_types(plan([reordered], [current])) == [MenuChangeType.UPDATE]


# ---- with the database ----


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


@pytest.fixture
def sample(client, db_session, image_storage, operator, glenfiddich):
    return upload_sample_review(client, db_session, operator, glenfiddich)


def publish(db_session, sample, body):
    review = validate_review(db_session, sample.menu_import, ReviewAndApplyRequest.model_validate(body))
    catalog = create_catalog_entries(db_session, sample.menu_import, review)
    board, result = review_plan(db_session, sample.bar.id, sample.menu_import.mode, review, catalog)
    write_board(db_session, board, sample.bar.id, sample.menu_import.id, result.entries)
    db_session.expire_all()
    return result, catalog


def board_rows(db_session, bar_id):
    _, entries = load_board(db_session, bar_id)
    return [(e.display_name, [(o.label, o.pour_ml, o.price_krw) for o in e.options]) for e in entries]


def test_publishing_the_sample_review(db_session, sample, glenfiddich):
    """Glenfiddich 12 gets the menu's new price, Unknown Distillery 25 is created and added,
    and Glenfiddich 15 is removed as approved."""
    result, catalog = publish(db_session, sample, valid_body(sample, glenfiddich))

    assert change_types(result) == [MenuChangeType.UPDATE, MenuChangeType.ADD, MenuChangeType.REMOVE]
    assert board_rows(db_session, sample.bar.id) == [
        ("글렌피딕 12년", [(None, 15, 9000), (None, 30, 17000)]),
        ("Unknown Distillery 25", [("잔", None, 45000)]),
    ]
    board = db_session.scalar(select(MenuBoard).where(MenuBoard.bar_id == sample.bar.id))
    assert board.id == sample.board.id
    assert board.last_import_id == sample.menu_import.id
    exact = sample.items[1]
    assert [o.source_extracted_option_id for o in board.entries[0].options] == [o.id for o in exact.options]
    # The bar now has a menu item for the new product; the one for Glenfiddich 15 is kept.
    items = set(db_session.scalars(select(BarMenuItem.product_id).where(BarMenuItem.bar_id == sample.bar.id)))
    assert items == {glenfiddich[12].id, glenfiddich[15].id, catalog.product_ids[sample.items[3].id]}


def test_ignored_removal_and_corrected_name(db_session, sample, glenfiddich):
    body = valid_body(sample, glenfiddich)
    remove = sample.changes[MenuChangeType.REMOVE]
    for decision in body["changeDecisions"]:
        if decision["changeId"] == str(remove.id):
            decision["decision"] = "ignore"
    body["itemDecisions"][1]["correctedProductName"] = "글렌피딕 12Y"

    publish(db_session, sample, body)

    assert [name for name, _ in board_rows(db_session, sample.bar.id)] == [
        "글렌피딕 12Y",
        "Unknown Distillery 25",
        "글렌피딕 15년",
    ]


def test_first_publish_creates_the_board(client, db_session, image_storage, operator, glenfiddich):
    sample = upload_sample_review(client, db_session, operator, glenfiddich)
    bar = make_bar(db_session, "Empty")
    entries = [BoardEntry(glenfiddich[12].id, "글렌피딕 12년", (opt(9000),))]

    board = write_board(db_session, None, bar.id, sample.menu_import.id, entries)

    assert board.bar_id == bar.id
    assert board_rows(db_session, bar.id) == [("글렌피딕 12년", [(None, 30, 9000)])]
