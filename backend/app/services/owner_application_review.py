"""Owner applications for operators (API spec, sections 3.11.6 to 3.11.8 and 3.11.13): list, approve,
reject, and check the business registration with NTS again.

Approving and rejecting lock the application row, like the applicant's cancel and photo upload, so
only one of them changes a pending application. Approving an existing_bar application also locks the
bar row and checks for a current owner; the partial unique index on bar_owners backs that up.

When the application has menu photos, approval creates the bar's first menu import from them in the
same transaction (spec 3.11.7). The caller starts processing after the commit, as for an upload.

The NTS recheck holds no lock while NTS answers; it locks the row only to store the answer, so a
decision made meanwhile wins and the answer is dropped.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.business_verification import BusinessVerificationUnavailable, BusinessVerifier
from app.adapters.extraction import MenuExtractor
from app.core.errors import ApiError, validation_failed
from app.core.pagination import decode_cursor, encode_cursor
from app.core.security import Principal
from app.models import (
    Bar,
    BarOwner,
    BarOwnerApplication,
    BarOwnerApplicationMenuImage,
    BarStatus,
    BusinessVerificationResult,
    ImportMode,
    ImportStatus,
    MenuBoard,
    MenuImport,
    OwnerApplicationStatus,
    OwnerApplicationType,
    User,
)
from app.schemas.owner_application import ApproveInput, OwnerApplicationPage, OwnerApplicationResponse, RejectInput
from app.services.image_links import ImageLinks
from app.services.menu_import_upload import UNFINISHED_STATUSES, add_images, fingerprint_from_hashes
from app.services.owner_applications import (
    application_not_found,
    application_responses,
    delete_menu_photo_rows,
    delete_stored_files,
    invalid_application_state,
    user_not_found,
)

StatusFilter = Literal["pending", "approved", "rejected", "canceled", "all"]
TypeFilter = Literal["existing_bar", "new_bar"]
VerificationFilter = Literal["matched", "not_matched", "unavailable"]
CURRENT_OWNER_INDEX = "uq_bar_owners_current_bar_id"


def bar_owner_exists() -> ApiError:
    return ApiError(409, "BAR_OWNER_EXISTS", "이미 업주가 등록된 업장입니다.")


def business_verification_unavailable() -> ApiError:
    return ApiError(
        503,
        "BUSINESS_VERIFICATION_UNAVAILABLE",
        "지금은 사업자등록 정보를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.",
    )


def list_applications(
    session: Session,
    links: ImageLinks,
    *,
    status: StatusFilter = "pending",
    application_type: TypeFilter | None = None,
    verification_result: VerificationFilter | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> OwnerApplicationPage:
    """Applications matching the filters. Pending ones come oldest first, the order an operator
    works through them; the other filters show the newest first. The cursor carries the filters, so a
    cursor from other filters is `INVALID_CURSOR` instead of silently skipping rows."""
    filters = [status, application_type, verification_result]
    oldest_first = status == "pending"
    stmt = select(BarOwnerApplication)
    if status != "all":
        stmt = stmt.where(BarOwnerApplication.status == OwnerApplicationStatus(status))
    if application_type is not None:
        stmt = stmt.where(BarOwnerApplication.application_type == OwnerApplicationType(application_type))
    if verification_result is not None:
        stmt = stmt.where(
            BarOwnerApplication.business_verification_result == BusinessVerificationResult(verification_result)
        )
    key = tuple_(BarOwnerApplication.created_at, BarOwnerApplication.id)
    if cursor is not None:
        after = tuple_(*decode_cursor(cursor, lambda values: _cursor_key(values, filters)))
        stmt = stmt.where(key > after if oldest_first else key < after)
    if oldest_first:
        stmt = stmt.order_by(BarOwnerApplication.created_at, BarOwnerApplication.id)
    else:
        stmt = stmt.order_by(BarOwnerApplication.created_at.desc(), BarOwnerApplication.id.desc())
    applications = list(session.scalars(stmt.limit(limit + 1)))
    page, more = applications[:limit], len(applications) > limit
    last = page[-1] if page else None
    return OwnerApplicationPage(
        items=application_responses(session, page, links, show_verification=True),
        nextCursor=encode_cursor([*filters, last.created_at.isoformat(), str(last.id)]) if more else None,
    )


def _cursor_key(values: list, filters: list) -> tuple[datetime, UUID]:
    *stored_filters, created_at, application_id = values
    if stored_filters != filters or not isinstance(created_at, str) or not isinstance(application_id, str):
        raise ValueError("cursor from other filters")
    return datetime.fromisoformat(created_at), UUID(application_id)


def approve_application(
    session: Session,
    principal: Principal,
    application_id: str,
    request: ApproveInput | None,
    *,
    extractor: MenuExtractor,
    now: datetime,
) -> tuple[BarOwnerApplication, MenuImport | None]:
    """Approve a pending application in one transaction: create the bar for new_bar, the ownership,
    and the first menu import when there are photos and the bar has no unfinished import. Returns the
    application and the import, if one was created, for the caller to start processing."""
    reviewer = _reviewer(session, principal)
    application = _pending_application(session, application_id)
    confirmed = request.bar if request is not None else None
    if application.application_type == OwnerApplicationType.EXISTING_BAR:
        if confirmed is not None:
            raise validation_failed("bar", "EXTRA_FORBIDDEN", "기존 업장 신청에는 업장 정보를 보내지 않습니다.")
        bar = session.scalar(select(Bar).where(Bar.id == application.bar_id).with_for_update())
        if session.scalar(select(BarOwner.id).where(BarOwner.bar_id == bar.id, BarOwner.revoked_at.is_(None))):
            raise bar_owner_exists()
    else:
        if confirmed is None:
            raise validation_failed("bar", "MISSING", "새 업장의 정보와 좌표를 입력해 주세요.")
        bar = Bar(
            name=confirmed.name,
            address=confirmed.address,
            latitude=Decimal(str(confirmed.latitude)),
            longitude=Decimal(str(confirmed.longitude)),
            phone=confirmed.phone,
            status=BarStatus.ACTIVE,
        )
        session.add(bar)
        session.flush()
        application.bar_id = bar.id

    application.status = OwnerApplicationStatus.APPROVED
    application.reviewed_by_user_id = reviewer.id
    application.reviewed_at = now
    try:
        session.add(BarOwner(bar_id=bar.id, user_id=application.applicant_user_id, application_id=application.id))
        # The owner row may be flushed here or by a query in _initial_import, so both are covered.
        menu_import = _initial_import(session, application, bar.id, extractor)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if getattr(error.orig.diag, "constraint_name", None) != CURRENT_OWNER_INDEX:
            raise
        # Another approval made someone the bar's owner after the check above.
        raise bar_owner_exists() from None
    return application, menu_import


def reject_application(
    session: Session,
    principal: Principal,
    application_id: str,
    request: RejectInput,
    *,
    links: ImageLinks,
    now: datetime,
) -> OwnerApplicationResponse:
    """Reject a pending application with a reason shown to the applicant, and delete its menu photos."""
    reviewer = _reviewer(session, principal)
    application = _pending_application(session, application_id)
    application.status = OwnerApplicationStatus.REJECTED
    application.rejection_reason = request.reason
    application.reviewed_by_user_id = reviewer.id
    application.reviewed_at = now
    removed = delete_menu_photo_rows(session, application.id)
    session.commit()
    delete_stored_files(links.storage, removed)
    return application_responses(session, [application], links, show_verification=True)[0]


def recheck_business(
    session: Session, application_id: str, *, verifier: BusinessVerifier | None, now: datetime
) -> BarOwnerApplication:
    """Check a pending application's stored values with NTS again (spec 3.11.13) and store the answer;
    the application's status stays. Not counted against the daily limit of 3.11.14. When NTS cannot
    answer, or the server has no NTS key, the stored result and `checkedAt` stay as they were."""
    application = _pending_application(session, application_id, lock=False)
    if verifier is None:
        raise business_verification_unavailable()
    number, name, opened = (
        application.business_registration_number,
        application.representative_name,
        application.opening_date,
    )
    # End the read transaction so the connection goes back to the pool while NTS answers (up to two
    # 5 s tries). The row is locked and checked again afterwards: an approval, rejection or cancel
    # made meanwhile answers 409 and the result is not stored.
    session.commit()
    try:
        check = verifier.verify(number, name, opened)
    except BusinessVerificationUnavailable:
        raise business_verification_unavailable() from None
    application = _pending_application(session, application_id)
    if check.matched:
        application.business_verification_result = BusinessVerificationResult.MATCHED
        application.business_status = check.business_status
    else:
        application.business_verification_result = BusinessVerificationResult.NOT_MATCHED
        application.business_status = None
    application.business_checked_at = now
    session.commit()
    return application


def _reviewer(session: Session, principal: Principal) -> User:
    """The operator's users row, recorded as the reviewer. Only a temporary-login operator can lack one."""
    reviewer = session.scalar(select(User).where(User.auth_subject == principal.subject))
    if reviewer is None:
        raise user_not_found()
    return reviewer


