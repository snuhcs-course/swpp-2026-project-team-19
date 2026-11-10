"""Owner applications for applicants (API spec, sections 3.11.2 to 3.11.5, 3.11.15 and 3.11.17).

Applying checks, in the spec's order, the fields, the caller's users row, the claimed bar and its
owner, the caller's pending applications, and last the NTS business check, which calls an external
API unless the caller matched the same values in the check before applying (business_check.py). A
mismatch creates nothing; a check that cannot be made stores `unavailable`. The partial
unique indexes catch a duplicate that a concurrent request created after the pending check.

Menu photos, and the cover photo of a new_bar application, are attached after the application exists
and replaced as a whole on each upload.
Storage and the database share no transaction, so new files are stored under fresh keys before
the rows change and the files they replace are deleted only after the commit.
"""

import hashlib
import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.business_verification import BusinessVerifier
from app.adapters.storage import ImageStorage
from app.core.business_number_crypto import get_business_number_cipher
from app.core.errors import ApiError
from app.core.security import Principal, user_type_of
from app.models import (
    Bar,
    BarOwner,
    BarOwnerApplication,
    BarOwnerApplicationMenuImage,
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
    ApplicationCoverPhoto,
    ApplicationMenuPhoto,
    ApplicationWarning,
    BusinessNumberSharedWarning,
    BusinessVerification,
    ExistingBarApplicationInput,
    OwnerApplicationInput,
    OwnerApplicationResponse,
    ProposedBar,
    SharedNumberApplication,
    SharedNumberDetails,
)
from app.services.bar_menu import bar_not_found
from app.services.bar_photo_image import process_photo
from app.services.bar_photos import PHOTO_CONTENT_TYPE
from app.services.image_links import ImageLinks
from app.services.menu_import_upload import ImageUpload, check_images
from app.services.business_check import RecentBusinessChecks, call_nts, check_opening_date
from app.services.request_limits import DailyRequestLimiter
from app.services.users import user_not_found

logger = logging.getLogger(__name__)


def application_not_found() -> ApiError:
    return ApiError(404, "OWNER_APPLICATION_NOT_FOUND", "업주 신청을 찾을 수 없습니다.")


def submit_application(
    session: Session,
    principal: Principal,
    request: OwnerApplicationInput,
    *,
    verifier: BusinessVerifier | None,
    limiter: DailyRequestLimiter,
    recent: RecentBusinessChecks,
    now: datetime,
) -> BarOwnerApplication:
    check_opening_date(request, now)
    applicant = _caller(session, principal)
    if applicant is None:
        raise user_not_found()
    applicant_id = applicant.id
    bar_id = _claimable_bar_id(session, request)
    if (existing := _pending_duplicate(session, applicant_id, request, bar_id)) is not None:
        raise _application_exists(existing)

    result, business_status, checked_at = BusinessVerificationResult.UNAVAILABLE, None, now
    if (match := recent.recall(principal.subject, request, now)) is not None:
        # A match from the check before applying (3.11.16): NTS is not asked again or counted.
        result, business_status = BusinessVerificationResult.MATCHED, match.business_status
        checked_at = match.checked_at
    elif verifier is not None:
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
        business_checked_at=checked_at,
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


def list_my_applications(
    session: Session, principal: Principal, links: ImageLinks
) -> list[OwnerApplicationResponse]:
    """The caller's applications, newest first; empty without a users row. Never shows the check result."""
    applicant = _caller(session, principal)
    if applicant is None:
        return []
    applications = session.scalars(
        select(BarOwnerApplication)
        .where(BarOwnerApplication.applicant_user_id == applicant.id)
        .order_by(BarOwnerApplication.created_at.desc(), BarOwnerApplication.id.desc())
    ).all()
    return application_responses(session, applications, links, show_verification=False)


def get_application(
    session: Session, principal: Principal, application_id: str, links: ImageLinks
) -> OwnerApplicationResponse:
    """The applicant's own application, or any application for an operator. Anything else is 404, so
    the caller cannot tell whether someone else's application exists."""
    application = _find(session, application_id)
    operator = user_type_of(principal, session) == "operator"
    if application is None or not (operator or _is_applicant(session, principal, application)):
        raise application_not_found()
    return application_responses(session, [application], links, show_verification=operator)[0]


