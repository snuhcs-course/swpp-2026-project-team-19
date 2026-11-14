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

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ApiError, validation_failed, validation_failed_fields
from app.core.normalize import normalize
from app.core.security import Principal
from app.models import (
    Bar,
    BarMenuItem,
    BarStatus,
    Brand,
    CheckReason,
    MenuBoard,
    MenuBoardEntry,
    MenuEntryOption,
    MenuItemKind,
    Product,
)
from app.schemas.menu import BarMenuResponse
from app.schemas.menu_edit import MenuItemAddRequest, MenuItemUpdateRequest, MenuOptionInput, MenuResetRequest
from app.services.bar_access import can_manage_bar, forbidden, is_operator
from app.services.bar_menu import bar_not_found, get_bar_menu
from app.matching.db_catalog import DbCatalog
from app.matching.rematch import name_corrected, rematch_name
from app.services.menu_checks import (
    dismiss_open_checks,
    move_open_check,
    raise_check,
    rename_open_check,
    settle_linked,
)
from app.services.menu_import_upload import check_no_unfinished_import
from app.services.menu_items import name_key, unlinked_entry_with_key
from app.services.menu_links import link_entry, unlink_entry
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
        if [body.productId, body.newProduct, body.kind].count(None) != 2:
            errors.add("productId", "EXACTLY_ONE_REQUIRED", "productId, newProduct, kind 중 하나만 보내야 합니다.")
        if body.kind is not None:
            # An item without a product is known only by its menu name (spec 3.14.3).
            if body.displayName is None:
                errors.add("displayName", "MISSING", "상품 없이 추가하려면 메뉴 이름이 필요합니다.")
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


def _item_exists(bar_menu_item_id: UUID, *, unlinked: bool = False) -> ApiError:
    message = (
        "같은 이름의 메뉴가 이미 있습니다. 그 항목을 수정해 주세요."
        if unlinked
        else "이 상품은 이미 메뉴에 있습니다. 그 항목을 수정해 주세요."
    )
    return ApiError(409, "MENU_ITEM_EXISTS", message, details={"barMenuItemId": str(bar_menu_item_id)})


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
        errors.raise_any()
        return product
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
    entries = board.entries if board is not None else []
    if body.kind is not None:
        item, display_name = _unlinked_item(session, bar_id, entries, body.kind, body.displayName)
    else:
        if body.newProduct is not None and not is_operator(session, principal):
            # Checked after the caller may manage the bar: an owner may add, but not grow the shared catalog.
            raise validation_failed("newProduct", "OPERATOR_ONLY", "새 상품은 운영자만 만들 수 있습니다.")
        item, display_name = _linked_item(session, bar_id, entries, body, principal)

    created = board is None
    if created:
        # The first add creates the board at version 1; _publish sets the time.
        board = MenuBoard(bar_id=bar_id, published_at=func.now(), version=1)
        session.add(board)
    board.entries.append(
        MenuBoardEntry(
            bar_menu_item_id=item.id,
            display_name=display_name,
            sort_order=max((e.sort_order for e in entries), default=0) + 1,
            options=_options(body.options),
        )
    )
    if item.product_id is None and item.kind == MenuItemKind.WHISKY:
        # It waits for an operator to link it, and only then appears in search (spec 3.18.1).
        raise_check(session, item, display_name, CheckReason.UNLINKED)
    return _publish(session, board, base_url, created=created)


def _unlinked_item(
    session: Session, bar_id: UUID, entries: list[MenuBoardEntry], kind: MenuItemKind, display_name: str
) -> tuple[BarMenuItem, str]:
    """A new item without a product (spec 3.14.3). One with the same name key already on the board is the
    same item; one that left the board is not reused."""
    key = name_key(display_name)
    if (same := unlinked_entry_with_key(entries, key)) is not None:
        raise _item_exists(same.bar_menu_item_id, unlinked=True)
    item = BarMenuItem(bar_id=bar_id, kind=kind, name_key=key)
    session.add(item)
    session.flush()
    return item, display_name


def _linked_item(
    session: Session, bar_id: UUID, entries: list[MenuBoardEntry], body: MenuItemAddRequest, principal: Principal
) -> tuple[BarMenuItem, str]:
    product = _product_for(session, body, principal)
    on_board = next((e for e in entries if e.bar_menu_item.product_id == product.id), None)
    if on_board is not None:
        raise _item_exists(on_board.bar_menu_item_id)
    # A product the bar sold before keeps its bar menu item, and with it its barMenuItemId.
    item = session.scalar(select(BarMenuItem).where(BarMenuItem.bar_id == bar_id, BarMenuItem.product_id == product.id))
    if item is None:
        item = BarMenuItem(bar_id=bar_id, product_id=product.id)
        session.add(item)
        session.flush()
    return item, body.displayName or product.display_name


