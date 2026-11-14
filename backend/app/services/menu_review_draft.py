"""Saving the reviewer's unfinished input (API spec 5.9).

The draft does not change the menu board, so the bar row is not locked: only the import row, which
review-and-apply and cancel lock too, so a save that comes after either of them sees the new status.
Two editors are kept from overwriting each other by the draft version a save must send.
"""

import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import Principal
from app.models import ImportStatus, MenuImport
from app.schemas.review_draft import MAX_DRAFT_BYTES, ReviewDraft, ReviewDraftRequest, ReviewDraftSavedResponse
from app.services.request_limits import rfc3339_utc
from app.services.users import caller_user_id


def draft_too_large() -> ApiError:
    return ApiError(
        413,
        "REVIEW_DRAFT_TOO_LARGE",
        "검수 초안이 너무 큽니다.",
        details={"maxBytes": MAX_DRAFT_BYTES},
    )


def check_draft_size(request: ReviewDraftRequest) -> None:
    """413 when the content written as JSON is over 256 KB; checked with the request's shape."""
    size = len(json.dumps(request.content, ensure_ascii=False, separators=(",", ":")).encode())
    if size > MAX_DRAFT_BYTES:
        raise draft_too_large()


def save_review_draft(
    session: Session, principal: Principal, import_id: UUID, request: ReviewDraftRequest
) -> ReviewDraftSavedResponse:
    # The route has checked that the import exists and that the caller manages its bar.
    menu_import = session.get(MenuImport, import_id, with_for_update=True)
    if menu_import.status != ImportStatus.READY_FOR_REVIEW:
        raise ApiError(
            409,
            "INVALID_IMPORT_STATE",
            "검수 중인 작업에만 초안을 저장할 수 있습니다.",
            details={"menuImportId": str(menu_import.id), "status": menu_import.status.value},
        )
    if request.draftVersion != menu_import.review_draft_version:
        raise ApiError(
            409,
            "REVIEW_DRAFT_OUTDATED",
            "다른 곳에서 먼저 저장한 초안이 있습니다. 최신 내용을 다시 확인해 주세요.",
            details={
                "currentDraftVersion": menu_import.review_draft_version,
                "savedAt": rfc3339_utc(menu_import.review_draft_saved_at)
                if menu_import.review_draft_saved_at
                else None,
                "reviewUrl": f"/api/menu-imports/{menu_import.id}",
            },
        )
    saved_by = caller_user_id(session, principal)
    # The response is built from this save's own values: after the commit the row is read again, and
    # another editor's save could already be there.
    response = ReviewDraftSavedResponse(
        menuImportId=menu_import.id,
        draftVersion=menu_import.review_draft_version + 1,
        savedAt=session.scalar(select(func.clock_timestamp())),
    )
    menu_import.review_draft = request.content
    menu_import.review_draft_review_version = request.reviewVersion
    menu_import.review_draft_version = response.draftVersion
    menu_import.review_draft_saved_by_user_id = saved_by
    menu_import.review_draft_saved_at = response.savedAt
    session.commit()
    return response


def review_draft_of(menu_import: MenuImport) -> ReviewDraft | None:
    """The saved draft for the review data (spec 5.4), or None."""
    if menu_import.review_draft is None:
        return None
    return ReviewDraft(
        draftVersion=menu_import.review_draft_version,
        reviewVersion=menu_import.review_draft_review_version,
        savedAt=menu_import.review_draft_saved_at,
        content=menu_import.review_draft,
    )


def clear_review_draft(menu_import: MenuImport) -> None:
    """Drop the draft once the import is applied or canceled; its version stays (spec 5.9)."""
    menu_import.review_draft = None
    menu_import.review_draft_review_version = None