def cancel_application(
    session: Session, principal: Principal, application_id: str, links: ImageLinks
) -> OwnerApplicationResponse:
    """Cancel the caller's own pending application and delete its menu photos. Operators may cancel
    only their own too; anything else is 404 like a missing one. The row is locked so that a
    concurrent approval, rejection or photo upload (3.11.7, 3.11.8, 3.11.15; they lock it too) and
    this cancel cannot both succeed."""
    application = _find(session, application_id, lock=True)
    if application is None or not _is_applicant(session, principal, application):
        raise application_not_found()
    if application.status != OwnerApplicationStatus.PENDING:
        raise invalid_application_state(application)
    # The cover photo first: only a pending application may hold one, and the query below flushes.
    removed = clear_cover_photo(application) + delete_menu_photo_rows(session, application.id)
    application.status = OwnerApplicationStatus.CANCELED
    session.commit()
    delete_stored_files(links.storage, removed)
    operator = user_type_of(principal, session) == "operator"
    return application_responses(session, [application], links, show_verification=operator)[0]


def replace_menu_photos(
    session: Session, principal: Principal, application_id: str, uploads: list[ImageUpload], links: ImageLinks
) -> OwnerApplicationResponse:
    """Replace the menu photos of the caller's own pending application (spec 3.11.15).

    Checks the application and its status before reading the photos, as the spec orders. The photos
    are stored without holding the row lock; the lock is taken only to check the status again and
    swap the rows, so an approval or cancel that won meanwhile makes this upload fail cleanly.
    """
    application = _find(session, application_id)
    if application is None or not _is_applicant(session, principal, application):
        raise application_not_found()
    if application.status != OwnerApplicationStatus.PENDING:
        raise invalid_application_state(application)
    images = check_images(uploads)
    # End the read transaction so the connection goes back to the pool while the files are stored.
    session.commit()

    prefix = f"owner-applications/{application.id}/{uuid4()}"
    rows = [
        BarOwnerApplicationMenuImage(
            application_id=application.id,
            storage_key=f"{prefix}/page-{order}.{image.extension}",
            original_filename=image.filename,
            image_order=order,
            content_sha256=hashlib.sha256(image.data).hexdigest(),
        )
        for order, image in enumerate(images, start=1)
    ]
    saved: list[str] = []
    try:
        for row, image in zip(rows, images):
            links.storage.save(row.storage_key, image.data, image.content_type)
            saved.append(row.storage_key)
        application = _find(session, application_id, lock=True)
        if application.status != OwnerApplicationStatus.PENDING:
            raise invalid_application_state(application)
        removed = delete_menu_photo_rows(session, application.id)
        # Flush the deletes first so the new rows can take the same image orders.
        session.flush()
        session.add_all(rows)
        session.commit()
    except Exception:
        session.rollback()
        delete_stored_files(links.storage, saved)
        raise
    delete_stored_files(links.storage, removed)
    operator = user_type_of(principal, session) == "operator"
    return application_responses(session, [application], links, show_verification=operator)[0]


def replace_cover_photo(
    session: Session, principal: Principal, application_id: str, upload: ImageUpload, links: ImageLinks
) -> OwnerApplicationResponse:
    """Store the cover photo of the caller's own pending new_bar application, replacing any (spec 3.11.17).

    The application, its type and its status are checked before the photo, as the spec orders. The photo
    is re-encoded like a bar photo (3.16.2) and stored without holding the row lock, as for menu photos.
    """
    application = _cover_photo_application(session, principal, application_id)
    processed = process_photo(upload)
    # End the read transaction so the connection goes back to the pool while the files are stored.
    session.commit()

    prefix = f"owner-applications/{application.id}/cover/{uuid4()}"
    image_key, thumbnail_key = f"{prefix}.jpg", f"{prefix}-thumb.jpg"
    saved: list[str] = []
    try:
        for key, data in ((image_key, processed.image), (thumbnail_key, processed.thumbnail)):
            # Before the save: a save that fails may still have written the file.
            saved.append(key)
            links.storage.save(key, data, PHOTO_CONTENT_TYPE)
        application = _cover_photo_application(session, principal, application_id, lock=True)
        removed = clear_cover_photo(application)
        application.cover_photo_storage_key = image_key
        application.cover_photo_thumbnail_storage_key = thumbnail_key
        application.cover_photo_sha256 = processed.content_sha256
        session.commit()
    except Exception:
        session.rollback()
        delete_stored_files(links.storage, saved)
        raise
    delete_stored_files(links.storage, removed)
    return _own_response(session, principal, application, links)


