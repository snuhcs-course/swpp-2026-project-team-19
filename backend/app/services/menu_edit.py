"""Manual menu edits (API spec 3.14.1 to 3.14.7): add, edit and delete one item, or empty the board.
The result is published right away, without a review.

Order of checks, the first failure answering:

1. the request on its own (check_request; the route runs it before looking the bar up)
2. the bar and the caller (the route, before the transaction)
3. in one SERIALIZABLE transaction: lock the bar row; the bar is active and the caller may
   manage it (again, now that it is locked); no unfinished import; the submitted menuVersion is
   the current one; then each API's own checks and the change

Only the requested item changes: other entries keep their ids, order, options and discounts.
A successful edit raises the board version and stamps `published_at` with the time taken after
the lock. Nothing is retried on the caller's behalf except a write conflict (app.services.serializable).
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ApiError, validation_failed_fields
from app.core.normalize import normalize
from app.core.security import Principal
from app.models import Bar, BarMenuItem, BarLocalMenuItem, BarStatus, Brand, MenuBoard, MenuBoardEntry, MenuEntryOption, Product
from app.schemas.menu import BarMenuResponse
from app.schemas.menu_edit import (
    LocalMenuApprovalRequest, MenuItemAddRequest, MenuItemUpdateRequest,
    MenuOptionInput, MenuResetRequest,
)
from app.services.bar_access import can_manage_bar, forbidden, is_operator
from app.services.bar_menu import bar_not_found, get_bar_menu
from app.services.menu_import_upload import check_no_unfinished_import
from app.services.menu_publish import clear_sold_out
from app.services.menu_review_catalog import create_new_product
from app.services.serializable import SessionFactory, run_serializable, write_conflict
from app.services.users import caller_user_id


class _Errors:
    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def add(self, path: str, code: str, message: str) -> None:
        self.items.append({"path": path, "code": code, "message": message})

    def raise_any(self) -> None:
        if self.items:
            raise validation_failed_fields(self.items)


# ---- 1. the request on its own ----


def _check_options(errors: _Errors, options: list[MenuOptionInput], now: datetime) -> None:
    keys = [(o.optionLabel, o.pourMl) for o in options]
    if len(keys) != len(set(keys)):
        errors.add("options", "DUPLICATE_OPTION_VALUES", "옵션명과 용량이 같은 옵션이 있습니다.")
    for index, option in enumerate(options):
        discount, path = option.discount, f"options[{index}].discount"
        if discount is None:
            continue
        if discount.discountedPriceKrw >= option.priceKrw:
            errors.add(f"{path}.discountedPriceKrw", "DISCOUNT_NOT_LOWER", "할인가는 정가보다 낮아야 합니다.")
        if discount.endsAt <= discount.startsAt:
            errors.add(f"{path}.endsAt", "END_BEFORE_START", "할인 종료 시각은 시작 시각보다 늦어야 합니다.")
        if discount.endsAt <= now:
            errors.add(f"{path}.endsAt", "DISCOUNT_ENDED", "이미 끝난 할인입니다.")


def _check_normalizable(errors: _Errors, path: str, text: str) -> None:
    if not normalize(text):
        errors.add(path, "NOT_NORMALIZABLE", "이름으로 쓸 수 있는 글자가 없습니다.")


def check_request(body: MenuItemAddRequest | MenuItemUpdateRequest, now: datetime) -> None:
    """The rules a request breaks on its own, all reported together as one 422. `now` is the request time."""
    errors = _Errors()
    if isinstance(body, MenuItemAddRequest):
        if sum(value is not None for value in (body.productId, body.newProduct, body.localItem)) != 1:
            errors.add("productId", "EXACTLY_ONE_REQUIRED",
                "productId, newProduct, localItem 중 하나만 보내야 합니다.")
        if body.localItem is not None:
            if body.displayName is None:
                errors.add("displayName", "MISSING", "매장 전용 메뉴 이름이 필요합니다.")
            else:
                _check_normalizable(errors, "displayName", body.displayName)
        new = body.newProduct
        if new is not None:
            if new.brand.type == "new":
                _check_normalizable(errors, "newProduct.brand.canonicalName", new.brand.canonicalName)
                for index, alias in enumerate(new.brand.aliases):
                    _check_normalizable(errors, f"newProduct.brand.aliases[{index}].aliasText", alias.aliasText)
            _check_normalizable(errors, "newProduct.product.displayName", new.product.displayName)
            for index, alias in enumerate(new.aliases):
                _check_normalizable(errors, f"newProduct.aliases[{index}].aliasText", alias.aliasText)
    _check_options(errors, body.options, now)
    errors.raise_any()


# ---- 3. inside the transaction ----


def menu_outdated(submitted: int | None, current: int | None) -> ApiError:
    return ApiError(
        409,
        "MENU_OUTDATED",
        "메뉴가 다른 곳에서 바뀌었습니다. 최신 메뉴를 다시 불러온 뒤 저장해 주세요.",
        details={"submittedMenuVersion": submitted, "currentMenuVersion": current},
    )


def _item_not_found(bar_menu_item_id: str) -> ApiError:
    return ApiError(
        404, "MENU_ITEM_NOT_FOUND", "메뉴 항목을 찾을 수 없습니다.", details={"barMenuItemId": bar_menu_item_id}
    )


def lock_managed_bar(session: Session, principal: Principal, bar_id: UUID) -> None:
    """Lock the bar row, then check what the route checked before the lock (spec 3.14.1): the bar is
    active (else 404 BAR_NOT_FOUND) and the caller may manage it (else 403). Used by every request
    that changes or confirms a bar's menu."""
    status = session.scalar(select(Bar.status).where(Bar.id == bar_id).with_for_update())
    if status != BarStatus.ACTIVE:
        raise bar_not_found(str(bar_id))
    if not can_manage_bar(session, principal, bar_id):
        raise forbidden()


