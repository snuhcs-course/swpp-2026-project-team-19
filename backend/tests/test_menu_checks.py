"""Raising and settling operator menu item checks (API spec 3.18.1, app/services/menu_checks.py)."""

from uuid import uuid4

from app.models import BarMenuItem, CheckReason, CheckStatus, MenuItemCheck, MenuItemCheckReason
from app.services.menu_checks import move_open_check, raise_check, settle_linked
from tests.factories import make_bar


def unlinked_item(session, bar, key="unknowndistillery25") -> BarMenuItem:
    item = BarMenuItem(bar_id=bar.id, name_key=key)
    session.add(item)
    session.flush()
    return item


def check_with(session, item, *reasons) -> MenuItemCheck:
    check = MenuItemCheck(
        bar_id=item.bar_id,
        bar_menu_item_id=item.id,
        display_name="Unknown Distillery 25",
        reasons=[MenuItemCheckReason(reason=r) for r in reasons],
        discarded_options=[{"priceKrw": 1}],
    )
    session.add(check)
    session.flush()
    return check


def test_a_reason_from_the_same_source_is_added_once(db_session):
    item = unlinked_item(db_session, make_bar(db_session))

    raise_check(db_session, item, "A", CheckReason.UNLINKED)
    check = raise_check(db_session, item, "B", CheckReason.UNLINKED)

    assert ([r.reason for r in check.reasons], check.display_name) == ([CheckReason.UNLINKED], "B")


def test_linking_keeps_the_other_reasons_open_on_the_same_item(db_session):
    item = unlinked_item(db_session, make_bar(db_session))
    check = check_with(db_session, item, CheckReason.UNLINKED, CheckReason.PRICE_CONFLICT)

    settle_linked(db_session, item.id, item, "Unknown Distillery 25년")
    db_session.flush()

    assert (check.status, [r.reason for r in check.reasons], check.display_name) == (
        CheckStatus.OPEN,
        [CheckReason.PRICE_CONFLICT],
        "Unknown Distillery 25년",
    )


def test_linking_moves_the_check_with_the_line(db_session):
    bar = make_bar(db_session)
    item, other = unlinked_item(db_session, bar), unlinked_item(db_session, bar, "다른")
    check = check_with(db_session, item, CheckReason.UNLINKED, CheckReason.ATTRIBUTE_CONFLICT)

    settle_linked(db_session, item.id, other, "Unknown Distillery 25")
    db_session.flush()

    assert (check.bar_menu_item_id, check.status) == (other.id, CheckStatus.OPEN)


def test_linking_merges_into_the_open_check_of_the_item_the_line_moved_to(db_session):
    bar = make_bar(db_session)
    item, other = unlinked_item(db_session, bar), unlinked_item(db_session, bar, "다른")
    moving = check_with(db_session, item, CheckReason.UNLINKED, CheckReason.PRICE_CONFLICT)
    staying = check_with(db_session, other, CheckReason.ATTRIBUTE_CONFLICT)
    staying.reasons[0].source_extracted_item_id = None

    settle_linked(db_session, item.id, other, "Unknown Distillery 25")
    db_session.flush()

    assert (moving.status, [r.reason for r in moving.reasons]) == (CheckStatus.DISMISSED, [CheckReason.PRICE_CONFLICT])
    assert staying.status == CheckStatus.OPEN
    assert sorted(r.reason.value for r in staying.reasons) == ["attribute_conflict", "price_conflict"]
    assert staying.discarded_options == [{"priceKrw": 1}, {"priceKrw": 1}]


def test_settling_an_item_without_an_open_check_does_nothing(db_session):
    item = unlinked_item(db_session, make_bar(db_session))

    settle_linked(db_session, item.id, item, "x")
    settle_linked(db_session, uuid4(), item, "x")


def test_moving_a_check_keeps_every_reason_and_adds_a_known_one_once(db_session):
    """A rematched line takes another item's place (spec 8.11): the item's open check goes with it."""
    bar = make_bar(db_session)
    item, other = unlinked_item(db_session, bar), unlinked_item(db_session, bar, "다른")
    moving = check_with(db_session, item, CheckReason.UNLINKED, CheckReason.ATTRIBUTE_CONFLICT)
    staying = check_with(db_session, other, CheckReason.ATTRIBUTE_CONFLICT)

    move_open_check(db_session, item.id, other, "다른")
    db_session.flush()

    assert moving.status == CheckStatus.DISMISSED
    assert sorted(r.reason.value for r in staying.reasons) == ["attribute_conflict", "unlinked"]


def test_moving_a_check_to_an_item_without_one_moves_it(db_session):
    bar = make_bar(db_session)
    item, other = unlinked_item(db_session, bar), unlinked_item(db_session, bar, "다른")
    check = check_with(db_session, item, CheckReason.UNLINKED)

    move_open_check(db_session, item.id, other, "다른")
    move_open_check(db_session, other.id, other, "다른")  # to the same item: nothing to do

    assert (check.bar_menu_item_id, check.status, check.display_name) == (other.id, CheckStatus.OPEN, "다른")
