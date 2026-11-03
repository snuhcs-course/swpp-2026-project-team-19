from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Path, Query
from sqlalchemy.orm import Session

from app.adapters.storage import ImageStorage
from app.api.deps import get_base_url, get_image_storage
from app.api.permissions import BarId, managed_bar, require_bar_manager
from app.api.routes.menu_imports import UploadedImage
from app.core.security import Principal, get_current_user, get_optional_user, require_operator
from app.db.session import get_serializable_session_factory, get_session
from app.models import Bar
from app.schemas.bar import BarDetail, BarListResponse, BarPhotosResponse, BarUpdateInput, PhotoOrderRequest
from app.schemas.bar_hours import OperatingExceptionInput
from app.schemas.errors import AUTH_UNAVAILABLE, AUTH_UNAVAILABLE_DESCRIPTION, error_responses
from app.schemas.menu import BarMenuResponse
from app.schemas.menu_edit import (
    MenuConfirmRequest,
    MenuItemAddRequest,
    MenuItemUpdateRequest,
    MenuResetRequest,
    SoldOutRequest,
)
from app.schemas.menu_import import MenuImportListResponse
from app.services.bar_access import can_manage_bar, is_operator
from app.services.bar_admin import BarStatusFilter, ImportStatusFilter, list_bars, list_menu_imports
from app.services.bar_detail import get_bar_detail, update_bar
from app.services.bar_menu import get_bar_menu
from app.services.bar_photo_image import MAX_LONG_EDGE, MAX_PHOTO_BYTES, THUMBNAIL_LONG_EDGE, single_upload
from app.services.bar_photos import MAX_PHOTOS, add_photo, check_photo_order, delete_photo, reorder_photos
from app.services.menu_edit import add_menu_item, check_request, delete_menu_item, reset_menu, update_menu_item
from app.services.menu_import_upload import ImageUpload
from app.services.menu_status import confirm_menu, set_sold_out
from app.services.operating_exception import apply_operating_exception, cancel_operating_exception
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
        "- `description`: one line of introduction, up to 100 characters (line breaks allowed and counted). "
        "null or blank removes it. Stored as sent, without escaping.\n"
        "- `defaultPourMl`: 1-999, null removes it. Only pre-fills glass options in the app; the menu is not "
        "changed.\n"
        "- `tags`: replaces all tags, in display order; `[]` removes them, null is not allowed. Up to 5, each "
        "1-24 characters on one line, unique ignoring case; stored with their case as sent.\n"
        "- `weeklyHours`: replaces all regular hours; `[]` removes them, null is not allowed. One entry per "
        "`dayOfWeek` (1 = Monday); `closed: true` is a day off and takes no times, otherwise `openTime` and "
        "`closeTime` are Seoul local `HH:MM` in 5-minute steps, different, and a close earlier than the open "
        "ends the next day. A change moves `updatedAt`.\n"
        "- `status` (`active` or `inactive`) only by operators; an owner who sends it gets `403`. "
        "An inactive bar leaves customer search and takes no new upload.\n"
        "- The temporary closure is changed with `PUT /api/bars/{barId}/operating-exception`; sending "
        "`operatingException` here is `EXTRA_FORBIDDEN`."
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
            "coordinate or `defaultPourMl` out of range, `TOO_LONG` for more than 5 tags, `EXTRA_FORBIDDEN`), "
            "`LAT_LNG_REQUIRED_TOGETHER`, `COORDINATES_REQUIRED` (an `address` without coordinates), "
            "`INVALID_CHARACTER` and `DUPLICATE_TAG` (`tags[i]`), or an hours rule (`weeklyHours[i].<field>`): "
            "`MISSING`, `DUPLICATE_DAY`, `INVALID_TIME`, `SAME_OPEN_CLOSE`, `TIME_ON_CLOSED_DAY`.",
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


# ---- the temporary closure (spec 3.15.2 to 3.15.4) ----

_EXCEPTION_RULES = (
    "Operator or the bar's owner; inactive bars too. The response is the bar as in `GET /api/bars/{barId}`.\n\n"
    "- `operatingException` is sent through the day after its `endDate` (a `custom_hours` past midnight still "
    "applies early that morning), then null. Whether it is in effect now is for the app to compute; the "
    "server sends no open status.\n"
    "- Changing it does not move `updatedAt`."
)