def current_board(session: Session, bar_id: UUID) -> MenuBoard | None:
    """The bar's board with its entries, their options and bar menu items; None without one."""
    return session.scalar(
        select(MenuBoard)
        .where(MenuBoard.bar_id == bar_id)
        .options(
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.options),
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.bar_menu_item),
        )
    )


def check_menu_version(board: MenuBoard | None, menu_version: int | None) -> None:
    current = board.version if board is not None else None
    if menu_version != current:
        raise menu_outdated(menu_version, current)


def _open_board(session: Session, principal: Principal, bar_id: UUID, menu_version: int | None) -> MenuBoard | None:
    """Lock the bar row and run the checks every edit shares; the bar's board, or None without one."""
    lock_managed_bar(session, principal, bar_id)
    check_no_unfinished_import(session, bar_id)
    board = current_board(session, bar_id)
    check_menu_version(board, menu_version)
    return board


def board_entry(board: MenuBoard | None, bar_menu_item_id: str) -> MenuBoardEntry:
    """The board's entry of a bar menu item; 404 MENU_ITEM_NOT_FOUND when it is not on the board."""
    try:
        item_id = UUID(bar_menu_item_id)
    except ValueError:
        raise _item_not_found(bar_menu_item_id) from None
    entry = next((e for e in (board.entries if board else []) if e.bar_menu_item_id == item_id), None)
    if entry is None:
        raise _item_not_found(bar_menu_item_id)
    return entry


def _options(options: list[MenuOptionInput]) -> list[MenuEntryOption]:
    """Option rows as sent. They are entered by hand, so none has a source extracted option."""
    return [
        MenuEntryOption(
            option_label=o.optionLabel,
            pour_ml=o.pourMl,
            price_krw=o.priceKrw,
            discount_price_krw=o.discount.discountedPriceKrw if o.discount else None,
            discount_starts_at=o.discount.startsAt if o.discount else None,
            discount_ends_at=o.discount.endsAt if o.discount else None,
            sort_order=sort_order,
        )
        for sort_order, o in enumerate(options, start=1)
    ]


def _local_options(options: list[MenuOptionInput]) -> list[dict]:
    return [
        {
            **option.model_dump(mode="json"),
            "menuEntryOptionId": str(uuid4()),
            "sortOrder": index,
        }
        for index, option in enumerate(options, start=1)
    ]


