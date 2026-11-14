from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models import BarMenuItem, ImportMode, MenuBoard, MenuChangeType, MenuItemKind
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
from tests.factories import make_bar, publish_menu
from tests.review_support import make_glenfiddich, upload_sample_review, valid_body

FULL, PARTIAL = ImportMode.FULL_REPLACE, ImportMode.PARTIAL_UPDATE
NOW = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
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
    # An unchanged entry is kept as it is, menu name included, now from the line that published it.
    assert result.entries[2] == replace(b, extracted_item_id=result.entries[2].extracted_item_id)
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


def test_lines_of_one_product_are_one_entry_with_every_lines_options():
    """A glass line and a bottle-corner line (spec 8.12): the first line's name and position, the options one
    after another, an equal option kept once."""
    first = Proposal(uuid4(), A, "글렌피딕 12년", (opt(15000, label="잔"), opt(9000, pour=15)))
    other = proposal(B, 5)
    second = Proposal(uuid4(), A, "Glenfiddich 12", (opt(180000, pour=None, label="병"), opt(9000, pour=15)))

    result = plan([first, other, second], [])

    assert products(result) == [A, B]
    merged = result.entries[0]
    assert (merged.display_name, merged.extracted_item_id) == ("글렌피딕 12년", first.extracted_item_id)
    assert [(o.label, o.pour_ml, o.price_krw) for o in merged.options] == [
        ("잔", 30, 15000),
        (None, 15, 9000),
        ("병", None, 180000),
    ]
    assert result.changes[0].extracted_item_ids == (first.extracted_item_id, second.extracted_item_id)
    assert result.discarded == {}


def test_an_ignored_line_is_left_out_of_the_merge():
    first, second = proposal(A, 1), Proposal(uuid4(), A, "menu", (opt(2, pour=60),))

    result = plan([first, second], [], ignored=[first.extracted_item_id])

    assert [(e.extracted_item_id, [o.price_krw for o in e.options]) for e in result.entries] == [
        (second.extracted_item_id, [2])
    ]


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
    review = validate_review(
        db_session, sample.menu_import, ReviewAndApplyRequest.model_validate(body), operator=True
    )
    catalog = create_catalog_entries(db_session, sample.menu_import, review, created_by_user_id=None)
    board, result = review_plan(db_session, sample.bar.id, sample.menu_import.mode, review, catalog)
    write_board(db_session, board, sample.bar.id, sample.menu_import.id, result.entries, published_at=NOW)
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


def test_publishing_again_keeps_the_board_and_moves_its_date(client, db_session, sample, glenfiddich):
    # The customer bar detail shows publishedAt as the menu's last update (spec 3.9).
    earlier = datetime(2026, 10, 1, tzinfo=timezone.utc)
    sample.board.published_at = earlier
    db_session.flush()

    publish(db_session, sample, valid_body(sample, glenfiddich))

    body = client.get(f"/api/bars/{sample.bar.id}/menu").json()
    assert body["menuBoardId"] == str(sample.board.id)
    assert datetime.fromisoformat(body["publishedAt"]) > earlier


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

    board, _ = write_board(db_session, None, bar.id, sample.menu_import.id, entries, published_at=NOW)

    assert (board.bar_id, board.version, board.published_at) == (bar.id, 1, NOW)
    assert board_rows(db_session, bar.id) == [("글렌피딕 12년", [(None, 30, 9000)])]


def test_a_publish_raises_the_version_and_carries_discounts_to_the_same_options(
    client, db_session, image_storage, operator, glenfiddich
):
    sample = upload_sample_review(client, db_session, operator, glenfiddich)
    bar = make_bar(db_session, "Discounts")
    started, ends = NOW, NOW + timedelta(days=14)
    publish_menu(
        db_session,
        bar,
        [
            (
                glenfiddich[12],
                "글렌피딕 12년",
                [("잔", 30, 17000, (14000, started, ends)), ("병", None, 160000, (150000, started, ends))],
            ),
            (
                glenfiddich[15],
                "글렌피딕 15년",
                [("잔", 30, 21000, (19000, started, ends)), ("하프", None, 90000, (80000, started, ends))],
            ),
        ],
        version=4,
    )
    board, current = load_board(db_session, bar.id)
    twelve, fifteen = current
    entries = [
        # The 12 keeps its glass; its bottle price changed, so that discount no longer fits.
        BoardEntry(
            glenfiddich[12].id, "글렌피딕 12Y", (opt(17000, 30, "잔"), opt(170000, None, "병")), twelve.bar_menu_item_id
        ),
        # The 15 is kept as it was, except its half bottle was dropped.
        BoardEntry(glenfiddich[15].id, "글렌피딕 15년", (fifteen.options[0],), fifteen.bar_menu_item_id),
    ]

    written, _ = write_board(db_session, board, bar.id, sample.menu_import.id, entries, published_at=NOW)

    assert (written.version, written.published_at, written.last_import_id) == (5, NOW, sample.menu_import.id)
    db_session.expire_all()
    written = db_session.get(MenuBoard, written.id)
    assert [
        [(o.option_label, o.discount_price_krw, o.discount_starts_at, o.discount_ends_at) for o in entry.options]
        for entry in written.entries
    ] == [
        [("잔", 14000, started, ends), ("병", None, None, None)],
        [("잔", 19000, started, ends)],
    ]


