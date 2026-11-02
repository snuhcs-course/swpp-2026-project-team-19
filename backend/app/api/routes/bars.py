from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.permissions import BarId, managed_bar, require_bar_manager
from app.core.security import Principal, get_current_user, get_optional_user, require_operator
from app.db.session import get_serializable_session_factory, get_session
from app.models import Bar
from app.schemas.bar import BarDetail, BarListResponse, BarUpdateInput
from app.schemas.errors import AUTH_UNAVAILABLE, AUTH_UNAVAILABLE_DESCRIPTION, error_responses
from app.schemas.menu import BarMenuResponse
from app.schemas.menu_edit import MenuItemAddRequest, MenuItemUpdateRequest, MenuResetRequest
from app.schemas.menu_import import MenuImportListResponse
from app.services.bar_access import can_manage_bar, is_operator
from app.services.bar_admin import BarStatusFilter, ImportStatusFilter, list_bars, list_menu_imports
from app.services.bar_detail import get_bar_detail, update_bar
from app.services.bar_menu import get_bar_menu
from app.services.menu_edit import add_menu_item, check_request, delete_menu_item, reset_menu, update_menu_item
from app.services.serializable import SessionFactory

router = APIRouter(prefix="/api/bars", tags=["bars"])

_OPERATOR_ERRORS = (
    (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
    (403, "`FORBIDDEN`: the caller is not an operator."),
    AUTH_UNAVAILABLE,
)
_MANAGER_ERRORS = (
    (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
    (403, "`FORBIDDEN`: the caller is neither an operator nor the bar's current owner."),
    AUTH_UNAVAILABLE,
)
_PAGING = (
    "Pages use a cursor: pass the response's `nextCursor` as `cursor` to get the next page; "
    "`nextCursor` is null on the last page. Treat the cursor as an opaque string."
)
Cursor = Annotated[str | None, Query(description="`nextCursor` of the previous page")]
Limit = Annotated[int, Query(ge=1, le=100, description="Maximum number of items per page")]


@router.get(
    "",
    response_model=BarListResponse,
    summary="Bars an operator manages",
    description=(
        "Operator only. Bars sorted by name. `query` matches part of the name or address, ignoring case. "
        "`activeMenuImport` is the bar's unfinished import (`uploaded`, `processing` or "
        "`ready_for_review`), so the app can continue it directly; null when none.\n\n" + _PAGING
    ),
    responses=error_responses(
        *_OPERATOR_ERRORS,
        (
            422,
            "`VALIDATION_FAILED`: `query` `BLANK` or `STRING_TOO_LONG` (over 100 characters); `status` not "
            "one of the values; `limit` out of range; `cursor` `INVALID_CURSOR`.",
        ),
    ),
)
def read_bars(
    query: Annotated[str | None, Query(description="Part of the name or address; 1-100 characters")] = None,
    status: Annotated[BarStatusFilter, Query(description="`active`, `inactive` or `all`")] = "active",
    limit: Limit = 20,
    cursor: Cursor = None,
    session: Session = Depends(get_session),
    _operator: Principal = Depends(require_operator),
) -> BarListResponse:
    return list_bars(session, query=query, status=status, limit=limit, cursor=cursor)


@router.get(
    "/{barId}/menu-imports",
    response_model=MenuImportListResponse,
    summary="A bar's menu imports",
    description=(
        "Operator or the bar's owner. Newest first, to return to an unfinished import after closing the app and to "
        "look back at applied, failed or canceled ones. Open one with `GET /api/menu-imports/{menuImportId}`.\n\n"
        "`status=active` means unfinished: `uploaded`, `processing` and `ready_for_review`. "
        "Imports of inactive bars are listed too.\n\n" + _PAGING
    ),
    responses=error_responses(
        *_MANAGER_ERRORS,
        (404, "`BAR_NOT_FOUND`: no such bar or a malformed id."),
        (
            422,
            "`VALIDATION_FAILED`: `status` not one of the values; `limit` out of range; `cursor` "
            "`INVALID_CURSOR`.",
        ),
    ),
)
def read_bar_menu_imports(
    status: Annotated[
        ImportStatusFilter,
        Query(description="`active`, `uploaded`, `processing`, `ready_for_review`, `applied`, `failed`, `canceled` or `all`"),
    ] = "all",
    limit: Limit = 20,
    cursor: Cursor = None,
    session: Session = Depends(get_session),
    bar: Bar = Depends(require_bar_manager),
) -> MenuImportListResponse:
    return list_menu_imports(session, bar, status=status, limit=limit, cursor=cursor)


@router.get(
    "/{barId}/menu",
    response_model=BarMenuResponse,
    summary="Bar info and its current published menu",
    description=(
        "Used by the customer bar detail screen, by operators and by bar owners.\n\n"
        "- Public for active bars; no token is needed. A token that is sent must be valid (`401` "
        "otherwise), but one the server cannot check right now (Supabase outage, missing settings) "
        "is treated as no token rather than failing with `503`.\n"
        "- Inactive bars are returned only to operators and the bar's current owner. Anyone else gets "
        "`404 BAR_NOT_FOUND`, the same as for a missing bar.\n"
        "- Sold-out items are left out for everyone but operators and the bar's current owner, who get "
        "them in place with `soldOut: true` (a token the server cannot check counts as no token).\n"
        "- A bar without a published menu returns `200` with `menuBoardId: null` and `items: []`. A menu "
        "whose items were all taken down, or are all sold out for a customer, keeps `menuBoardId` and "
        "`publishedAt`, with `items: []`.\n"
        "- `menuVersion` goes up with every review publish and manual edit; manual edits send it back.\n"
        "- `options[].discount` comes only while the discount has not ended (one that has not started yet comes "
        "too); `priceKrw` is always the list price. The app shows the discounted price while "
        "`startsAt <= now < endsAt`.\n"
        "- `phone`, `optionLabel`, `pourMl` and `discount` are null when missing. Coordinates are WGS84 and never "
        "null.\n"
        "- Items and their options are sorted by `sortOrder`."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: an Authorization header was sent but the token is invalid or expired."),
        (404, "`BAR_NOT_FOUND`: no such bar, a malformed id, or an inactive bar for anyone but an operator or its owner."),
    ),
)
def read_bar_menu(
    bar_id: Annotated[str, Path(alias="barId", description="Bar id (UUID)")],
    session: Session = Depends(get_session),
    user: Principal | None = Depends(get_optional_user),
) -> BarMenuResponse:
    return get_bar_menu(
        session, bar_id, can_manage=lambda bar: user is not None and can_manage_bar(session, user, bar.id)
    )


@router.get(
    "/{barId}",
    response_model=BarDetail,
    summary="A bar with its management state",
    description=(
        "Operator or the bar's owner. The bar, its unfinished import, a summary of the published menu, and "
        "its current owner; not the menu items (use `GET /api/bars/{barId}/menu`). Inactive bars are "
        "returned too."
    ),
    responses=error_responses(*_MANAGER_ERRORS, (404, "`BAR_NOT_FOUND`: no such bar or a malformed id.")),
)
def read_bar(
    session: Session = Depends(get_session),
    bar: Bar = Depends(require_bar_manager),
) -> BarDetail:
    return get_bar_detail(session, bar)


@router.patch(
    "/{barId}",
    response_model=BarDetail,
    summary="Edit a bar, or deactivate it",
    description=(
        "Operator or the bar's owner. Send only the fields to change; the response is the bar as in "
        "`GET /api/bars/{barId}`. An empty body changes nothing.\n\n"
        "- `name` and `address` cannot be null. Surrounding spaces are removed.\n"
        "- `latitude` and `longitude` are sent together. A new `address` needs both, so the map "
        "position follows it; coordinates alone can correct the position.\n"
        "- `phone`: null or blank removes it.\n"
        "- `status` (`active` or `inactive`) only by operators; an owner who sends it gets `403`. "
        "An inactive bar leaves customer search and takes no new upload."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
        (
            403,
            "`FORBIDDEN`: the caller is neither an operator nor the bar's current owner, or an owner sent `status`.",
        ),
        AUTH_UNAVAILABLE,
        (404, "`BAR_NOT_FOUND`: no such bar or a malformed id."),
        (
            422,
            "`VALIDATION_FAILED`: a field rule (`NULL_NOT_ALLOWED`, `STRING_TOO_SHORT`, `STRING_TOO_LONG`, a "
            "coordinate out of range, `EXTRA_FORBIDDEN`), `LAT_LNG_REQUIRED_TOGETHER`, or "
            "`COORDINATES_REQUIRED` (an `address` without coordinates).",
        ),
    ),
)
def edit_bar(
    body: BarUpdateInput,
    # Declared before the bar so the token is checked first; FastAPI runs it once for both.
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    bar: Bar = Depends(require_bar_manager),
) -> BarDetail:
    return update_bar(session, bar, body, operator=is_operator(session, principal))


# ---- manual menu edits (spec 3.14) ----

_EDIT_RULES = (
    "Operator or the bar's owner. The change is published at once, with no review, and the response is "
    "the whole menu as in `GET /api/bars/{barId}/menu`, so the app needs no reload.\n\n"
    "- Send the `menuVersion` of the menu the edit was made on; a different one changes nothing and "
    "answers `409 MENU_OUTDATED`. A successful edit raises it by 1. A request retried after it succeeded "
    "gets `MENU_OUTDATED` too: reload the menu to see whether it was applied.\n"
    "- No edit is accepted while the bar has an unfinished import (`409 ACTIVE_IMPORT_EXISTS`).\n"
    "- Only the requested item changes; other items keep their options and discounts.\n"
    "- Checks, first failure answering: token, request (`422`), bar (`404`), caller (`403`), then under "
    "the bar row lock: inactive bar (`404`), unfinished import, `menuVersion`, then the item."
)
_OPTION_RULES = (
    "**Options**: 1 to 3, in display order. `optionLabel` 1-100 characters or null, `pourMl` 1-32767 or "
    "null (stored as sent), `priceKrw` 1-99,999,999. `discount` is optional: `discountedPriceKrw` lower "
    "than `priceKrw`, `startsAt` and `endsAt` with a time zone, `endsAt` after `startsAt` and after now."
)
_EDIT_COMMON_ERRORS = (
    (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
    (403, "`FORBIDDEN`: the caller is neither an operator nor the bar's current owner."),
    (
        503,
        "`TEMPORARY_WRITE_CONFLICT`: conflicted with concurrent writes three times; send the same request "
        "again. " + AUTH_UNAVAILABLE_DESCRIPTION,
    ),
)
_EDIT_CONFLICTS = (
    "`ACTIVE_IMPORT_EXISTS` (`details.menuImportId`, `details.status`); `MENU_OUTDATED` "
    "(`details.submittedMenuVersion`, `details.currentMenuVersion`)"
)
_OPTION_CODES = (
    "`TOO_SHORT` or `TOO_LONG` (`options`), `DUPLICATE_OPTION_VALUES` (same label and pour size), "
    "`DISCOUNT_NOT_LOWER`, `END_BEFORE_START`, `DISCOUNT_ENDED`, `TIMEZONE_AWARE`"
)
_ITEM_NOT_FOUND = (
    "`MENU_ITEM_NOT_FOUND` (`details.barMenuItemId`): the item is not on the current menu, or a malformed id"
)
BarMenuItemId = Annotated[str, Path(alias="barMenuItemId", description="The item's `barMenuItemId` (UUID)")]


@router.post(
    "/{barId}/menu/items",
    status_code=201,
    response_model=BarMenuResponse,
    summary="Add a menu item",
    description=(
        _EDIT_RULES
        + "\n\nSend `productId` (an active product) or `newProduct` (a product not in the catalog, as a "
        "review's `create_product`), not both. A new product is checked for duplicates as in a review and "
        "records who created it; it is used by search and matching at once. A product already on the menu "
        "is `409 MENU_ITEM_EXISTS`: edit that item instead. The item goes to the end of the menu; a product "
        "the bar sold before gets its old `barMenuItemId` back. `displayName` null means the product's name. "
        "Find the added item in the response by `productId`. The first add to a bar without a menu sends "
        "`menuVersion: null` and creates the menu at version 1.\n\n" + _OPTION_RULES
    ),
    responses=error_responses(
        *_EDIT_COMMON_ERRORS,
        (404, "`BAR_NOT_FOUND`: no such bar, a malformed id, or an inactive bar."),
        (
            409,
            _EDIT_CONFLICTS + "; `MENU_ITEM_EXISTS` (`details.barMenuItemId`); `DUPLICATE_BRAND_FOUND` / "
            "`DUPLICATE_PRODUCT_FOUND` (`details.existingBrand` / `existingProduct`; use it, or search the "
            "catalog when `existingProduct.isActive` is false).",
        ),
        (
            422,
            "`VALIDATION_FAILED`: field rules, " + _OPTION_CODES + ", `EXACTLY_ONE_REQUIRED` (`productId`), "
            "`NOT_NORMALIZABLE` (a new name with no usable characters), `PRODUCT_NOT_FOUND`, "
            "`PRODUCT_INACTIVE`, `BRAND_NOT_FOUND`.",
        ),
    ),
)
def add_bar_menu_item(
    bar_id: BarId,
    body: MenuItemAddRequest,
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    session_factory: SessionFactory = Depends(get_serializable_session_factory),
) -> BarMenuResponse:
    check_request(body, datetime.now(timezone.utc))
    bar = managed_bar(session, principal, bar_id)
    return add_menu_item(session_factory, principal, bar.id, body)


@router.put(
    "/{barId}/menu/items/{barMenuItemId}",
    response_model=BarMenuResponse,
    summary="Edit a menu item",
    description=(
        _EDIT_RULES
        + "\n\nReplaces the item's menu name and all of its options; the product and the position stay. "
        "To keep a discount, send the `discount` from the menu back; leaving it out removes it. On "
        "`DISCOUNT_ENDED`, drop that discount and send again. To link another product, delete the item and "
        "add the product.\n\n" + _OPTION_RULES
    ),
    responses=error_responses(
        *_EDIT_COMMON_ERRORS,
        (404, "`BAR_NOT_FOUND`: no such bar, a malformed id, or an inactive bar; " + _ITEM_NOT_FOUND + "."),
        (409, _EDIT_CONFLICTS + "."),
        (422, "`VALIDATION_FAILED`: field rules, " + _OPTION_CODES + "."),
    ),
)
def edit_bar_menu_item(
    bar_id: BarId,
    bar_menu_item_id: BarMenuItemId,
    body: MenuItemUpdateRequest,
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    session_factory: SessionFactory = Depends(get_serializable_session_factory),
) -> BarMenuResponse:
    check_request(body, datetime.now(timezone.utc))
    bar = managed_bar(session, principal, bar_id)
    return update_menu_item(session_factory, principal, bar.id, bar_menu_item_id, body)


@router.delete(
    "/{barId}/menu/items/{barMenuItemId}",
    response_model=BarMenuResponse,
    summary="Delete a menu item",
    description=(
        _EDIT_RULES
        + "\n\nTakes the item off the menu; the other items keep their `sortOrder`, so the order may have a "
        "gap. Its `barMenuItemId` stays and comes back when the same product is added again. Deleting the "
        "last item keeps the menu with `items: []`."
    ),
    responses=error_responses(
        *_EDIT_COMMON_ERRORS,
        (404, "`BAR_NOT_FOUND`: no such bar, a malformed id, or an inactive bar; " + _ITEM_NOT_FOUND + "."),
        (409, _EDIT_CONFLICTS + "."),
        (422, "`VALIDATION_FAILED`: `menuVersion` `MISSING` or not an integer."),
    ),
)
def delete_bar_menu_item(
    bar_id: BarId,
    bar_menu_item_id: BarMenuItemId,
    menu_version: Annotated[int, Query(alias="menuVersion", description="`menuVersion` of the menu")],
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    session_factory: SessionFactory = Depends(get_serializable_session_factory),
) -> BarMenuResponse:
    bar = managed_bar(session, principal, bar_id)
    return delete_menu_item(session_factory, principal, bar.id, bar_menu_item_id, menu_version)


@router.post(
    "/{barId}/menu/reset",
    response_model=BarMenuResponse,
    summary="Empty the menu",
    description=(
        _EDIT_RULES
        + "\n\nTakes every item off the menu, with their discounts. The menu stays, with `menuBoardId` and "
        "`publishedAt` and `items: []`. A bar without a menu (`menuVersion: null`) changes nothing and "
        "answers `200`. There is no undo: confirm with the user first."
    ),
    responses=error_responses(
        *_EDIT_COMMON_ERRORS,
        (404, "`BAR_NOT_FOUND`: no such bar, a malformed id, or an inactive bar."),
        (409, _EDIT_CONFLICTS + "."),
        (422, "`VALIDATION_FAILED`: `menuVersion` `MISSING`, or neither an integer nor null."),
    ),
)
def reset_bar_menu(
    bar_id: BarId,
    body: MenuResetRequest,
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    session_factory: SessionFactory = Depends(get_serializable_session_factory),
) -> BarMenuResponse:
    bar = managed_bar(session, principal, bar_id)
    return reset_menu(session_factory, principal, bar.id, body)