def _local_for(session: Session, bar_id: UUID, raw_id: str) -> BarLocalMenuItem | None:
    try:
        item_id = UUID(raw_id)
    except ValueError:
        return None
    item = session.get(BarLocalMenuItem, item_id)
    return item if item is not None and item.bar_id == bar_id else None


def _publish(session: Session, board: MenuBoard, base_url: str, *, created: bool = False) -> BarMenuResponse:
    """Raise the version (a board created by this edit starts at 1), stamp the time, and answer the
    whole menu (spec 3.9) as it now is."""
    # clock_timestamp(), not now(): an edit that waited for the bar lock must not look older than a
    # request that committed while it waited (spec 3.14.1).
    board.published_at = session.scalar(select(func.clock_timestamp()))
    if not created:
        board.version += 1
    session.flush()
    session.expire_all()
    return get_bar_menu(session, str(board.bar_id), can_manage=lambda bar: True, base_url=base_url)


def _product_for(session: Session, body: MenuItemAddRequest, principal: Principal) -> Product:
    """The product to add: an existing active one, or a new one created with the same duplicate checks
    as a review (409 DUPLICATE_BRAND_FOUND or DUPLICATE_PRODUCT_FOUND when it is already there)."""
    errors = _Errors()
    if body.productId is not None:
        product = session.get(Product, body.productId)
        if product is None:
            errors.add("productId", "PRODUCT_NOT_FOUND", "상품을 찾을 수 없습니다.")
        elif not product.is_active:
            errors.add("productId", "PRODUCT_INACTIVE", "비활성 상품은 메뉴에 연결할 수 없습니다.")
        elif product.category != "whisky" and not is_operator(session, principal):
            errors.add("productId", "PRODUCT_NOT_APPROVED",
                "비위스키 상품은 공용 카탈로그와 연결할 수 없어요. 매장 메뉴로 등록해 주세요.")
        errors.raise_any()
        return product
    # A bar owner may publish an existing, approved catalog product, but not
    # create a globally searchable brand/product as a side effect of manual add.
    # Bar-local/pending menu items need a separate persistence model and operator
    # approval flow (tracked in issue #152). Fail closed until that exists.
    if not is_operator(session, principal):
        raise ApiError(
            403,
            "CATALOG_APPROVAL_REQUIRED",
            "새 상품은 관리자 승인 후 카탈로그에 등록할 수 있어요. 현재 직접 등록은 지원하지 않아요.",
        )
    new = body.newProduct
    if new.brand.type == "existing" and session.get(Brand, new.brand.brandId) is None:
        errors.add("newProduct.brand.brandId", "BRAND_NOT_FOUND", "브랜드를 찾을 수 없습니다.")
    errors.raise_any()
    product_id = create_new_product(
        session, new.brand, new.product, new.aliases, created_by_user_id=caller_user_id(session, principal)
    )
    return session.get(Product, product_id)


def _add_once(
    session: Session, principal: Principal, bar_id: UUID, body: MenuItemAddRequest, base_url: str
) -> BarMenuResponse:
    board = _open_board(session, principal, bar_id, body.menuVersion)
    if body.localItem is not None:
        existing_local = session.scalars(
            select(BarLocalMenuItem).where(BarLocalMenuItem.bar_id == bar_id)
        ).all()
        for previous in existing_local:
            if normalize(previous.display_name) == normalize(body.displayName):
                raise ApiError(409, "MENU_ITEM_EXISTS",
                    "이미 등록한 메뉴예요. 기존 메뉴를 수정해 주세요.",
                    details={"barMenuItemId": str(previous.id)})
        created = board is None
        if created:
            board = MenuBoard(bar_id=bar_id, published_at=func.now(), version=1)
            session.add(board)
        session.add(BarLocalMenuItem(
            bar_id=bar_id,
            display_name=body.displayName,
            category=body.localItem.category,
            options=_local_options(body.options),
        ))
        return _publish(session, board, base_url, created=created)
    product = _product_for(session, body, principal)
    entries = board.entries if board is not None else []
    on_board = next((e for e in entries if e.bar_menu_item.product_id == product.id), None)
    if on_board is not None:
        raise ApiError(
            409,
            "MENU_ITEM_EXISTS",
            "이 상품은 이미 메뉴에 있습니다. 그 항목을 수정해 주세요.",
            details={"barMenuItemId": str(on_board.bar_menu_item_id)},
        )

    created = board is None
    if created:
        # The first add creates the board at version 1; _publish sets the time.
        board = MenuBoard(bar_id=bar_id, published_at=func.now(), version=1)
        session.add(board)
    # A product the bar sold before keeps its bar menu item, and with it its barMenuItemId.
    item = session.scalar(select(BarMenuItem).where(BarMenuItem.bar_id == bar_id, BarMenuItem.product_id == product.id))
    if item is None:
        item = BarMenuItem(bar_id=bar_id, product_id=product.id)
        session.add(item)
        session.flush()
    board.entries.append(
        MenuBoardEntry(
            bar_menu_item_id=item.id,
            display_name=body.displayName or product.display_name,
            sort_order=max((e.sort_order for e in entries), default=0) + 1,
            options=_options(body.options),
        )
    )
    return _publish(session, board, base_url, created=created)


