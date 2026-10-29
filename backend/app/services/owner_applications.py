"""Owner applications for applicants (API spec, sections 3.11.2 to 3.11.5).

Applying checks, in the spec's order, the fields, the caller's users row, the claimed bar and its
owner, the caller's pending applications, and last the NTS business check, which calls an external
API. A mismatch creates nothing; a check that cannot be made stores `unavailable`. The partial
unique indexes catch a duplicate that a concurrent request created after the pending check.
"""

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.business_verification import BusinessVerificationUnavailable, BusinessVerifier
from app.core.errors import ApiError, validation_failed
from app.core.security import Principal, user_type_of
from app.models import (
    Bar,
    BarOwner,
    BarOwnerApplication,
    BarStatus,
    BusinessStatus,
    BusinessVerificationResult,
    OwnerApplicationStatus,
    OwnerApplicationType,
    User,
)
from app.schemas.owner_application import (
    Applicant,
    ApplicationBar,
    BusinessVerification,
    ExistingBarApplicationInput,
    OwnerApplicationInput,
    OwnerApplicationResponse,
    ProposedBar,
)
from app.services.bar_menu import bar_not_found
from app.services.request_limits import BUSINESS_VERIFICATION, DailyRequestLimiter, acquire_or_raise, kst_date


def user_not_found() -> ApiError:
    return ApiError(404, "USER_NOT_FOUND", "사용자 정보가 없습니다. 다시 시도해 주세요.")


def application_not_found() -> ApiError:
    return ApiError(404, "OWNER_APPLICATION_NOT_FOUND", "업주 신청을 찾을 수 없습니다.")


def submit_application(
    session: Session,
    principal: Principal,
    request: OwnerApplicationInput,
    *,
    verifier: BusinessVerifier | None,
    limiter: DailyRequestLimiter,
    now: datetime,
) -> BarOwnerApplication:
    if request.openingDate > kst_date(now):
        raise validation_failed("openingDate", "DATE_IN_FUTURE", "개업일자는 오늘 이후일 수 없습니다.")
    applicant = _caller(session, principal)
    if applicant is None:
        raise user_not_found()
    applicant_id = applicant.id
    bar_id = _claimable_bar_id(session, request)
    if (existing := _pending_duplicate(session, applicant_id, request, bar_id)) is not None:
        raise _application_exists(existing)

    result, business_status = BusinessVerificationResult.UNAVAILABLE, None
    if verifier is not None:
        # End the read transaction so the connection goes back to the pool while NTS answers (up to
        # two 5 s tries). The bar or its owner may change meanwhile, so they are checked again; a
        # duplicate application created meanwhile is caught by the partial unique index below.
        session.commit()
        result, business_status = _check_business(principal, request, verifier, limiter, now)
        _claimable_bar_id(session, request)
    application = BarOwnerApplication(
        applicant_user_id=applicant_id,
        application_type=OwnerApplicationType(request.applicationType),
        bar_id=bar_id,
        business_registration_number=request.businessRegistrationNumber,
        representative_name=request.representativeName,
        opening_date=request.openingDate,
        business_verification_result=result,
        business_status=business_status,
        business_checked_at=now,
        contact_phone=request.contactPhone,
        applicant_note=request.applicantNote,
    )
    if not isinstance(request, ExistingBarApplicationInput):
        application.proposed_bar_name = request.proposedBar.name
        application.proposed_address = request.proposedBar.address
        application.proposed_phone = request.proposedBar.phone or None
    try:
        with session.begin_nested():
            session.add(application)
    except IntegrityError:
        # A concurrent request created the same pending application after the check above. The
        # NTS check stays counted, as the spec says.
        existing = _pending_duplicate(session, applicant_id, request, bar_id)
        if existing is None:
            raise
        raise _application_exists(existing) from None
    session.commit()
    return application


def list_my_applications(session: Session, principal: Principal) -> list[OwnerApplicationResponse]:
    """The caller's applications, newest first; empty without a users row. Never shows the check result."""
    applicant = _caller(session, principal)
    if applicant is None:
        return []
    applications = session.scalars(
        select(BarOwnerApplication)
        .where(BarOwnerApplication.applicant_user_id == applicant.id)
        .order_by(BarOwnerApplication.created_at.desc(), BarOwnerApplication.id.desc())
    ).all()
    return application_responses(session, applications, show_verification=False)


def get_application(session: Session, principal: Principal, application_id: str) -> OwnerApplicationResponse:
    """The applicant's own application, or any application for an operator. Anything else is 404, so
    the caller cannot tell whether someone else's application exists."""
    application = _find(session, application_id)
    operator = user_type_of(principal, session) == "operator"
    if application is None or not (operator or _is_applicant(session, principal, application)):
        raise application_not_found()
    return application_responses(session, [application], show_verification=operator)[0]


def cancel_application(session: Session, principal: Principal, application_id: str) -> OwnerApplicationResponse:
    """Cancel the caller's own pending application. Operators may cancel only their own too; anything
    else is 404 like a missing one. The row is locked so that a concurrent approval or rejection
    (3.11.7, 3.11.8; they must lock it too) and this cancel cannot both succeed."""
    application = _find(session, application_id, lock=True)
    if application is None or not _is_applicant(session, principal, application):
        raise application_not_found()
    if application.status != OwnerApplicationStatus.PENDING:
        raise invalid_application_state(application)
    application.status = OwnerApplicationStatus.CANCELED
    session.commit()
    operator = user_type_of(principal, session) == "operator"
    return application_responses(session, [application], show_verification=operator)[0]


def invalid_application_state(application: BarOwnerApplication) -> ApiError:
    return ApiError(
        409,
        "INVALID_APPLICATION_STATE",
        "이미 처리된 업주 신청입니다.",
        details={"status": application.status.value},
    )