@router.put(
    "/{barId}/operating-exception",
    response_model=BarDetail,
    summary="Apply a temporary closure or today's changed hours",
    description=(
        _EXCEPTION_RULES
        + "\n\nReplaces the bar's closure, a `vacation` not started yet included. By `kind`:\n\n"
        "- `closed_today`: `date`, today in Seoul when the user applies it.\n"
        "- `custom_hours`: `date` as above, `openTime` and `closeTime` (`HH:MM`, 5-minute steps, different; "
        "may end past midnight).\n"
        "- `vacation`: `startDate` today or later, `endDate` on or after it.\n\n"
        "`note` is optional for every kind: one line for customers, up to 100 characters; blank is null. "
        "A request equal to the current closure (kind, dates, times, trimmed note) changes nothing and skips "
        "the date checks, so it can be sent again safely after midnight."
    ),
    responses=error_responses(
        *_MANAGER_ERRORS,
        (404, "`BAR_NOT_FOUND`: no such bar or a malformed id."),
        (
            422,
            "`VALIDATION_FAILED`: `UNION_TAG_NOT_FOUND` or `UNION_TAG_INVALID` (`kind`), `EXTRA_FORBIDDEN` (a "
            "field of another kind), `MISSING`, `INVALID_TIME`, `SAME_OPEN_CLOSE`, `END_BEFORE_START`, "
            "`INVALID_CHARACTER` or `STRING_TOO_LONG` (`note`), `DATE_NOT_TODAY` (`date`: ask the user to "
            "apply again), `DATE_IN_PAST` (`startDate`).",
        ),
    ),
)
def put_operating_exception(
    body: Annotated[OperatingExceptionInput, Body(discriminator="kind")],
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    bar: Bar = Depends(require_bar_manager),
) -> BarDetail:
    return apply_operating_exception(session, principal, bar, body)


@router.delete(
    "/{barId}/operating-exception",
    response_model=BarDetail,
    summary="Cancel the temporary closure",
    description=(
        _EXCEPTION_RULES
        + "\n\nBack to the regular hours. `200` with `operatingException: null` also when there was none or "
        "it had ended, so it can be sent again."
    ),
    responses=error_responses(*_MANAGER_ERRORS, (404, "`BAR_NOT_FOUND`: no such bar or a malformed id.")),
)
def delete_operating_exception(
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    bar: Bar = Depends(require_bar_manager),
) -> BarDetail:
    return cancel_operating_exception(session, principal, bar)


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


# ---- sold-out and the sales info confirmation (spec 3.14.8, 3.14.9) ----

_STATUS_RULES = (
    "Operator or the bar's owner. Accepted while the bar has an unfinished import, since neither changes "
    "the menu's content: `menuVersion` does not go up and `publishedAt` stays."
)


