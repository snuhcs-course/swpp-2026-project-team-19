"""The sold-out mark (API spec 3.14.8) and the sales info confirmation (3.14.9).

Neither changes the menu's content, so unlike the manual edits (app.services.menu_edit) they are
accepted while an import is unfinished, take no menuVersion bump, and leave `publishedAt` alone.
They still take the bar row lock first and check the bar and the caller again under it, so they run
one after another with edits, review publishes and uploads of the same bar (3.14.1).

They touch only the bar's own rows, so the bar row lock orders them fully: each runs in the
request's ordinary (READ COMMITTED) transaction, whose statements after the lock see what earlier
requests committed. No retry is needed.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import Principal
from app.models import Bar, BarLocalMenuItem, MenuBoard
from app.schemas.bar import BarDetail
from app.schemas.menu import BarMenuResponse
from app.services.bar_detail import get_bar_detail
from app.services.bar_menu import get_bar_menu
from app.services.menu_edit import board_entry, check_menu_version, current_board, lock_managed_bar
from app.services.users import caller_user_id


def _locked_now(session: Session):
    """The time after the bar lock was taken, not the transaction start (spec 3.14.1)."""
    return session.scalar(select(func.clock_timestamp()))


def set_sold_out(
    session: Session, principal: Principal, bar_id: UUID, bar_menu_item_id: str, sold_out: bool, *, base_url: str
) -> BarMenuResponse:
    """Mark an item on the board sold out or back on sale; the menu as its managers see it (spec 3.9).
    Setting the value it already has changes nothing, and an item stays sold out from the first mark."""
    lock_managed_bar(session, principal, bar_id)
    # Local menu items have their own stock state; they are not catalog products.
    try:
        parsed_id = UUID(bar_menu_item_id)
    except ValueError:
        parsed_id = None
    local = session.get(BarLocalMenuItem, parsed_id) if parsed_id is not None else None
    if local is not None and local.bar_id == bar_id:
        if not sold_out:
            local.sold_out_at = None
        elif local.sold_out_at is None:
            local.sold_out_at = _locked_now(session)
        session.commit()
        return get_bar_menu(session, str(bar_id), can_manage=lambda bar: True, base_url=base_url)
    # Checked under the lock, so an item a review or a delete has just taken off the board is not found.
    item = board_entry(current_board(session, bar_id), bar_menu_item_id).bar_menu_item
    if not sold_out:
        item.sold_out_at = None
    elif item.sold_out_at is None:
        item.sold_out_at = _locked_now(session)
    session.commit()
    return get_bar_menu(session, str(bar_id), can_manage=lambda bar: True, base_url=base_url)


def _no_published_menu() -> ApiError:
    return ApiError(409, "NO_PUBLISHED_MENU", "확인할 메뉴가 없습니다. 먼저 메뉴를 등록해 주세요.")


def confirm_menu(
    session: Session, principal: Principal, bar_id: UUID, menu_version: int | None, *, base_url: str
) -> BarDetail:
    """Record that the caller confirmed the menu they saw is still accurate; the bar as in spec 3.6."""
    lock_managed_bar(session, principal, bar_id)
    board = session.scalar(select(MenuBoard).where(MenuBoard.bar_id == bar_id))
    # Before the version, so a bar without a menu that sends null is told there is nothing to confirm.
    # Sold-out items count: they are still on the menu.
    if board is None or not board.entries:
        raise _no_published_menu()
    check_menu_version(board, menu_version)
    board.confirmed_at = _locked_now(session)
    board.confirmed_by_user_id = caller_user_id(session, principal)
    session.commit()
    return get_bar_detail(session, session.get(Bar, bar_id), base_url=base_url)
