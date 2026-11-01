"""Who may manage a bar (API spec 2.2): an operator manages every bar, an approved owner only theirs.

Ownership is the bar's current `bar_owners` row (`revoked_at` null), read on every request, so an
approval or a revocation applies from the next request. A pending application grants nothing.
"""

from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import Principal, user_type_of
from app.models import BarOwner, User


def forbidden() -> ApiError:
    return ApiError(403, "FORBIDDEN", "이 작업을 할 권한이 없습니다.")


def _owned_by_caller(principal: Principal):
    return (
        select(BarOwner.bar_id)
        .join(User, User.id == BarOwner.user_id)
        .where(User.auth_subject == principal.subject, BarOwner.revoked_at.is_(None))
    )


def is_operator(session: Session, principal: Principal) -> bool:
    return user_type_of(principal, session) == "operator"


def owns_bar(session: Session, principal: Principal, bar_id: UUID) -> bool:
    return session.scalar(select(exists(_owned_by_caller(principal).where(BarOwner.bar_id == bar_id)))) is True


def owns_any_bar(session: Session, principal: Principal) -> bool:
    return session.scalar(select(exists(_owned_by_caller(principal)))) is True


def can_manage_bar(session: Session, principal: Principal, bar_id: UUID) -> bool:
    return is_operator(session, principal) or owns_bar(session, principal, bar_id)
