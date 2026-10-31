from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.adapters.business_verification import BusinessVerifier
from app.adapters.extraction import MenuExtractor
from app.api.deps import (
    get_business_verifier,
    get_clock,
    get_image_links,
    get_matching_llm_layer,
    get_menu_extractor,
    get_request_limiter,
)
from app.api.routes.bars import Cursor, Limit
from app.api.routes.menu_imports import UploadedImage
from app.core.security import Principal, get_current_user, require_operator, user_type_of
from app.db.session import get_session, get_session_factory
from app.matching.llm_layer import LLMLayerConfig
from app.schemas.errors import AUTH_UNAVAILABLE, error_responses
from app.schemas.owner_application import (
    ApproveInput,
    OwnerApplicationInput,
    OwnerApplicationListResponse,
    OwnerApplicationPage,
    OwnerApplicationResponse,
    RejectInput,
)
from app.services import menu_import_upload as upload
from app.services.image_links import ImageLinks
from app.services.menu_import_processing import SessionFactory, start_processing
from app.services.menu_import_upload import ImageUpload
from app.services.owner_application_review import (
    StatusFilter,
    TypeFilter,
    VerificationFilter,
    approve_application,
    list_applications,
    reject_application,
)
from app.services.owner_applications import (
    application_responses,
    cancel_application,
    get_application,
    list_my_applications,
    replace_menu_photos,
    submit_application,
)
from app.services.request_limits import DAILY_LIMIT, DailyRequestLimiter

router = APIRouter(prefix="/api", tags=["owner applications"])

_UNAUTHENTICATED = (401, "`UNAUTHENTICATED`: missing, invalid or expired token.")
_FORBIDDEN = (403, "`FORBIDDEN`: the caller is not an operator.")
_REVIEW_NOT_FOUND = (
    404,
    "`USER_NOT_FOUND`: the operator has no users row (only a temporary-login operator can lack one; call "
    "`GET /api/me` and retry). `OWNER_APPLICATION_NOT_FOUND`: no such application, or a malformed id.",
)
_NOT_PENDING = "`INVALID_APPLICATION_STATE`: the application is not `pending`; `details.status` is its status."


@router.post(
    "/owner-applications",
    status_code=status.HTTP_201_CREATED,
    response_model=OwnerApplicationResponse,
    summary="Apply to own an existing bar or to register a new one",
    description=(
        "Any signed-in user with a users row (call `GET /api/me` first). Creates a `pending` application "
        "after the checks of spec 3.11.2, in this order: fields, users row, the bar and its owner, the "
        "caller's pending applications, and last the NTS business check.\n\n"
        "- The NTS check compares `businessRegistrationNumber`, `representativeName` and `openingDate`. "
        "A mismatch creates nothing (`422 BUSINESS_VERIFICATION_FAILED`). When NTS cannot be reached or the "
        "server has no NTS key, the application is created with the result `unavailable` for an operator "
        "to check again.\n"
        f"- At most {DAILY_LIMIT} NTS checks per user (token `sub`) per day, reset at midnight KST; only "
        "requests that call NTS count.\n"
        "- `Location` is the new application. `businessVerification` is null unless the caller is an operator."
    ),
    responses=error_responses(
        _UNAUTHENTICATED,
        (
            404,
            "`USER_NOT_FOUND`: no users row; call `GET /api/me` and retry. `BAR_NOT_FOUND`: the existing_bar "
            "bar does not exist, is inactive, or `barId` is not a UUID.",
        ),
        (
            409,
            "`BAR_OWNER_EXISTS`: the bar already has an owner (the caller included). `OWNER_APPLICATION_EXISTS`: "
            "the caller has a pending application for the same bar, or a pending new_bar application with the "
            "same business number; `details.applicationId` is that application.",
        ),
        (429, "`RATE_LIMITED`: today's NTS checks are used up; `details.retryAfter` is the next reset (UTC)."),
        (
            422,
            "`VALIDATION_FAILED`: see `fieldErrors`; `INVALID_BUSINESS_NUMBER` for a malformed business number "
            "or check digit, `DATE_IN_FUTURE` for an opening date after today (KST). "
            "`BUSINESS_VERIFICATION_FAILED`: the three values do not match NTS records; nothing was created.",
        ),
        AUTH_UNAVAILABLE,
    ),
)
def create_owner_application(
    response: Response,
    request: Annotated[OwnerApplicationInput, Body(discriminator="applicationType")],
    # Declared before the session so a request without a valid token never opens a database session.
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    verifier: BusinessVerifier | None = Depends(get_business_verifier),
    limiter: DailyRequestLimiter = Depends(get_request_limiter),
    clock: Callable[[], datetime] = Depends(get_clock),
    links: ImageLinks = Depends(get_image_links),
) -> OwnerApplicationResponse:
    application = submit_application(session, principal, request, verifier=verifier, limiter=limiter, now=clock())
    response.headers["Location"] = f"/api/owner-applications/{application.id}"
    operator = user_type_of(principal, session) == "operator"
    return application_responses(session, [application], links, show_verification=operator)[0]


