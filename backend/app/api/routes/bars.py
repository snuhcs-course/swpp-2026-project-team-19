from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.permissions import require_bar_manager
from app.core.security import Principal, get_current_user, get_optional_user, require_operator
from app.db.session import get_session
from app.models import Bar
from app.schemas.bar import BarDetail, BarListResponse, BarUpdateInput
from app.schemas.errors import AUTH_UNAVAILABLE, error_responses
from app.schemas.menu import BarMenuResponse
from app.schemas.menu_import import MenuImportListResponse
from app.services.bar_access import can_manage_bar, is_operator
from app.services.bar_admin import BarStatusFilter, ImportStatusFilter, list_bars, list_menu_imports
from app.services.bar_detail import get_bar_detail, update_bar
from app.services.bar_menu import get_bar_menu

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
        "- A bar without a published menu returns `200` with `menuBoardId: null` and `items: []`. A menu "
        "whose items were all taken down keeps `menuBoardId` and `publishedAt`, with `items: []`.\n"
        "- `phone`, `optionLabel` and `pourMl` are null when missing. Coordinates are WGS84 and never null.\n"
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
        session, bar_id, may_see_inactive=lambda bar: user is not None and can_manage_bar(session, user, bar.id)
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
