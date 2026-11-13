"""Raising and closing operator menu item checks as menus change (API spec 3.18.1).

The list and resolve APIs come later; this module keeps the checks right while menus are published and
edited: a whisky item without a product on the current board always has an open check, and an item that
leaves the board has none.
"""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import BarMenuItem, CheckReason, CheckStatus, MenuItemCheck, MenuItemCheckReason


def open_check(session: Session, item_id: UUID) -> MenuItemCheck | None:
    return session.scalar(
        select(MenuItemCheck).where(MenuItemCheck.bar_menu_item_id == item_id, MenuItemCheck.status == CheckStatus.OPEN)
    )


def raise_check(
    session: Session,
    item: BarMenuItem,
    display_name: str,
    reason: CheckReason,
    *,
    source_menu_import_id: UUID | None = None,
    source_extracted_item_id: UUID | None = None,
) -> MenuItemCheck:
    """Add `reason` to the item's open check, or open one. A reason with the same source is not added twice,
    and earlier reasons keep their sources (spec 3.18.1). The check takes the line's current name."""
    check = open_check(session, item.id)
    if check is None:
        check = MenuItemCheck(bar_id=item.bar_id, bar_menu_item_id=item.id, display_name=display_name)
        session.add(check)
    else:
        check.display_name = display_name
        if any(
            r.reason == reason and r.source_extracted_item_id == source_extracted_item_id for r in check.reasons
        ):
            return check
    check.reasons.append(
        MenuItemCheckReason(
            reason=reason,
            source_menu_import_id=source_menu_import_id,
            source_extracted_item_id=source_extracted_item_id,
        )
    )
    session.flush()
    return check


def rename_open_check(session: Session, item_id: UUID, display_name: str) -> None:
    """Keep the open check's name with the board line's, so a closed check still shows it (spec 3.18.2)."""
    check = open_check(session, item_id)
    if check is not None:
        check.display_name = display_name


def dismiss_open_checks(session: Session, item_ids: Iterable[UUID]) -> None:
    """Close the open checks of items that left the board (spec 3.18.1). Their reasons stay."""
    item_ids = set(item_ids)
    if item_ids:
        session.execute(
            update(MenuItemCheck)
            .where(MenuItemCheck.bar_menu_item_id.in_(item_ids), MenuItemCheck.status == CheckStatus.OPEN)
            .values(status=CheckStatus.DISMISSED, resolved_at=func.clock_timestamp())
        )
