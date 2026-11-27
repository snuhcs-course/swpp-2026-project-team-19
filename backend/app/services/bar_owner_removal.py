"""Ending a bar's current ownership (API spec 3.11.10): an operator removes the owner, or the owner ends
their own management of the bar. The route has already found the bar and checked the caller.

The ownership row is kept, with when and by whom (the operator, or the owner themselves) it was revoked,
and the approved application stays approved; the former owner may apply again. The bar's status is not
changed. The bar row is locked and the caller checked again before the owner is read, as approvals and
every menu, hours and photo change of the bar do (spec 3.14.1): a request of the former owner that takes
the lock after the removal gets `403`, a second removal by the owner too, and an approval of another
application for the bar or a second removal by an operator waits and then sees no current owner.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import Principal
from app.models import BarOwner
from app.services.bar_access import lock_bar_for_manager
from app.services.users import caller_user_id, user_not_found


def bar_owner_not_found() -> ApiError:
    return ApiError(404, "BAR_OWNER_NOT_FOUND", "업장에 현재 업주가 없습니다.")


def remove_owner(session: Session, principal: Principal, bar_id: UUID, *, now: datetime) -> None:
    """Revoke the bar's current ownership. Under the bar row lock, checks the caller again (an operator or
    the current owner), then the caller's users row (the revoker is recorded), then the current owner."""
    lock_bar_for_manager(session, principal, bar_id)
    revoker_id = caller_user_id(session, principal)
    if revoker_id is None:
        raise user_not_found()
    ownership = session.scalar(select(BarOwner).where(BarOwner.bar_id == bar_id, BarOwner.revoked_at.is_(None)))
    if ownership is None:
        raise bar_owner_not_found()
    ownership.revoked_at = now
    ownership.revoked_by_user_id = revoker_id
    session.commit()
