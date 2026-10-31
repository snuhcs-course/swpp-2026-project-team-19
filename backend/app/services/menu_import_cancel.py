"""Canceling an unfinished menu import (spec 5.7).

The import becomes `canceled` without changing the menu board or the catalog, and its images and
AI records are kept. A run being extracted is ended here, so it does not stay `running` if the
server restarts; the background job sees the cancel at its next commit and stores nothing.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import ImportStatus, MenuImport, PipelineStatus
from app.schemas.menu_import import ImportCanceledResponse
from app.services.menu_import_review import canceled_response, menu_import_not_found
from app.services.menu_import_upload import UNFINISHED_STATUSES


def cancel_menu_import(session: Session, menu_import_id: str) -> ImportCanceledResponse:
    try:
        import_id = UUID(menu_import_id)
    except ValueError:
        raise menu_import_not_found(menu_import_id) from None
    # The same row lock as review-and-apply and the background job, so only one of them wins.
    menu_import = session.get(MenuImport, import_id, with_for_update=True)
    if menu_import is None:
        raise menu_import_not_found(menu_import_id)
    if menu_import.status == ImportStatus.CANCELED:
        # A retried request gets the same response.
        return canceled_response(menu_import)
    if menu_import.status not in UNFINISHED_STATUSES:
        raise ApiError(
            409,
            "INVALID_IMPORT_STATE",
            "이미 끝난 메뉴 등록 작업은 취소할 수 없습니다.",
            details={"menuImportId": str(menu_import.id), "status": menu_import.status.value},
        )
    now = datetime.now(timezone.utc)
    for image in menu_import.images:
        run = image.extraction_run
        if run is not None and run.status == PipelineStatus.RUNNING:
            run.status = PipelineStatus.FAILED
            run.raw_output = {"error": "Canceled", "message": "The import was canceled during extraction"}
            run.completed_at = now
    menu_import.status = ImportStatus.CANCELED
    menu_import.completed_at = now
    session.commit()
    return canceled_response(menu_import)
