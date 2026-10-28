from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Response, status
from sqlalchemy.orm import Session

from app.adapters.business_verification import BusinessVerifier
from app.api.deps import get_business_verifier, get_clock, get_request_limiter
from app.core.security import Principal, get_current_user, user_type_of
from app.db.session import get_session
from app.schemas.errors import AUTH_UNAVAILABLE, error_responses
from app.schemas.owner_application import (
    OwnerApplicationInput,
    OwnerApplicationListResponse,
    OwnerApplicationResponse,
)
from app.services.owner_applications import (
    application_responses,
    get_application,
    list_my_applications,
    submit_application,
)
from app.services.request_limits import DAILY_LIMIT, DailyRequestLimiter

router = APIRouter(prefix="/api", tags=["owner applications"])

_UNAUTHENTICATED = (401, "`UNAUTHENTICATED`: missing, invalid or expired token.")


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
) -> OwnerApplicationResponse:
    application = submit_application(session, principal, request, verifier=verifier, limiter=limiter, now=clock())
    response.headers["Location"] = f"/api/owner-applications/{application.id}"
    operator = user_type_of(principal, session) == "operator"
    return application_responses(session, [application], show_verification=operator)[0]


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
) -> OwnerApplicationListResponse:
    return OwnerApplicationListResponse(items=list_my_applications(session, principal))


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
) -> OwnerApplicationResponse:
    return get_application(session, principal, application_id)