def _approve_local_once(
    session: Session, principal: Principal, bar_id: UUID, local_id: str,
    body: LocalMenuApprovalRequest, base_url: str,
) -> BarMenuResponse:
    if not is_operator(session, principal):
        raise forbidden()
    board = _open_board(session, principal, bar_id, body.menuVersion)
    local = _local_for(session, bar_id, local_id)
    if local is None:
        raise _item_not_found(local_id)
    if local.category != "whisky":
        raise ApiError(409, "NOT_PENDING_WHISKY",
            "위스키 승인 대기 항목만 카탈로그에 연결할 수 있어요.")
    if (body.productId is None) == (body.newProduct is None):
        raise validation_failed_fields([{
            "path": "productId", "code": "EXACTLY_ONE_REQUIRED",
            "message": "productId 또는 newProduct 중 하나가 필요합니다.",
        }])
    price_options = [
        MenuOptionInput.model_validate({
            "optionLabel": o.get("optionLabel"), "pourMl": o.get("pourMl"),
            "priceKrw": o["priceKrw"], "discount": o.get("discount"),
        }) for o in local.options
    ]
    add_body = MenuItemAddRequest(
        menuVersion=body.menuVersion, productId=body.productId,
        newProduct=body.newProduct,
        displayName=local.display_name, options=price_options,
    )
    check_request(add_body, datetime.now(timezone.utc))
    product = _product_for(session, add_body, principal)
    if product.category != "whisky":
        raise ApiError(409, "NOT_APPROVED_WHISKY",
            "승인할 카탈로그 상품은 위스키여야 합니다.")
    if board is None:
        raise _item_not_found(local_id)
    if any(entry.bar_menu_item.product_id == product.id for entry in board.entries):
        raise ApiError(409, "MENU_ITEM_EXISTS",
            "이미 같은 상품이 매장 메뉴에 등록되어 있어요.")
    item = session.scalar(select(BarMenuItem).where(
        BarMenuItem.bar_id == bar_id, BarMenuItem.product_id == product.id,
    ))
    if item is None:
        item = BarMenuItem(bar_id=bar_id, product_id=product.id)
        session.add(item)
        session.flush()
    board.entries.append(MenuBoardEntry(
        bar_menu_item_id=item.id, display_name=local.display_name,
        sort_order=max((entry.sort_order for entry in board.entries), default=0) + 1,
        options=_options(price_options),
    ))
    item.sold_out_at = local.sold_out_at
    session.delete(local)
    return _publish(session, board, base_url)


def _update_once(
    session: Session,
    principal: Principal,
    bar_id: UUID,
    bar_menu_item_id: str,
    body: MenuItemUpdateRequest,
    base_url: str,
) -> BarMenuResponse:
    board = _open_board(session, principal, bar_id, body.menuVersion)
    local = _local_for(session, bar_id, bar_menu_item_id)
    if local is not None:
        local.display_name = body.displayName
        if body.category is not None:
            local.category = body.category
        local.options = _local_options(body.options)
        return _publish(session, board, base_url)
    entry = board_entry(board, bar_menu_item_id)
    if body.category is not None and (
        body.category != entry.bar_menu_item.product.category
        or entry.bar_menu_item.product.category != "whisky"
    ):
        # Detach only this bar's listing. The shared catalog row and other bars stay untouched.
        session.add(BarLocalMenuItem(
            bar_id=bar_id, display_name=body.displayName, category=body.category,
            options=_local_options(body.options), sold_out_at=entry.bar_menu_item.sold_out_at,
        ))
        board.entries.remove(entry)
        clear_sold_out(session, {entry.bar_menu_item_id})
        return _publish(session, board, base_url)
    entry.display_name = body.displayName
    # Delete the old options before inserting the new ones, which reuse their sort orders.
    entry.options.clear()
    session.flush()
    entry.options.extend(_options(body.options))
    return _publish(session, board, base_url)


