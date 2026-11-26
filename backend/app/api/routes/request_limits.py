from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_clock, get_request_limiter
from app.core.security import Principal, require_operator
from app.db.session import get_session
from app.schemas.errors import AUTH_UNAVAILABLE, error_responses
from app.schemas.request_limit import RequestLimitResetInput, RequestLimitResetResponse
from app.services.request_limit_reset import reset_request_limits
from app.services.request_limits import (
    BUSINESS_CERTIFICATE_OCR_DAILY_LIMIT,
    BUSINESS_VERIFICATION_DAILY_LIMIT,
    DailyRequestLimiter,
)

router = APIRouter(prefix="/api", tags=["request limits"])


@router.post(
    "/request-limits/reset",
    response_model=RequestLimitResetResponse,
    summary="Reset today's NTS check, certificate OCR and menu photo counts",
    description=(
        "Operator only. Clears today's counts of the daily limits (at most "
        f"{BUSINESS_VERIFICATION_DAILY_LIMIT} NTS checks and {BUSINESS_CERTIFICATE_OCR_DAILY_LIMIT} certificate OCR "
        "calls per user, and the daily menu photo limit of spec 4.1) without restarting the server, so the "
        "user can call again at once.\n\n"
        "- No body or `{}` clears every user's counts of every kind.\n"
        "- `userId` clears only that user's counts. Counts are kept by token `sub`, so the user is looked up in "
        "`users`; a caller without a `users` row is cleared only by a reset of every user.\n"
        "- `kind` clears only `business_verification`, `business_certificate_ocr` or `menu_import_photos`.\n"
        "- Checks in order: operator, body fields, the user."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
        (403, "`FORBIDDEN`: the caller is not an operator."),
        (404, "`USER_NOT_FOUND`: no `users` row has `userId`."),
        AUTH_UNAVAILABLE,
    ),
)
def reset_limits(
    request: Annotated[RequestLimitResetInput | None, Body()] = None,
    operator: Principal = Depends(require_operator),
    session: Session = Depends(get_session),
    limiter: DailyRequestLimiter = Depends(get_request_limiter),
    clock: Callable[[], datetime] = Depends(get_clock),
) -> RequestLimitResetResponse:
    return reset_request_limits(session, limiter, operator, request or RequestLimitResetInput(), clock())
