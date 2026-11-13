"""An operator resolving a menu item check (API spec 3.18.3).

Order of checks, the first failure answering: the check exists (404 MENU_ITEM_CHECK_NOT_FOUND); then in
one SERIALIZABLE transaction: lock the bar row (spec 3.14.1); the bar is active (404 BAR_NOT_FOUND); no
unfinished import (409 ACTIVE_IMPORT_EXISTS, so an owner's review never decides on a board that changed
under it); the check is still open (409 INVALID_CHECK_STATE); the resolution fits the item (422
RESOLUTION_NOT_ALLOWED); then the product or brand (422 PRODUCT_NOT_FOUND, PRODUCT_INACTIVE,
BRAND_NOT_FOUND; 409 DUPLICATE_*).

Linking moves the line by the rule in app.services.menu_links, so the item may change; the check stays on
the item it was resolved on. A link or mark_as_other raises the board's version but not `publishedAt`:
what customers see (names and prices) does not change. keep and aliases alone change no version.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.adapters.storage import ImageStorage
from app.core.errors import ApiError, validation_failed, validation_failed_fields
from app.core.normalize import normalize
from app.core.security import Principal
from app.models import (
    Bar,
    BarStatus,
    Brand,
    CheckReason,
    CheckResolution,
    CheckStatus,
    MenuBoard,
    MenuBoardEntry,
    MenuItemCheck,
    MenuItemKind,
    Product,
)
from app.schemas.menu_check import CreateAndLink, Keep, LinkExisting, MarkAsOther, MenuItemCheckResponse, ResolveRequest
from app.services.bar_menu import bar_not_found
from app.services.menu_check_list import check_responses
from app.services.menu_checks import raise_check
from app.services.menu_import_upload import check_no_unfinished_import
from app.services.menu_links import link_entry
from app.services.menu_review_catalog import add_product_aliases, create_new_product
from app.services.serializable import SessionFactory, run_serializable, write_conflict
from app.services.users import caller_user_id


def check_not_found(check_id: str) -> ApiError:
    return ApiError(404, "MENU_ITEM_CHECK_NOT_FOUND", "메뉴 항목 확인을 찾을 수 없습니다.", details={"checkId": check_id})


def find_check_bar(session: Session, check_id: str) -> UUID:
    """The bar of the check; 404 MENU_ITEM_CHECK_NOT_FOUND when there is none or the id is not a UUID."""
    try:
        bar_id = session.scalar(select(MenuItemCheck.bar_id).where(MenuItemCheck.id == UUID(check_id)))
    except ValueError:
        bar_id = None
    if bar_id is None:
        raise check_not_found(check_id)
    return bar_id


def check_request(request: ResolveRequest) -> None:
    """Names that normalize to nothing, all reported together as one 422; checked before the check is
    looked up, like the other rules a request breaks on its own (spec 3.18.3)."""
    texts: list[tuple[str, str]] = []
    if isinstance(request, LinkExisting):
        texts += [(f"aliasesToAdd[{i}].aliasText", a.aliasText) for i, a in enumerate(request.aliasesToAdd)]
    elif isinstance(request, CreateAndLink):
        if request.brand.type == "new":
            texts.append(("brand.canonicalName", request.brand.canonicalName))
            texts += [(f"brand.aliases[{i}].aliasText", a.aliasText) for i, a in enumerate(request.brand.aliases)]
        texts.append(("product.displayName", request.product.displayName))
        texts += [(f"aliases[{i}].aliasText", a.aliasText) for i, a in enumerate(request.aliases)]
    errors = [
        {"path": path, "code": "NOT_NORMALIZABLE", "message": "이름으로 쓸 수 있는 글자가 없습니다."}
        for path, text in texts
        if not normalize(text)
    ]
    if errors:
        raise validation_failed_fields(errors)


def _not_allowed(message: str) -> ApiError:
    return validation_failed("resolution", "RESOLUTION_NOT_ALLOWED", message)


def _resolve_once(
    session: Session, principal: Principal, check_id: str, request: ResolveRequest, storage: ImageStorage, base_url: str
) -> MenuItemCheckResponse:
    bar_id = find_check_bar(session, check_id)
    status = session.scalar(select(Bar.status).where(Bar.id == bar_id).with_for_update())
    if status != BarStatus.ACTIVE:
        raise bar_not_found(str(bar_id))
    check_no_unfinished_import(session, bar_id)
    check = session.scalar(
        select(MenuItemCheck).where(MenuItemCheck.id == UUID(check_id)).options(selectinload(MenuItemCheck.reasons))
    )
    if check.status != CheckStatus.OPEN:
        raise ApiError(
            409,
            "INVALID_CHECK_STATE",
            "이미 처리되었거나 닫힌 확인입니다.",
            details={"checkId": str(check.id), "status": check.status.value},
        )
    board = session.scalar(
        select(MenuBoard)
        .where(MenuBoard.bar_id == bar_id)
        .options(
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.options),
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.bar_menu_item),
        )
    )
    entry = next((e for e in (board.entries if board else []) if e.bar_menu_item_id == check.bar_menu_item_id), None)
    if entry is None:
        # An open check's item is on the board; leaving it dismisses the check (spec 3.18.1).
        raise ApiError(
            409,
            "INVALID_CHECK_STATE",
            "메뉴판에 없는 항목의 확인입니다.",
            details={"checkId": str(check.id), "status": check.status.value},
        )
    item = entry.bar_menu_item

    if isinstance(request, Keep):
        if item.product_id is None:
            raise _not_allowed("상품에 연결되지 않은 항목은 그대로 둘 수 없습니다. 상품에 연결해 주세요.")
        product_id = item.product_id
    elif isinstance(request, MarkAsOther):
        if item.product_id is not None:
            raise _not_allowed("상품에 연결된 항목은 위스키가 아닌 메뉴로 바꿀 수 없습니다.")
        item.kind = MenuItemKind.OTHER
        board.version += 1
        product_id = None
    else:
        product_id = _product_for(session, principal, request)
        linking = item.product_id != product_id
        result = link_entry(session, board, entry, product_id)
        if result.discarded:
            # The merge kept the staying line's prices; the dropped ones wait for an operator (spec 3.14.1).
            check_for_prices = raise_check(
                session, result.entry.bar_menu_item, result.entry.display_name, CheckReason.PRICE_CONFLICT
            )
            check_for_prices.discarded_options = [*check_for_prices.discarded_options, *result.discarded]
        if linking:
            # Search now finds the item; edits opened before must see the change (spec 3.18.3).
            board.version += 1

    # Read the caller first: a query would flush a half-closed check, which the table's checks refuse.
    resolved_by = caller_user_id(session, principal)
    check.status = CheckStatus.RESOLVED
    check.resolution = CheckResolution(request.resolution)
    check.resolved_product_id = product_id
    check.resolved_by_user_id = resolved_by
    check.resolved_at = func.clock_timestamp()
    session.flush()
    session.expire_all()
    check = session.scalar(
        select(MenuItemCheck).where(MenuItemCheck.id == UUID(check_id)).options(selectinload(MenuItemCheck.reasons))
    )
    return check_responses(session, [check], storage, base_url)[0]


def _product_for(session: Session, principal: Principal, request: LinkExisting | CreateAndLink) -> UUID:
    if isinstance(request, LinkExisting):
        product = session.get(Product, request.productId)
        if product is None:
            raise validation_failed("productId", "PRODUCT_NOT_FOUND", "상품을 찾을 수 없습니다.")
        if not product.is_active:
            raise validation_failed("productId", "PRODUCT_INACTIVE", "비활성 상품은 메뉴에 연결할 수 없습니다.")
        add_product_aliases(session, product.id, request.aliasesToAdd)
        return product.id
    if request.brand.type == "existing" and session.get(Brand, request.brand.brandId) is None:
        raise validation_failed("brand.brandId", "BRAND_NOT_FOUND", "브랜드를 찾을 수 없습니다.")
    return create_new_product(
        session, request.brand, request.product, request.aliases, created_by_user_id=caller_user_id(session, principal)
    )


def resolve_check(
    session_factory: SessionFactory,
    principal: Principal,
    check_id: str,
    request: ResolveRequest,
    storage: ImageStorage,
    *,
    base_url: str,
) -> MenuItemCheckResponse:
    return run_serializable(
        session_factory,
        lambda session: _resolve_once(session, principal, check_id, request, storage, base_url),
        label=f"menu item check {check_id}",
        conflict=write_conflict("다른 요청과 동시에 처리되어 저장하지 못했습니다. 잠시 후 다시 시도해 주세요."),
    )
