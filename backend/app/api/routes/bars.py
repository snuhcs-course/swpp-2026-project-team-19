# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9, #13). Reviewed by Haeul Yang.
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.security import get_optional_user, require_operator
from app.db.session import get_session
from app.schemas.bar import BarListResponse
from app.schemas.errors import error_responses
from app.schemas.menu import BarMenuResponse
from app.schemas.menu_import import MenuImportListResponse
from app.services.bar_admin import BarStatusFilter, ImportStatusFilter, list_bars, list_menu_imports
from app.services.bar_menu import get_bar_menu

router = APIRouter(prefix="/api/bars", tags=["bars"])

_OPERATOR_ERRORS = (
    (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
    (403, "`FORBIDDEN`: the caller is not an operator."),
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
    _operator: dict[str, Any] = Depends(require_operator),
) -> BarListResponse:
    return list_bars(session, query=query, status=status, limit=limit, cursor=cursor)


@router.get(
    "/{barId}/menu-imports",
    response_model=MenuImportListResponse,
    summary="A bar's menu imports",
    description=(
        "Operator only. Newest first, to return to an unfinished import after closing the app and to "
        "look back at applied or failed ones. Open one with `GET /api/menu-imports/{menuImportId}`.\n\n"
        "`status=active` means unfinished: `uploaded`, `processing` and `ready_for_review`. "
        "Imports of inactive bars are listed too.\n\n" + _PAGING
    ),
    responses=error_responses(
        *_OPERATOR_ERRORS,
        (404, "`BAR_NOT_FOUND`: no such bar or a malformed id."),
        (
            422,
            "`VALIDATION_FAILED`: `status` not one of the values; `limit` out of range; `cursor` "
            "`INVALID_CURSOR`.",
        ),
    ),
)
def read_bar_menu_imports(
    bar_id: Annotated[str, Path(alias="barId", description="Bar id (UUID)")],
    status: Annotated[
        ImportStatusFilter,
        Query(description="`active`, `uploaded`, `processing`, `ready_for_review`, `applied`, `failed` or `all`"),
    ] = "all",
    limit: Limit = 20,
    cursor: Cursor = None,
    session: Session = Depends(get_session),
    _operator: dict[str, Any] = Depends(require_operator),
) -> MenuImportListResponse:
    return list_menu_imports(session, bar_id, status=status, limit=limit, cursor=cursor)


@router.get(
    "/{barId}/menu",
    response_model=BarMenuResponse,
    summary="Bar info and its current published menu",
    description=(
        "Used by the customer bar detail screen and by operators.\n\n"
        "- Public for active bars; no token is needed.\n"
        "- Inactive bars are returned only to operators. Anonymous callers and customers get "
        "`404 BAR_NOT_FOUND`, the same as for a missing bar.\n"
        "- A bar without a published menu returns `200` with `menuBoardId: null` and `items: []`.\n"
        "- Items and their options are sorted by `sortOrder`."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: an Authorization header was sent but the token is invalid or expired."),
        (404, "`BAR_NOT_FOUND`: no such bar, a malformed id, or an inactive bar for a non-operator."),
    ),
)
def read_bar_menu(
    bar_id: Annotated[str, Path(alias="barId", description="Bar id (UUID)")],
    session: Session = Depends(get_session),
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> BarMenuResponse:
    is_operator = user is not None and user.get("user_type") == "operator"
    return get_bar_menu(session, bar_id, include_inactive=is_operator)
