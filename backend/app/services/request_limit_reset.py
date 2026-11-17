"""An operator clearing today's request counts without a restart (API spec, section 3.11.19).

The limiter counts by token `sub`, so a `userId` is turned into the user's `auth_subject`. A caller
without a `users` row is reached only by a reset of every user.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.models import User
from app.schemas.request_limit import RequestLimitResetInput, RequestLimitResetResponse
from app.services.request_limits import DailyRequestLimiter
from app.services.users import caller_user_id, user_not_found

logger = logging.getLogger(__name__)


def reset_request_limits(
    session: Session,
    limiter: DailyRequestLimiter,
    operator: Principal,
    request: RequestLimitResetInput,
    now: datetime,
) -> RequestLimitResetResponse:
    subject = None
    if request.userId is not None:
        subject = session.scalar(select(User.auth_subject).where(User.id == request.userId))
        if subject is None:
            raise user_not_found()
    operator_id = caller_user_id(session, operator)

    cleared = limiter.reset(subject, request.kind, now)
    # Ids only: never the token subject or an email.
    logger.info(
        "Request counts reset by operator %s: user %s, kind %s, %d cleared",
        operator_id,
        request.userId or "all",
        request.kind or "all",
        cleared,
    )
    return RequestLimitResetResponse(clearedCount=cleared)