def _delete_once(
    session: Session, principal: Principal, bar_id: UUID, bar_menu_item_id: str, menu_version: int, base_url: str
) -> BarMenuResponse:
    board = _open_board(session, principal, bar_id, menu_version)
    local = _local_for(session, bar_id, bar_menu_item_id)
    if local is not None:
        session.delete(local)
        return _publish(session, board, base_url)
    # The entry and its options go; the bar menu item stays for a later add of the same product, back
    # on sale. The other entries keep their sort orders, so the order may have a gap.
    entry = board_entry(board, bar_menu_item_id)
    board.entries.remove(entry)
    clear_sold_out(session, {entry.bar_menu_item_id})
    return _publish(session, board, base_url)


def _reset_once(
    session: Session, principal: Principal, bar_id: UUID, body: MenuResetRequest, base_url: str
) -> BarMenuResponse:
    board = _open_board(session, principal, bar_id, body.menuVersion)
    for local in session.scalars(
        select(BarLocalMenuItem).where(BarLocalMenuItem.bar_id == bar_id)
    ).all():
        session.delete(local)
    if board is None:
        # Nothing to empty: the answer is the menu as it is, with nothing changed.
        return get_bar_menu(session, str(bar_id), can_manage=lambda bar: True, base_url=base_url)
    clear_sold_out(session, {entry.bar_menu_item_id for entry in board.entries})
    board.entries.clear()
    return _publish(session, board, base_url)


def _run(session_factory: SessionFactory, bar_id: UUID, label: str, work) -> BarMenuResponse:
    return run_serializable(
        session_factory,
        work,
        label=f"{label} {bar_id}",
        conflict=write_conflict("다른 요청과 동시에 처리되어 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."),
    )


def approve_local_menu_item(
    session_factory: SessionFactory, principal: Principal, bar_id: UUID,
    local_id: str, body: LocalMenuApprovalRequest, *, base_url: str,
) -> BarMenuResponse:
    return _run(
        session_factory, bar_id, "approve local menu",
        lambda session: _approve_local_once(session, principal, bar_id, local_id, body, base_url),
    )


def add_menu_item(
    session_factory: SessionFactory, principal: Principal, bar_id: UUID, body: MenuItemAddRequest, *, base_url: str
) -> BarMenuResponse:
    return _run(
        session_factory, bar_id, "menu add", lambda session: _add_once(session, principal, bar_id, body, base_url)
    )


def update_menu_item(
    session_factory: SessionFactory,
    principal: Principal,
    bar_id: UUID,
    bar_menu_item_id: str,
    body: MenuItemUpdateRequest,
    *,
    base_url: str,
) -> BarMenuResponse:
    return _run(
        session_factory,
        bar_id,
        "menu edit",
        lambda session: _update_once(session, principal, bar_id, bar_menu_item_id, body, base_url),
    )


def delete_menu_item(
    session_factory: SessionFactory,
    principal: Principal,
    bar_id: UUID,
    bar_menu_item_id: str,
    menu_version: int,
    *,
    base_url: str,
) -> BarMenuResponse:
    return _run(
        session_factory,
        bar_id,
        "menu delete",
        lambda session: _delete_once(session, principal, bar_id, bar_menu_item_id, menu_version, base_url),
    )


def reset_menu(
    session_factory: SessionFactory, principal: Principal, bar_id: UUID, body: MenuResetRequest, *, base_url: str
) -> BarMenuResponse:
    return _run(
        session_factory, bar_id, "menu reset", lambda session: _reset_once(session, principal, bar_id, body, base_url)
    )