def _pending_application(session: Session, application_id: str, *, lock: bool = True) -> BarOwnerApplication:
    try:
        application = session.get(BarOwnerApplication, UUID(application_id), with_for_update=lock)
    except ValueError:
        application = None
    if application is None:
        raise application_not_found()
    if application.status != OwnerApplicationStatus.PENDING:
        raise invalid_application_state(application)
    return application


def _initial_import(
    session: Session, application: BarOwnerApplication, bar_id: UUID, extractor: MenuExtractor
) -> MenuImport | None:
    """The first menu import from the application's photos, or None without photos or when the bar
    already has an unfinished import (for an existing bar its row is locked by the caller)."""
    photos = list(
        session.scalars(
            select(BarOwnerApplicationMenuImage)
            .where(BarOwnerApplicationMenuImage.application_id == application.id)
            .order_by(BarOwnerApplicationMenuImage.image_order)
        )
    )
    if not photos:
        return None
    unfinished = select(MenuImport.id).where(MenuImport.bar_id == bar_id, MenuImport.status.in_(UNFINISHED_STATUSES))
    if session.scalar(unfinished) is not None:
        return None
    has_menu = session.scalar(select(MenuBoard.id).where(MenuBoard.bar_id == bar_id)) is not None
    mode = ImportMode.PARTIAL_UPDATE if has_menu else ImportMode.FULL_REPLACE
    menu_import = MenuImport(
        # One approval per application, so this key never collides (docs/schema_guide.md 8.1).
        idempotency_key=f"owner-application:{application.id}",
        request_fingerprint=fingerprint_from_hashes(bar_id, mode, None, [photo.content_sha256 for photo in photos]),
        bar_id=bar_id,
        mode=mode,
        status=ImportStatus.UPLOADED,
    )
    session.add(menu_import)
    session.flush()
    add_images(session, menu_import.id, [(photo.storage_key, photo.original_filename) for photo in photos], extractor)
    return menu_import
