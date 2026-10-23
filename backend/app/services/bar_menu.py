from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ApiError
from app.models import Bar, BarStatus, MenuBoard, MenuBoardEntry
from app.schemas.menu import BarMenuResponse, MenuItemResponse, MenuOptionResponse


def bar_not_found(bar_id: str) -> ApiError:
    return ApiError(404, "BAR_NOT_FOUND", "업장을 찾을 수 없습니다.", details={"barId": bar_id})


def get_bar_menu(session: Session, bar_id: str, *, include_inactive: bool) -> BarMenuResponse:
    """The bar and its current menu board. Inactive bars look missing unless include_inactive."""
    try:
        bar = session.get(Bar, UUID(bar_id))
    except ValueError:
        bar = None
    if bar is None or (bar.status != BarStatus.ACTIVE and not include_inactive):
        raise bar_not_found(bar_id)

    board = session.scalar(
        select(MenuBoard)
        .where(MenuBoard.bar_id == bar.id)
        .options(
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.options),
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.bar_menu_item),
        )
    )
    items = [
        MenuItemResponse(
            menuBoardEntryId=entry.id,
            barMenuItemId=entry.bar_menu_item_id,
            productId=entry.bar_menu_item.product_id,
            displayName=entry.display_name,
            sortOrder=entry.sort_order,
            options=[
                MenuOptionResponse(
                    menuEntryOptionId=option.id,
                    optionLabel=option.option_label,
                    pourMl=option.pour_ml,
                    priceKrw=option.price_krw,
                    sortOrder=option.sort_order,
                )
                for option in entry.options
            ],
        )
        for entry in (board.entries if board else [])
    ]
    return BarMenuResponse(
        barId=bar.id,
        name=bar.name,
        address=bar.address,
        latitude=float(bar.latitude),
        longitude=float(bar.longitude),
        phone=bar.phone,
        menuBoardId=board.id if board else None,
        publishedAt=board.published_at if board else None,
        items=items,
    )
