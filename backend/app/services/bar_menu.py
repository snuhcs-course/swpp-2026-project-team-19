from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ApiError
from app.models import Bar, BarMenuItem, BarStatus, MenuBoard, MenuBoardEntry, MenuEntryOption, Product
from app.schemas.menu import BarMenuResponse, DiscountResponse, MenuItemResponse, MenuOptionResponse


def bar_not_found(bar_id: str) -> ApiError:
    return ApiError(404, "BAR_NOT_FOUND", "업장을 찾을 수 없습니다.", details={"barId": bar_id})


def discount_response(option: MenuEntryOption, now: datetime) -> DiscountResponse | None:
    """The option's discount unless it has ended; one that has not started yet is sent too.
    Ended discounts stay in the database and are only left out here (spec 3.14.2)."""
    if option.discount_ends_at is None or option.discount_ends_at <= now:
        return None
    return DiscountResponse(
        discountedPriceKrw=option.discount_price_krw,
        startsAt=option.discount_starts_at,
        endsAt=option.discount_ends_at,
    )


def get_bar_menu(session: Session, bar_id: str, *, may_see_inactive: Callable[[Bar], bool]) -> BarMenuResponse:
    """The bar and its current menu board. An inactive bar looks missing unless may_see_inactive(bar),
    which is asked only for inactive bars so that public requests cost no permission query."""
    try:
        bar = session.get(Bar, UUID(bar_id))
    except ValueError:
        bar = None
    if bar is None or (bar.status != BarStatus.ACTIVE and not may_see_inactive(bar)):
        raise bar_not_found(bar_id)

    board = session.scalar(
        select(MenuBoard)
        .where(MenuBoard.bar_id == bar.id)
        .options(
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.options),
            selectinload(MenuBoard.entries)
            .selectinload(MenuBoardEntry.bar_menu_item)
            .selectinload(BarMenuItem.product)
            .selectinload(Product.brand),
        )
    )
    now = datetime.now(timezone.utc)
    items = [
        MenuItemResponse(
            menuBoardEntryId=entry.id,
            barMenuItemId=entry.bar_menu_item_id,
            productId=entry.bar_menu_item.product_id,
            productName=entry.bar_menu_item.product.display_name,
            brandId=entry.bar_menu_item.product.brand_id,
            brandName=entry.bar_menu_item.product.brand.canonical_name,
            category=entry.bar_menu_item.product.category,
            displayName=entry.display_name,
            sortOrder=entry.sort_order,
            options=[
                MenuOptionResponse(
                    menuEntryOptionId=option.id,
                    optionLabel=option.option_label,
                    pourMl=option.pour_ml,
                    priceKrw=option.price_krw,
                    discount=discount_response(option, now),
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
        menuVersion=board.version if board else None,
        publishedAt=board.published_at if board else None,
        items=items,
    )