def delete_cover_photo(
    session: Session, principal: Principal, application_id: str, links: ImageLinks
) -> OwnerApplicationResponse:
    """Remove the cover photo of the caller's own pending new_bar application; nothing to remove is fine."""
    application = _cover_photo_application(session, principal, application_id, lock=True)
    removed = clear_cover_photo(application)
    session.commit()
    delete_stored_files(links.storage, removed)
    return _own_response(session, principal, application, links)


def clear_cover_photo(application: BarOwnerApplication) -> list[str]:
    """Empty the application's cover photo columns and return the storage keys they held. The caller
    deletes the files after committing, or hands them to the bar photo it creates on approval."""
    keys = [
        key
        for key in (application.cover_photo_storage_key, application.cover_photo_thumbnail_storage_key)
        if key is not None
    ]
    application.cover_photo_storage_key = None
    application.cover_photo_thumbnail_storage_key = None
    application.cover_photo_sha256 = None
    return keys


def delete_menu_photo_rows(session: Session, application_id: UUID) -> list[str]:
    """Delete the application's menu photo rows and return their storage keys. The caller deletes
    the files with `delete_stored_files` after committing, so a rollback never loses a photo."""
    images = session.scalars(
        select(BarOwnerApplicationMenuImage).where(BarOwnerApplicationMenuImage.application_id == application_id)
    ).all()
    for image in images:
        session.delete(image)
    return [image.storage_key for image in images]


def delete_stored_files(storage: ImageStorage, keys: Iterable[str]) -> None:
    for key in keys:
        try:
            storage.delete(key)
        except Exception:
            # The database is already right; an orphaned object is only wasted space.
            logger.warning("Could not delete stored file %s", key, exc_info=True)


def invalid_application_state(application: BarOwnerApplication) -> ApiError:
    return ApiError(
        409,
        "INVALID_APPLICATION_STATE",
        "이미 처리된 업주 신청입니다.",
        details={"status": application.status.value},
    )


