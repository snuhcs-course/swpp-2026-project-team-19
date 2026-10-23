from uuid import UUID

from app.models import ImportMode, MenuChangeType
from app.services.menu_diff import CurrentEntry, DraftChange, ProposedEntry, compute_draft_changes

ITEM = [UUID(int=100 + n) for n in range(6)]
PRODUCT = [UUID(int=200 + n) for n in range(4)]
BAR_ITEM = [UUID(int=300 + n) for n in range(4)]
GLASS_BOTTLE = (("잔", None, 11000), ("병", None, 150000))


def proposed(item, product, options=GLASS_BOTTLE):
    return ProposedEntry(extracted_item_id=item, product_id=product, options=options)


def current(bar_item, product, options=GLASS_BOTTLE):
    return CurrentEntry(bar_menu_item_id=bar_item, product_id=product, options=options)


def test_products_not_on_the_board_are_added():
    changes = compute_draft_changes([proposed(ITEM[0], PRODUCT[0])], [], ImportMode.FULL_REPLACE)

    assert changes == [DraftChange(MenuChangeType.ADD, extracted_item_id=ITEM[0])]


def test_unchanged_products_produce_no_change():
    changes = compute_draft_changes(
        [proposed(ITEM[0], PRODUCT[0])], [current(BAR_ITEM[0], PRODUCT[0])], ImportMode.FULL_REPLACE
    )

    assert changes == []


def test_different_price_pour_label_or_option_order_is_an_update():
    board = [current(BAR_ITEM[0], PRODUCT[0])]
    for options in [
        (("잔", None, 12000), ("병", None, 150000)),
        (("잔", 30, 11000), ("병", None, 150000)),
        ((None, None, 11000), ("병", None, 150000)),
        (("병", None, 150000), ("잔", None, 11000)),
        (("잔", None, 11000),),
    ]:
        changes = compute_draft_changes([proposed(ITEM[0], PRODUCT[0], options)], board, ImportMode.PARTIAL_UPDATE)

        assert changes == [DraftChange(MenuChangeType.UPDATE, bar_menu_item_id=BAR_ITEM[0], extracted_item_id=ITEM[0])]


def test_full_replace_removes_board_products_missing_from_the_import():
    board = [current(BAR_ITEM[0], PRODUCT[0]), current(BAR_ITEM[1], PRODUCT[1])]

    changes = compute_draft_changes([proposed(ITEM[0], PRODUCT[0])], board, ImportMode.FULL_REPLACE)

    assert changes == [DraftChange(MenuChangeType.REMOVE, bar_menu_item_id=BAR_ITEM[1])]


def test_partial_update_never_removes():
    board = [current(BAR_ITEM[0], PRODUCT[0]), current(BAR_ITEM[1], PRODUCT[1])]

    assert compute_draft_changes([], board, ImportMode.PARTIAL_UPDATE) == []


def test_first_occurrence_of_a_product_wins():
    board = [current(BAR_ITEM[0], PRODUCT[0])]
    later_price = (("잔", None, 99000),)

    changes = compute_draft_changes(
        [proposed(ITEM[0], PRODUCT[0]), proposed(ITEM[1], PRODUCT[0], later_price)], board, ImportMode.FULL_REPLACE
    )

    assert changes == []


def test_every_unmatched_item_is_an_add():
    changes = compute_draft_changes(
        [proposed(ITEM[0], None), proposed(ITEM[1], None)], [current(BAR_ITEM[0], PRODUCT[0])], ImportMode.PARTIAL_UPDATE
    )

    assert changes == [
        DraftChange(MenuChangeType.ADD, extracted_item_id=ITEM[0]),
        DraftChange(MenuChangeType.ADD, extracted_item_id=ITEM[1]),
    ]


def test_mixed_changes_keep_menu_order_then_removals():
    board = [current(BAR_ITEM[0], PRODUCT[0]), current(BAR_ITEM[1], PRODUCT[1]), current(BAR_ITEM[2], PRODUCT[2])]
    items = [
        proposed(ITEM[0], PRODUCT[3]),
        proposed(ITEM[1], PRODUCT[0], (("잔", None, 1),)),
        proposed(ITEM[2], None),
        proposed(ITEM[3], PRODUCT[1]),
    ]

    changes = compute_draft_changes(items, board, ImportMode.FULL_REPLACE)

    assert [(c.change_type, c.extracted_item_id, c.bar_menu_item_id) for c in changes] == [
        (MenuChangeType.ADD, ITEM[0], None),
        (MenuChangeType.UPDATE, ITEM[1], BAR_ITEM[0]),
        (MenuChangeType.ADD, ITEM[2], None),
        (MenuChangeType.REMOVE, None, BAR_ITEM[2]),
    ]
