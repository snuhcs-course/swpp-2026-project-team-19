"""The BottleMap user behind a verified token (API spec, section 3.2).

`GET /api/me` is the only place that creates users. The first call stores the token's subject
as `auth_subject` with user type customer (a temporary user takes TEMP_AUTH_USER_TYPE instead).
Later calls keep the email in step with the token but never overwrite the display name, which
the user may have changed.
"""

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.models import User, UserType

MAX_DISPLAY_NAME_LENGTH = 20
MAX_EMAIL_LENGTH = 255


def sync_current_user(session: Session, principal: Principal) -> User:
    """Create the caller's user on the first call, then bring the stored values up to date."""
    # Concurrent first calls insert at most one row; the losers fall through to the select.
    session.execute(
        insert(User)
        .values(
            id=uuid4(),
            auth_subject=principal.subject,
            display_name=display_name_from(principal.claims),
            user_type=_initial_user_type(principal),
        )
        .on_conflict_do_nothing(index_elements=[User.auth_subject])
    )
    user = session.scalars(select(User).where(User.auth_subject == principal.subject)).one()

    if principal.user_type is not None and user.user_type != principal.user_type:
        # A temporary user's role follows TEMP_AUTH_USER_TYPE (API spec, section 3.1.3).
        user.user_type = UserType(principal.user_type)
    _set_email(session, user, email_from(principal.claims))
    session.commit()
    return user


def display_name_from(claims: dict[str, Any]) -> str | None:
    """The Google account name, trimmed and cut to 20 characters; None when there is none."""
    metadata = claims.get("user_metadata")
    name = metadata.get("name") if isinstance(metadata, dict) else claims.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    return name.strip()[:MAX_DISPLAY_NAME_LENGTH]


def email_from(claims: dict[str, Any]) -> str | None:
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip() or len(email.strip()) > MAX_EMAIL_LENGTH:
        return None
    return email.strip()


def _initial_user_type(principal: Principal) -> UserType:
    return UserType(principal.user_type) if principal.user_type is not None else UserType.CUSTOMER


def _set_email(session: Session, user: User, email: str | None) -> None:
    """Store the token's email; null when another user already has it (`users.email` is unique)."""
    if user.email == email:
        return
    try:
        with session.begin_nested():
            user.email = email
            session.flush()
    except IntegrityError:
        # The rollback expired the row; reading it reloads the stored email.
        if user.email is not None:
            user.email = None