def _update_once(
    session: Session,
    principal: Principal,
    bar_id: UUID,
    bar_menu_item_id: str,
    body: MenuItemUpdateRequest,
    base_url: str,
) -> BarMenuResponse:
    board = _open_board(session, principal, bar_id, body.menuVersion)
    entry = board_entry(board, bar_menu_item_id)
    item = entry.bar_menu_item
    # A whisky renamed to another name is matched again (spec 3.14.4, the rules of 8.11).
    product_id = item.product_id
    if item.kind == MenuItemKind.WHISKY and name_corrected(body.displayName, entry.display_name):
        product_id = rematch_name(body.displayName, DbCatalog(session))
    key = name_key(body.displayName)
    if product_id is None:
        # An item without a product is known by its name, so a new name is a new key (spec 3.14.4).
        if not key:
            raise validation_failed("displayName", "NOT_NORMALIZABLE", "이름으로 쓸 수 있는 글자가 없습니다.")
        if (same := unlinked_entry_with_key(board.entries, key, except_item_id=item.id)) is not None:
            raise _item_exists(same.bar_menu_item_id, unlinked=True)
        if item.product_id is None:
            item.name_key = key
    rename_open_check(session, item.id, body.displayName)
    entry.display_name = body.displayName
    # Delete the old options before inserting the new ones, which reuse their sort orders.
    entry.options.clear()
    session.flush()
    entry.options.extend(_options(body.options))
    session.flush()
    if product_id != item.product_id:
        _relink(session, board, entry, product_id, key)
    return _publish(session, board, base_url)


def _relink(session: Session, board: MenuBoard, entry: MenuBoardEntry, product_id: UUID | None, key: str) -> None:
    """Rematching changed the line's link (spec 3.14.4): move it by the rule of 3.14.1, take its open check
    along, and show the change to an operator. A reason raised by a manual edit has no source line."""
    old = entry.bar_menu_item
    was_unlinked = old.product_id is None
    result = link_entry(session, board, entry, product_id) if product_id else unlink_entry(session, entry, key)
    now_on = result.entry.bar_menu_item
    name = result.entry.display_name
    if was_unlinked and now_on.product_id is not None:
        settle_linked(session, old.id, now_on, name)
    else:
        move_open_check(session, old.id, now_on, name)
    reason = CheckReason.RELINKED_BY_NAME if now_on.product_id else CheckReason.UNLINKED_BY_NAME
    raise_check(session, now_on, name, reason)
    if result.discarded:
        # Merged into the line already of that product: its prices stayed (spec 3.14.1).
        check = raise_check(session, now_on, name, CheckReason.PRICE_CONFLICT)
        check.discarded_options = [*check.discarded_options, *result.discarded]


def _delete_once(
    session: Session, principal: Principal, bar_id: UUID, bar_menu_item_id: str, menu_version: int, base_url: str
) -> BarMenuResponse:
    board = _open_board(session, principal, bar_id, menu_version)
    # The entry and its options go; the bar menu item stays for a later add of the same product, back
    # on sale. The other entries keep their sort orders, so the order may have a gap.
    entry = board_entry(board, bar_menu_item_id)
    board.entries.remove(entry)
    clear_sold_out(session, {entry.bar_menu_item_id})
    dismiss_open_checks(session, {entry.bar_menu_item_id})
    return _publish(session, board, base_url)


def _reset_once(
    session: Session, principal: Principal, bar_id: UUID, body: MenuResetRequest, base_url: str
) -> BarMenuResponse:
    board = _open_board(session, principal, bar_id, body.menuVersion)
    if board is None:
        # Nothing to empty: the answer is the menu as it is, with nothing changed.
        return get_bar_menu(session, str(bar_id), can_manage=lambda bar: True, base_url=base_url)
    clear_sold_out(session, {entry.bar_menu_item_id for entry in board.entries})
    dismiss_open_checks(session, {entry.bar_menu_item_id for entry in board.entries})
    board.entries.clear()
    return _publish(session, board, base_url)


def _run(session_factory: SessionFactory, bar_id: UUID, label: str, work) -> BarMenuResponse:
    return run_serializable(
        session_factory,
        work,
        label=f"{label} {bar_id}",
        conflict=write_conflict("다른 요청과 동시에 처리되어 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."),
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