@router.get(
    "/me/owner-applications",
    response_model=OwnerApplicationListResponse,
    summary="My owner applications",
    description=(
        "Any signed-in user. The caller's applications in every status, newest first, without paging; "
        "empty when there are none or the caller has no users row yet. `businessVerification` is always "
        "null here; `businessStatus` shows the NTS status. Operators also see only their own."
    ),
    responses=error_responses(_UNAUTHENTICATED, AUTH_UNAVAILABLE),
)
def read_my_owner_applications(
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    links: ImageLinks = Depends(get_image_links),
) -> OwnerApplicationListResponse:
    return OwnerApplicationListResponse(items=list_my_applications(session, principal, links))


@router.get(
    "/owner-applications/{applicationId}",
    response_model=OwnerApplicationResponse,
    summary="One owner application",
    description=(
        "The applicant or an operator. `businessVerification` is filled only for operators. Someone "
        "else's application answers `404` like a missing one, so its existence is not revealed."
    ),
    responses=error_responses(
        _UNAUTHENTICATED,
        (
            404,
            "`OWNER_APPLICATION_NOT_FOUND`: no such application, someone else's, or `applicationId` is not a UUID.",
        ),
        AUTH_UNAVAILABLE,
    ),
)
def read_owner_application(
    application_id: Annotated[str, Path(alias="applicationId", description="Application id (UUID)")],
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    links: ImageLinks = Depends(get_image_links),
) -> OwnerApplicationResponse:
    return get_application(session, principal, application_id, links)


@router.post(
    "/owner-applications/{applicationId}/cancel",
    response_model=OwnerApplicationResponse,
    summary="Cancel my pending owner application",
    description=(
        "The applicant only; an operator may cancel only their own applications too. No request body. "
        "A `pending` application becomes `canceled`, a final status; the applicant may apply again. "
        "Its menu photos are deleted. "
        "`businessVerification` is null unless the caller is an operator."
    ),
    responses=error_responses(
        _UNAUTHENTICATED,
        (
            404,
            "`OWNER_APPLICATION_NOT_FOUND`: no such application, someone else's, or `applicationId` is not a UUID.",
        ),
        (409, "`INVALID_APPLICATION_STATE`: the application is not `pending`; `details.status` is its status."),
        AUTH_UNAVAILABLE,
    ),
)
def cancel_owner_application(
    application_id: Annotated[str, Path(alias="applicationId", description="Application id (UUID)")],
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    links: ImageLinks = Depends(get_image_links),
) -> OwnerApplicationResponse:
    return cancel_application(session, principal, application_id, links)


@router.put(
    "/owner-applications/{applicationId}/menu-photos",
    response_model=OwnerApplicationResponse,
    summary="Replace the menu photos of my pending owner application",
    description=(
        "The applicant only, while the application is `pending`. Each call replaces all of the "
        "application's menu photos with the ones sent, in display order; retrying the same request gives "
        "the same result. On approval the photos become the bar's first menu import and extraction starts; "
        "rejecting or canceling deletes them.\n\n"
        f"- Up to {upload.MAX_IMAGES} JPEG or PNG photos, {upload.MAX_IMAGE_BYTES // 2**20} MB each and "
        f"{upload.MAX_TOTAL_BYTES // 2**20} MB in total, checked like `POST /api/bars/{{barId}}/menu-imports`.\n"
        "- `menuPhotos` in the response has short-lived URLs; fetch the application again when they expire."
    ),
    responses=error_responses(
        _UNAUTHENTICATED,
        (
            404,
            "`OWNER_APPLICATION_NOT_FOUND`: no such application, someone else's, or `applicationId` is not a UUID.",
        ),
        (409, "`INVALID_APPLICATION_STATE`: the application is not `pending`; `details.status` is its status."),
        (413, "`UPLOAD_TOO_LARGE`: too many photos, or a photo or the total is too large; limits in `details`."),
        (415, "`UNSUPPORTED_IMAGE_TYPE`: not JPEG or PNG (HEIC included); `details.imageOrder` names the photo."),
        (422, "`VALIDATION_FAILED`: `images` `MISSING`."),
        AUTH_UNAVAILABLE,
    ),
)
def put_owner_application_menu_photos(
    application_id: Annotated[str, Path(alias="applicationId", description="Application id (UUID)")],
    images: Annotated[list[UploadedImage], File(description="Menu photos in display order")],
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
    links: ImageLinks = Depends(get_image_links),
) -> OwnerApplicationResponse:
    uploads = [ImageUpload(image.filename, image.content_type, image.file) for image in images]
    return replace_menu_photos(session, principal, application_id, uploads, links)