def application_responses(
    session: Session, applications: Iterable[BarOwnerApplication], links: ImageLinks, *, show_verification: bool
) -> list[OwnerApplicationResponse]:
    """`OwnerApplication` bodies, loading the applicants, bars and menu photos in one query each. The operator
    view (`show_verification`) also gets the warnings, with one more query for the shared business numbers."""
    applications = list(applications)
    application_ids = [application.id for application in applications]
    user_ids = {application.applicant_user_id for application in applications}
    sharing = _sharing_applications(session, applications) if show_verification else []
    bar_ids = {application.bar_id for application in [*applications, *sharing] if application.bar_id is not None}
    users = {user.id: user for user in session.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    bars = {bar.id: bar for bar in session.scalars(select(Bar).where(Bar.id.in_(bar_ids)))} if bar_ids else {}
    photos: dict[UUID, list[ApplicationMenuPhoto]] = defaultdict(list)
    if application_ids:
        for image in session.scalars(
            select(BarOwnerApplicationMenuImage)
            .where(BarOwnerApplicationMenuImage.application_id.in_(application_ids))
            .order_by(BarOwnerApplicationMenuImage.application_id, BarOwnerApplicationMenuImage.image_order)
        ):
            url, expires_at = links.url(image.storage_key)
            photos[image.application_id].append(
                ApplicationMenuPhoto(imageOrder=image.image_order, imageUrl=url, imageUrlExpiresAt=expires_at)
            )
    by_number: dict[bytes, list[BarOwnerApplication]] = defaultdict(list)
    for other in sharing:
        by_number[bytes(other.business_registration_number_hmac)].append(other)
    return [
        _response(
            application,
            users,
            bars,
            photos[application.id],
            links,
            show_verification,
            warnings=_warnings(application, by_number, bars) if show_verification else None,
        )
        for application in applications
    ]


SHARED_STATUSES = (OwnerApplicationStatus.PENDING, OwnerApplicationStatus.APPROVED)


def _sharing_applications(session: Session, applications: list[BarOwnerApplication]) -> list[BarOwnerApplication]:
    """The pending and approved applications, of any user and type, whose business number one of
    `applications` also has (the applications themselves included), newest first."""
    lookups = {bytes(application.business_registration_number_hmac) for application in applications}
    if not lookups:
        return []
    return list(
        session.scalars(
            select(BarOwnerApplication)
            .where(
                BarOwnerApplication.business_registration_number_hmac.in_(lookups),
                BarOwnerApplication.status.in_(SHARED_STATUSES),
            )
            .order_by(BarOwnerApplication.created_at.desc(), BarOwnerApplication.id.desc())
        )
    )


def _warnings(
    application: BarOwnerApplication, by_number: dict[bytes, list[BarOwnerApplication]], bars: dict[UUID, Bar]
) -> list[ApplicationWarning]:
    """BUSINESS_NUMBER_SHARED when other pending or approved applications give the same number. Only the
    application itself is left out: the applicant's other applications count too. A bar whose owner was
    removed later (3.11.10) still counts, since its application stays approved."""
    others = [
        other
        for other in by_number.get(bytes(application.business_registration_number_hmac), [])
        if other.id != application.id
    ]
    if not others:
        return []
    return [
        BusinessNumberSharedWarning(
            code="BUSINESS_NUMBER_SHARED",
            message=(
                f"같은 사업자등록번호로 낸 다른 신청이 {len(others)}건 있습니다. "
                "같은 사업자의 다른 매장인지 확인해 주세요."
            ),
            details=SharedNumberDetails(
                applications=[
                    SharedNumberApplication(
                        applicationId=other.id,
                        status=other.status.value,
                        applicationType=other.application_type.value,
                        barName=bars[other.bar_id].name if other.bar_id is not None else other.proposed_bar_name,
                        sameApplicant=other.applicant_user_id == application.applicant_user_id,
                    )
                    for other in others
                ]
            ),
        )
    ]


def _response(
    application: BarOwnerApplication,
    users: dict[UUID, User],
    bars: dict[UUID, Bar],
    photos: list[ApplicationMenuPhoto],
    links: ImageLinks,
    show_verification: bool,
    *,
    warnings: list[ApplicationWarning] | None,
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
        warnings=warnings,
        contactPhone=application.contact_phone,
        applicantNote=application.applicant_note,
        menuPhotos=photos,
        coverPhoto=_cover_photo(application, links),
        rejectionReason=application.rejection_reason,
        reviewedAt=application.reviewed_at,
        createdAt=application.created_at,
        updatedAt=application.updated_at,
    )


def _cover_photo_application(
    session: Session, principal: Principal, application_id: str, *, lock: bool = False
) -> BarOwnerApplication:
    """The caller's own pending new_bar application, checked in the order of spec 3.11.17."""
    application = _find(session, application_id, lock=lock)
    if application is None or not _is_applicant(session, principal, application):
        raise application_not_found()
    if application.application_type != OwnerApplicationType.NEW_BAR:
        raise ApiError(
            409,
            "INVALID_APPLICATION_TYPE",
            "새 업장 신청에만 대표 사진을 올릴 수 있습니다.",
            details={"applicationType": application.application_type.value},
        )
    if application.status != OwnerApplicationStatus.PENDING:
        raise invalid_application_state(application)
    return application


def _own_response(
    session: Session, principal: Principal, application: BarOwnerApplication, links: ImageLinks
) -> OwnerApplicationResponse:
    operator = user_type_of(principal, session) == "operator"
    return application_responses(session, [application], links, show_verification=operator)[0]


def _cover_photo(application: BarOwnerApplication, links: ImageLinks) -> ApplicationCoverPhoto | None:
    if application.cover_photo_storage_key is None:
        return None
    image_url, expires_at = links.url(application.cover_photo_storage_key)
    thumbnail_url, _ = links.url(application.cover_photo_thumbnail_storage_key)
    return ApplicationCoverPhoto(imageUrl=image_url, thumbnailUrl=thumbnail_url, imageUrlExpiresAt=expires_at)


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
        lookup = get_business_number_cipher().lookup(request.businessRegistrationNumber)
        stmt = stmt.where(BarOwnerApplication.business_registration_number_hmac == lookup)
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
    check = call_nts(principal, request, verifier, limiter, now)
    if check is None:
        return BusinessVerificationResult.UNAVAILABLE, None
    if not check.matched:
        raise ApiError(
            422,
            "BUSINESS_VERIFICATION_FAILED",
            "사업자등록번호, 대표자명, 개업일자가 사업자등록증과 같은지 확인해 주세요.",
        )
    return BusinessVerificationResult.MATCHED, check.business_status