def application_responses(
    session: Session, applications: Iterable[BarOwnerApplication], *, show_verification: bool
) -> list[OwnerApplicationResponse]:
    """`OwnerApplication` bodies, loading the applicants and bars in one query each."""
    applications = list(applications)
    user_ids = {application.applicant_user_id for application in applications}
    bar_ids = {application.bar_id for application in applications if application.bar_id is not None}
    users = {user.id: user for user in session.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    bars = {bar.id: bar for bar in session.scalars(select(Bar).where(Bar.id.in_(bar_ids)))} if bar_ids else {}
    return [_response(application, users, bars, show_verification) for application in applications]


def _response(
    application: BarOwnerApplication, users: dict[UUID, User], bars: dict[UUID, Bar], show_verification: bool
) -> OwnerApplicationResponse:
    applicant = users[application.applicant_user_id]
    bar = bars.get(application.bar_id) if application.bar_id is not None else None
    return OwnerApplicationResponse(
        applicationId=application.id,
        applicationType=application.application_type.value,
        status=application.status.value,
        applicant=Applicant(userId=applicant.id, email=applicant.email, displayName=applicant.display_name),
        bar=ApplicationBar(barId=bar.id, name=bar.name, address=bar.address) if bar is not None else None,
        proposedBar=(
            ProposedBar(
                name=application.proposed_bar_name,
                address=application.proposed_address,
                phone=application.proposed_phone,
            )
            if application.application_type == OwnerApplicationType.NEW_BAR
            else None
        ),
        businessRegistrationNumber=application.business_registration_number,
        representativeName=application.representative_name,
        openingDate=application.opening_date,
        businessStatus=application.business_status.value if application.business_status is not None else None,
        businessVerification=(
            BusinessVerification(
                result=application.business_verification_result.value, checkedAt=application.business_checked_at
            )
            if show_verification
            else None
        ),
        contactPhone=application.contact_phone,
        applicantNote=application.applicant_note,
        rejectionReason=application.rejection_reason,
        reviewedAt=application.reviewed_at,
        createdAt=application.created_at,
        updatedAt=application.updated_at,
    )


def _caller(session: Session, principal: Principal) -> User | None:
    return session.scalar(select(User).where(User.auth_subject == principal.subject))


def _is_applicant(session: Session, principal: Principal, application: BarOwnerApplication) -> bool:
    caller = _caller(session, principal)
    return caller is not None and caller.id == application.applicant_user_id


def _find(session: Session, application_id: str, *, lock: bool = False) -> BarOwnerApplication | None:
    try:
        return session.get(BarOwnerApplication, UUID(application_id), with_for_update=lock)
    except ValueError:
        return None


def _active_bar(session: Session, bar_id: str) -> Bar:
    try:
        bar = session.get(Bar, UUID(bar_id))
    except ValueError:
        bar = None
    if bar is None or bar.status != BarStatus.ACTIVE:
        raise bar_not_found(bar_id)
    return bar


def _claimable_bar_id(session: Session, request: OwnerApplicationInput) -> UUID | None:
    """The claimed bar of an existing_bar application, if it is active and has no current owner."""
    if not isinstance(request, ExistingBarApplicationInput):
        return None
    bar = _active_bar(session, request.barId)
    if session.scalar(select(BarOwner.id).where(BarOwner.bar_id == bar.id, BarOwner.revoked_at.is_(None))):
        raise ApiError(409, "BAR_OWNER_EXISTS", "이미 업주가 등록된 업장입니다.")
    return bar.id


def _pending_duplicate(
    session: Session, applicant_id: UUID, request: OwnerApplicationInput, bar_id: UUID | None
) -> BarOwnerApplication | None:
    """The caller's pending application for the same bar (existing_bar) or the same business number (new_bar)."""
    stmt = select(BarOwnerApplication).where(
        BarOwnerApplication.applicant_user_id == applicant_id,
        BarOwnerApplication.status == OwnerApplicationStatus.PENDING,
        BarOwnerApplication.application_type == OwnerApplicationType(request.applicationType),
    )
    if bar_id is not None:
        stmt = stmt.where(BarOwnerApplication.bar_id == bar_id)
    else:
        stmt = stmt.where(BarOwnerApplication.business_registration_number == request.businessRegistrationNumber)
    return session.scalar(stmt)


def _application_exists(existing: BarOwnerApplication) -> ApiError:
    return ApiError(
        409,
        "OWNER_APPLICATION_EXISTS",
        "이미 처리 중인 업주 신청이 있습니다.",
        details={"applicationId": str(existing.id)},
    )


def _check_business(
    principal: Principal,
    request: OwnerApplicationInput,
    verifier: BusinessVerifier,
    limiter: DailyRequestLimiter,
    now: datetime,
) -> tuple[BusinessVerificationResult, BusinessStatus | None]:
    """The NTS check of spec 3.11.2, counted against today's limit. Without a verifier nothing is
    called or counted, and the caller stores `unavailable`."""
    acquire_or_raise(limiter, principal.subject, BUSINESS_VERIFICATION, now)
    try:
        check = verifier.verify(request.businessRegistrationNumber, request.representativeName, request.openingDate)
    except BusinessVerificationUnavailable:
        return BusinessVerificationResult.UNAVAILABLE, None
    if not check.matched:
        raise ApiError(
            422,
            "BUSINESS_VERIFICATION_FAILED",
            "사업자등록번호, 대표자명, 개업일자가 사업자등록증과 같은지 확인해 주세요.",
        )
    return BusinessVerificationResult.MATCHED, check.business_status
