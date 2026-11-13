from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ApiError
from app.models import Bar, BarLocalMenuItem, BarMenuItem, BarStatus, MenuBoard, MenuBoardEntry, MenuEntryOption, Product
from app.schemas.menu import BarMenuResponse, DiscountResponse, MenuItemResponse, MenuOptionResponse
from app.services.bar_hours import operating_exceptions_by_bar, seoul_today, weekly_hours_by_bar
from app.services.bar_photo_links import photos_by_bar


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


def get_bar_menu(
    session: Session, bar_id: str, *, can_manage: Callable[[Bar], bool], base_url: str
) -> BarMenuResponse:
    """The bar and its current menu board, as the caller may see it (spec 3.9). Unless can_manage(bar),
    an inactive bar looks missing and sold-out items are left out; a manager gets them in place with
    `soldOut = true`. can_manage is asked at most once and only when the answer matters, so a public
    request for an active bar without sold-out items costs no permission query."""
    try:
        bar = session.get(Bar, UUID(bar_id))
    except ValueError:
        bar = None
    manages: list[bool] = []

    def is_manager() -> bool:
        if not manages:
            manages.append(can_manage(bar))
        return manages[0]

    if bar is None or (bar.status != BarStatus.ACTIVE and not is_manager()):
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
    entries = board.entries if board else []
    # Customers are not shown what the bar does not sell right now (spec 3.14.8).
    if any(e.bar_menu_item.sold_out_at is not None for e in entries) and not is_manager():
        entries = [e for e in entries if e.bar_menu_item.sold_out_at is None]
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
            soldOut=entry.bar_menu_item.sold_out_at is not None,
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
        for entry in entries
    ]
    # Local items are never joined to Product and cannot enter customer whisky
    # search. They are nonetheless public on this bar's own posted menu.
    local_rows = session.scalars(
        select(BarLocalMenuItem).where(BarLocalMenuItem.bar_id == bar.id)
        .order_by(BarLocalMenuItem.created_at, BarLocalMenuItem.id)
    ).all()
    for local in local_rows:
        if local.sold_out_at is not None and not is_manager():
            continue
        prices = []
        for index, opt in enumerate(local.options, start=1):
            discount = opt.get("discount")
            if discount is not None:
                try:
                    expiry = datetime.fromisoformat(discount["endsAt"].replace("Z", "+00:00"))
                    if expiry <= now:
                        discount = None
                except (ValueError, KeyError, TypeError):
                    discount = None
            prices.append(MenuOptionResponse(
                menuEntryOptionId=UUID(opt["menuEntryOptionId"]),
                optionLabel=opt.get("optionLabel"),
                pourMl=opt.get("pourMl"),
                priceKrw=opt["priceKrw"],
                discount=DiscountResponse.model_validate(discount) if discount else None,
                sortOrder=index,
            ))
        items.append(MenuItemResponse(
            menuBoardEntryId=local.id, barMenuItemId=local.id,
            # The id is an opaque local identity, never a catalog Product row.
            productId=local.id, productName=local.display_name,
            brandId=None, brandName=None, category=local.category,
            displayName=local.display_name, sortOrder=len(items) + 1,
            soldOut=local.sold_out_at is not None, options=prices,
            catalogMatched=False,
            catalogReviewStatus="pending" if local.category == "whisky" else None,
        ))
    return BarMenuResponse(
        barId=bar.id,
        name=bar.name,
        address=bar.address,
        latitude=float(bar.latitude),
        longitude=float(bar.longitude),
        phone=bar.phone,
        description=bar.description,
        tags=list(bar.tags),
        weeklyHours=weekly_hours_by_bar(session, [bar.id])[bar.id],
        operatingException=operating_exceptions_by_bar(session, [bar.id], seoul_today()).get(bar.id),
        photos=photos_by_bar(session, [bar.id], base_url)[bar.id],
        menuBoardId=board.id if board else None,
        menuVersion=board.version if board else None,
        publishedAt=board.published_at if board else None,
        items=items,
    )
