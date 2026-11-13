"""Operator menu item checks (API spec 3.18): the list and resolving one. Operators only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy.orm import Session

from app.adapters.storage import ImageStorage
from app.api.deps import get_base_url, get_image_storage
from app.core.security import Principal, require_operator
from app.db.session import get_serializable_session_factory, get_session
from app.schemas.errors import AUTH_UNAVAILABLE, error_responses
from app.schemas.menu_check import (
    CreateAndLink,
    Keep,
    LinkExisting,
    MarkAsOther,
    MenuItemCheckPage,
    MenuItemCheckResponse,
)
from app.services.menu_check_list import StatusFilter, list_checks
from app.services.menu_check_resolve import check_request, find_check_bar, resolve_check
from app.services.serializable import SessionFactory

router = APIRouter(prefix="/api", tags=["menu item checks"])

_UNAUTHENTICATED = (401, "`UNAUTHENTICATED`: missing, invalid or expired token.")
_FORBIDDEN = (403, "`FORBIDDEN`: the caller is not an operator.")


@router.get(
    "/menu-item-checks",
    response_model=MenuItemCheckPage,
    summary="Menu items for operators to check",
    description=(
        "Operator only (spec 3.18.2). Whiskies published without a product, and links an owner's review "
        "changed in a way a person should confirm. Each reason has the review line that raised it. With the "
        "default `status=open` they come oldest first, the order to work through them; `resolved` and "
        "`dismissed` come newest first by when they closed.\n\n"
        "Pages use a cursor: pass `nextCursor` as `cursor` with the same filters; it is null on the last "
        "page. A cursor from other filters is `INVALID_CURSOR`."
    ),
    responses=error_responses(
        _UNAUTHENTICATED,
        _FORBIDDEN,
        (
            422,
            "`VALIDATION_FAILED`: `status` not one of the values (`LITERAL_ERROR`); `barId` not a UUID; "
            "`limit` out of range; `cursor` `INVALID_CURSOR`.",
        ),
        AUTH_UNAVAILABLE,
    ),
)
def read_menu_item_checks(
    check_status: Annotated[
        StatusFilter, Query(alias="status", description="`open`, `resolved` or `dismissed`")
    ] = "open",
    bar_id: Annotated[UUID | None, Query(alias="barId", description="Checks of this bar only")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum number of items per page")] = 100,
    cursor: Annotated[str | None, Query(description="`nextCursor` of the previous page")] = None,
    _operator: Principal = Depends(require_operator),
    session: Session = Depends(get_session),
    storage: ImageStorage = Depends(get_image_storage),
    base_url: str = Depends(get_base_url),
) -> MenuItemCheckPage:
    return list_checks(session, storage, base_url, status=check_status, bar_id=bar_id, limit=limit, cursor=cursor)


@router.post(
    "/menu-item-checks/{checkId}/resolve",
    response_model=MenuItemCheckResponse,
    summary="Resolve a menu item check",
    description=(
        "Operator only (spec 3.18.3). `link_existing` links the item to a catalog product (optionally adding "
        "the board's spelling as an alias), `create_and_link` creates the product (and brand) first, `keep` "
        "confirms the current link, and `mark_as_other` makes an unlinked item a non-whisky menu. Linking may "
        "move the board line to another item of the bar (spec 3.14.1). A link or `mark_as_other` raises "
        "`menuVersion`, not `publishedAt`. The answer is the resolved check."
    ),
    responses=error_responses(
        _UNAUTHENTICATED,
        _FORBIDDEN,
        (404, "`MENU_ITEM_CHECK_NOT_FOUND` (`details.checkId`), or `BAR_NOT_FOUND` for an inactive bar."),
        (
            409,
            "`ACTIVE_IMPORT_EXISTS` (the bar has an unfinished menu import; resolve after it ends); "
            "`INVALID_CHECK_STATE` (already resolved or dismissed; `details.status`); `DUPLICATE_BRAND_FOUND` / "
            "`DUPLICATE_PRODUCT_FOUND` (spec 9.5, without the review fields).",
        ),
        (
            422,
            "`VALIDATION_FAILED`: shape errors, `RESOLUTION_NOT_ALLOWED`, `NOT_NORMALIZABLE`, `PRODUCT_NOT_FOUND`, "
            "`PRODUCT_INACTIVE`, `BRAND_NOT_FOUND`.",
        ),
        (503, "`TEMPORARY_WRITE_CONFLICT`: three serialization failures in a row; send the same request again."),
        AUTH_UNAVAILABLE,
    ),
)
def resolve_menu_item_check(
    check_id: Annotated[str, Path(alias="checkId")],
    body: Annotated[LinkExisting | CreateAndLink | Keep | MarkAsOther, Body(discriminator="resolution")],
    principal: Principal = Depends(require_operator),
    session: Session = Depends(get_session),
    session_factory: SessionFactory = Depends(get_serializable_session_factory),
    storage: ImageStorage = Depends(get_image_storage),
    base_url: str = Depends(get_base_url),
) -> MenuItemCheckResponse:
    check_request(body)
    find_check_bar(session, check_id)
    return resolve_check(session_factory, principal, check_id, body, storage, base_url=base_url)