# ---- items without a product (spec 3.14.1, 5.4, 8.10) ----


def unlinked_on_board(key, price, kind=MenuItemKind.WHISKY):
    return BoardEntry(None, key, (opt(price),), uuid4(), kind=kind, name_key=key)


def unlinked_proposal(key, price, kind=MenuItemKind.WHISKY):
    return Proposal(uuid4(), None, key, (opt(price),), kind=kind, name_key=key)


def test_an_unlinked_line_is_the_unlinked_entry_of_its_name_key():
    highball = unlinked_on_board("하이볼", 9000, MenuItemKind.OTHER)

    result = plan([unlinked_proposal("하이볼", 9000, MenuItemKind.OTHER), unlinked_proposal("진토닉", 8000)], [highball])

    assert [(e.name_key, e.bar_menu_item_id) for e in result.entries] == [("하이볼", highball.bar_menu_item_id), ("진토닉", None)]
    assert change_types(result) == [MenuChangeType.ADD]


def test_a_changed_kind_is_an_update():
    highball = unlinked_on_board("하이볼", 9000)

    result = plan([unlinked_proposal("하이볼", 9000, MenuItemKind.OTHER)], [highball])

    assert change_types(result) == [MenuChangeType.UPDATE]
    assert result.entries[0].kind == MenuItemKind.OTHER


def test_a_line_takes_over_only_an_unlinked_entry():
    """A takeover comes from an applied update; one whose entry has a product (the reviewer picked another
    product for that line) adds the line instead."""
    unlinked, linked = unlinked_on_board("unknown", 45000), on_board(B, 1000)
    first, second = proposal(A, 45000), proposal(C, 1000)
    takeovers = {first.extracted_item_id: unlinked.bar_menu_item_id, second.extracted_item_id: linked.bar_menu_item_id}

    result = plan_publish(
        [first, second, unlinked_proposal("unknown", 45000)],
        [unlinked, linked],
        mode=PARTIAL,
        ignored_items=set(),
        approved_removals=set(),
        takeovers=takeovers,
    )

    assert result.linked_items == {unlinked.bar_menu_item_id}
    assert [(e.product_id, e.bar_menu_item_id) for e in result.entries] == [
        (A, unlinked.bar_menu_item_id),
        (B, linked.bar_menu_item_id),
        (C, None),
        # The unlinked entry is now the product's; a later line of its name is a new item.
        (None, None),
    ]


def test_a_bar_without_a_board_has_no_entries(db_session):
    assert load_board(db_session, make_bar(db_session, "No board").id) == (None, [])


def test_a_product_the_bar_sold_before_gets_its_item_back(client, db_session, image_storage, operator, glenfiddich):
    sample = upload_sample_review(client, db_session, operator, glenfiddich)
    bar = make_bar(db_session, "Sold before")
    old = BarMenuItem(bar_id=bar.id, product_id=glenfiddich[15].id)
    db_session.add(old)
    db_session.flush()

    _, items = write_board(
        db_session, None, bar.id, sample.menu_import.id, [BoardEntry(glenfiddich[15].id, "15", (opt(1),))], published_at=NOW
    )

    assert [item.id for item in items] == [old.id]


def test_a_corrected_name_replaces_the_boards_name_even_with_the_same_options():
    """A name the AI read differently keeps the board's; a name the reviewer sent replaces it (spec 8.7)."""
    a = on_board(A, 10000)
    read = Proposal(uuid4(), A, "menu read differently", (opt(10000),))
    corrected = replace(read, name_corrected=True)
    same_name = replace(corrected, display_name=a.display_name)

    assert (plan([read], [a]).changes, plan([read], [a]).entries[0].display_name) == ([], a.display_name)
    assert change_types(plan([corrected], [a])) == [MenuChangeType.UPDATE]
    assert plan([corrected], [a]).entries[0].display_name == "menu read differently"
    assert plan([same_name], [a]).changes == []


def test_unlinked_whisky_lines_of_one_name_key_keep_the_earlier_price():
    """The server's name key can join lines the reviewer saw apart (spec 8.12): no refusal, the earlier
    price stays and the other is kept for the operator."""
    first = unlinked_proposal("glenallachie10cs", 26000)
    second = replace(unlinked_proposal("glenallachie10cs", 28000, kind=MenuItemKind.OTHER), display_name="글렌알라키10CS")

    result = plan([first, second], [])

    [entry] = result.entries
    assert ([o.price_krw for o in entry.options], entry.kind) == ([26000], MenuItemKind.WHISKY)
    assert result.discarded == {
        first.extracted_item_id: [
            {
                "optionLabel": None,
                "pourMl": 30,
                "priceKrw": 28000,
                "displayName": "글렌알라키10CS",
                "extractedItemId": str(second.extracted_item_id),
            }
        ]
    }


def test_other_lines_of_one_name_key_are_other():
    result = plan([unlinked_proposal("하이볼", 1, MenuItemKind.OTHER), unlinked_proposal("하이볼", 1, MenuItemKind.OTHER)], [])

    assert [(e.kind, len(e.options)) for e in result.entries] == [(MenuItemKind.OTHER, 1)]