@router.put(
    "/{barId}/menu/items/{barMenuItemId}/sold-out",
    response_model=BarMenuResponse,
    summary="Mark a menu item sold out, or back on sale",
    description=(
        _STATUS_RULES
        + "\n\n- The whole item goes sold out, not single options. Customers no longer see it in the bar menu "
        "or in search; operators and the owner get it in place with `soldOut: true`.\n"
        "- It sets a value, so sending the same request again gives the same result (`200`).\n"
        "- It stays while the item is on the menu, through edits and review publishes, and clears when the "
        "item leaves the menu.\n"
        "- The response is the menu as in `GET /api/bars/{barId}/menu`, sold-out items included.\n"
        "- Checks, first failure answering: token, request (`422`), bar (`404`), caller (`403`), then under "
        "the bar row lock: inactive bar (`404`), the item."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
        (403, "`FORBIDDEN`: the caller is neither an operator nor the bar's current owner."),
        AUTH_UNAVAILABLE,
        (404, "`BAR_NOT_FOUND`: no such bar, a malformed id, or an inactive bar; " + _ITEM_NOT_FOUND + "."),
        (422, "`VALIDATION_FAILED`: `soldOut` `MISSING` or not a boolean (`BOOL_TYPE`)."),
    ),
)
def mark_bar_menu_item_sold_out(
    bar_id: BarId,
    bar_menu_item_id: BarMenuItemId,
    body: SoldOutRequest,
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BarMenuResponse:
    bar = managed_bar(session, principal, bar_id)
    return set_sold_out(session, principal, bar.id, bar_menu_item_id, body.soldOut)


@router.post(
    "/{barId}/menu/confirm",
    response_model=BarDetail,
    summary="Confirm the menu is still accurate",
    description=(
        _STATUS_RULES
        + "\n\n- Records the time and the caller as `currentMenu.confirmedAt`; confirming again moves it. "
        "Customers keep seeing `publishedAt` as the menu date.\n"
        "- Send the `menuVersion` of the menu that was shown, so a menu the user did not see is not confirmed.\n"
        "- A bar without a menu, or whose menu has no items, is `409 NO_PUBLISHED_MENU`, checked before the "
        "version: `menuVersion: null` there gets `NO_PUBLISHED_MENU`. Sold-out items count as items.\n"
        "- The response is the bar as in `GET /api/bars/{barId}`.\n"
        "- Checks, first failure answering: token, request (`422`), bar (`404`), caller (`403`), then under "
        "the bar row lock: inactive bar (`404`), `NO_PUBLISHED_MENU`, `MENU_OUTDATED`."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
        (403, "`FORBIDDEN`: the caller is neither an operator nor the bar's current owner."),
        AUTH_UNAVAILABLE,
        (404, "`BAR_NOT_FOUND`: no such bar, a malformed id, or an inactive bar."),
        (
            409,
            "`NO_PUBLISHED_MENU`: no menu, or no item on it. `MENU_OUTDATED` (`details.submittedMenuVersion`, "
            "`details.currentMenuVersion`): reload the menu and ask the user to confirm again.",
        ),
        (422, "`VALIDATION_FAILED`: `menuVersion` `MISSING`, or neither an integer nor null."),
    ),
)
def confirm_bar_menu(
    bar_id: BarId,
    body: MenuConfirmRequest,
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BarDetail:
    bar = managed_bar(session, principal, bar_id)
    return confirm_menu(session, principal, bar.id, body.menuVersion)


# ---- photos (spec 3.16) ----

_PHOTO_RULES = (
    "Operator or the bar's owner; inactive bars too. The response is the bar's photos in display order, the "
    "first being the cover, as `photos` of `GET /api/bars/{barId}`, so the app needs no reload. Changes to one "
    "bar's photos are applied one at a time."
)
PhotoId = Annotated[str, Path(alias="photoId", description="Photo id (UUID)")]


@router.post(
    "/{barId}/photos",
    status_code=201,
    response_model=BarPhotosResponse,
    summary="Add a bar photo",
    description=(
        _PHOTO_RULES
        + f"\n\n- One JPEG or PNG in `image`, at most {MAX_PHOTO_BYTES // 2**20} MB and {MAX_LONG_EDGE} px on the "
        "long edge. The type is read from the file content; a declared image type that disagrees is rejected. "
        "The app shrinks and compresses photos to JPEG before uploading.\n"
        "- The server re-encodes the photo as a JPEG without metadata (EXIF orientation applied; EXIF, XMP and "
        f"location removed; transparent areas white) and makes a {THUMBNAIL_LONG_EDGE} px thumbnail. The uploaded "
        "file is not kept.\n"
        f"- The photo goes last; on a bar without photos it becomes the cover. At most {MAX_PHOTOS} per bar.\n"
        "- A file already added to the bar (same bytes) is `409 PHOTO_EXISTS`, so a retried request never adds "
        "a second copy; no `Idempotency-Key` is taken.\n"
        "- Checks, first failure answering: token, request (`422`), bar (`404`), caller (`403`), size (`413`) "
        "and type (`415`), dimensions (`422`), decoding (`415`), then under the bar row lock: the same photo "
        "(`409 PHOTO_EXISTS`), the count (`409 PHOTO_LIMIT_REACHED`)."
    ),
    responses=error_responses(
        *_MANAGER_ERRORS,
        (404, "`BAR_NOT_FOUND`: no such bar or a malformed id."),
        (
            409,
            "`PHOTO_EXISTS`: the bar has this file already, `details.photoId`; `PHOTO_LIMIT_REACHED`: the bar has "
            f"{MAX_PHOTOS} photos, `details.maxPhotos`.",
        ),
        (413, f"`UPLOAD_TOO_LARGE`: over {MAX_PHOTO_BYTES // 2**20} MB; `details.maxImageBytes`."),
        (415, "`UNSUPPORTED_IMAGE_TYPE`: not JPEG or PNG, a declared type that disagrees, or a file that does not decode."),
        (
            422,
            "`VALIDATION_FAILED`: `image` `MISSING` or more than one (`TOO_LONG`), or `IMAGE_DIMENSIONS_TOO_LARGE` "
            f"(long edge over {MAX_LONG_EDGE} px).",
        ),
    ),
)
def add_bar_photo(
    bar_id: BarId,
    image: Annotated[list[UploadedImage], File(description="One JPEG or PNG photo")],
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    storage: ImageStorage = Depends(get_image_storage),
    base_url: str = Depends(get_base_url),
) -> BarPhotosResponse:
    upload = single_upload([ImageUpload(item.filename, item.content_type, item.file) for item in image])
    bar = managed_bar(session, principal, bar_id)
    return BarPhotosResponse(photos=add_photo(session, storage, principal, bar.id, upload, base_url))


@router.delete(
    "/{barId}/photos/{photoId}",
    response_model=BarPhotosResponse,
    summary="Delete a bar photo",
    description=(
        _PHOTO_RULES
        + "\n\nThe photos after it move forward; deleting the cover makes the next photo the cover, and the last "
        "photo can be deleted too. There is no undo. Its URLs answer `404` at once, but devices and caches that "
        "fetched them may keep them for up to a day. A retried request gets `404 PHOTO_NOT_FOUND`: reload the bar."
    ),
    responses=error_responses(
        *_MANAGER_ERRORS,
        (
            404,
            "`BAR_NOT_FOUND`: no such bar or a malformed id; `PHOTO_NOT_FOUND`: not a photo of this bar, already "
            "deleted, or a malformed id, `details.photoId`.",
        ),
    ),
)
def delete_bar_photo(
    photo_id: PhotoId,
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    storage: ImageStorage = Depends(get_image_storage),
    base_url: str = Depends(get_base_url),
    bar: Bar = Depends(require_bar_manager),
) -> BarPhotosResponse:
    return BarPhotosResponse(photos=delete_photo(session, storage, principal, bar.id, photo_id, base_url))


@router.put(
    "/{barId}/photos/order",
    response_model=BarPhotosResponse,
    summary="Reorder the bar photos and choose the cover",
    description=(
        _PHOTO_RULES
        + "\n\nSend every photo of the bar once, in the new order; the first becomes the cover. Ids that differ "
        "from the bar's photos (one added or deleted on another device) change nothing and answer "
        "`409 PHOTOS_OUTDATED` with the current photos in `details.photos`. Sending the same order again gives "
        "the same result.\n\n"
        "Checks, first failure answering: token, request (`422`), bar (`404`), caller (`403`), then under the "
        "bar row lock: the ids (`409`)."
    ),
    responses=error_responses(
        *_MANAGER_ERRORS,
        (404, "`BAR_NOT_FOUND`: no such bar or a malformed id."),
        (409, "`PHOTOS_OUTDATED`: the ids are not the bar's photos; `details.photos` has the current ones."),
        (422, "`VALIDATION_FAILED`: `photoIds` `MISSING` or not UUIDs, or `DUPLICATE_ITEM` (`photoIds[i]`)."),
    ),
)
def reorder_bar_photos(
    bar_id: BarId,
    body: PhotoOrderRequest,
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    base_url: str = Depends(get_base_url),
) -> BarPhotosResponse:
    check_photo_order(body.photoIds)
    bar = managed_bar(session, principal, bar_id)
    return BarPhotosResponse(photos=reorder_photos(session, principal, bar.id, body.photoIds, base_url))