@router.get(
    "/owner-applications",
    response_model=OwnerApplicationPage,
    summary="Owner applications for operators to review",
    description=(
        "Operator only. Applications with the NTS check result (`businessVerification`) and menu photos. "
        "With the default `status=pending` they come oldest first, the order to work through them; other "
        "statuses come newest first. Use `verificationResult=unavailable` to find applications to check again.\n\n"
        "Pages use a cursor: pass `nextCursor` as `cursor` with the same filters; it is null on the last "
        "page. A cursor from other filters is `INVALID_CURSOR`."
    ),
    responses=error_responses(
        _UNAUTHENTICATED,
        _FORBIDDEN,
        (
            422,
            "`VALIDATION_FAILED`: `status`, `applicationType` or `verificationResult` not one of the values "
            "(`LITERAL_ERROR`); `limit` out of range; `cursor` `INVALID_CURSOR`.",
        ),
        AUTH_UNAVAILABLE,
    ),
)
def read_owner_applications(
    application_status: Annotated[
        StatusFilter, Query(alias="status", description="`pending`, `approved`, `rejected`, `canceled` or `all`")
    ] = "pending",
    application_type: Annotated[
        TypeFilter | None, Query(alias="applicationType", description="`existing_bar` or `new_bar`; both if omitted")
    ] = None,
    verification_result: Annotated[
        VerificationFilter | None,
        Query(alias="verificationResult", description="`matched`, `not_matched` or `unavailable`; all if omitted"),
    ] = None,
    limit: Limit = 20,
    cursor: Cursor = None,
    _operator: Principal = Depends(require_operator),
    session: Session = Depends(get_session),
    links: ImageLinks = Depends(get_image_links),
) -> OwnerApplicationPage:
    return list_applications(
        session,
        links,
        status=application_status,
        application_type=application_type,
        verification_result=verification_result,
        limit=limit,
        cursor=cursor,
    )


@router.post(
    "/owner-applications/{applicationId}/approve",
    response_model=OwnerApplicationResponse,
    summary="Approve an owner application",
    description=(
        "Operator only, whatever the NTS check result. In one transaction: for `new_bar`, creates an active "
        "bar from `bar` (prefill it from `proposedBar` and add the coordinates); makes the applicant the "
        "bar's owner from their next request; and, when the application has menu photos and the bar has no "
        "unfinished import, creates the bar's menu import from them (`full_replace` without a current menu, "
        "`partial_update` with one). Extraction starts after the commit; nothing is published before the "
        "owner's review. The owner finds the import as `activeMenuImport` of `GET /api/bars/{barId}`.\n\n"
        "- `existing_bar`: no body or `{}`. Allowed even if the bar was deactivated after applying.\n"
        "- Checks in order: operator, body fields, users row, application and status, `bar` for the "
        "application type, the bar's current owner."
    ),
    responses=error_responses(
        _UNAUTHENTICATED,
        _FORBIDDEN,
        _REVIEW_NOT_FOUND,
        (
            409,
            f"{_NOT_PENDING} `BAR_OWNER_EXISTS`: the bar already has an owner, e.g. another application for "
            "it was approved first; reject this one.",
        ),
        (
            422,
            "`VALIDATION_FAILED`: `bar` field rules; `bar` `MISSING` for new_bar, `EXTRA_FORBIDDEN` for existing_bar.",
        ),
        AUTH_UNAVAILABLE,
    ),
)
def approve_owner_application(
    background_tasks: BackgroundTasks,
    application_id: Annotated[str, Path(alias="applicationId", description="Application id (UUID)")],
    request: Annotated[ApproveInput | None, Body()] = None,
    operator: Principal = Depends(require_operator),
    session: Session = Depends(get_session),
    links: ImageLinks = Depends(get_image_links),
    extractor: MenuExtractor = Depends(get_menu_extractor),
    llm_layer: LLMLayerConfig | None = Depends(get_matching_llm_layer),
    session_factory: SessionFactory = Depends(get_session_factory),
    clock: Callable[[], datetime] = Depends(get_clock),
) -> OwnerApplicationResponse:
    application, menu_import = approve_application(
        session, operator, application_id, request, extractor=extractor, now=clock()
    )
    if menu_import is not None:
        start_processing(
            session,
            background_tasks,
            menu_import,
            session_factory=session_factory,
            storage=links.storage,
            extractor=extractor,
            llm_layer=llm_layer,
        )
    return application_responses(session, [application], links, show_verification=True)[0]


@router.post(
    "/owner-applications/{applicationId}/reject",
    response_model=OwnerApplicationResponse,
    summary="Reject an owner application",
    description=(
        "Operator only, whatever the NTS check result. `reason` is shown to the applicant as it is. "
        "The application's menu photos are deleted. The applicant may apply again."
    ),
    responses=error_responses(
        _UNAUTHENTICATED,
        _FORBIDDEN,
        _REVIEW_NOT_FOUND,
        (409, _NOT_PENDING),
        (422, "`VALIDATION_FAILED`: `reason` `MISSING`, `BLANK` (only spaces) or `STRING_TOO_LONG` (over 500)."),
        AUTH_UNAVAILABLE,
    ),
)
def reject_owner_application(
    application_id: Annotated[str, Path(alias="applicationId", description="Application id (UUID)")],
    request: RejectInput,
    operator: Principal = Depends(require_operator),
    session: Session = Depends(get_session),
    links: ImageLinks = Depends(get_image_links),
    clock: Callable[[], datetime] = Depends(get_clock),
) -> OwnerApplicationResponse:
    return reject_application(session, operator, application_id, request, links=links, now=clock())
