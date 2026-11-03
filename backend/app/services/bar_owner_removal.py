"""Removing a bar's current owner (API spec 3.11.10). Operator only; the route checks that first.

The ownership row is kept, with when and by which operator it was revoked, and the approved
application stays approved; the former owner may apply again. The bar row is locked before the owner
is read, as approvals and every menu, hours and photo change of the bar do (spec 3.14.1): a request
of the former owner that takes the lock after the removal checks again and gets `403`, and an approval
of another application for the bar or a second removal waits and then sees no current owner.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import Principal
from app.models import Bar, BarOwner
from app.services.bar_menu import bar_not_found
from app.services.users import caller_user_id, user_not_found


def bar_owner_not_found() -> ApiError:
    return ApiError(404, "BAR_OWNER_NOT_FOUND", "업장에 현재 업주가 없습니다.")


def remove_owner(session: Session, principal: Principal, bar_id: str, *, now: datetime) -> None:
    """Revoke the bar's current ownership. Checks the operator's users row (the revoker is recorded),
    then the bar, then, under the bar row lock, its current owner."""
    revoker_id = caller_user_id(session, principal)
    if revoker_id is None:
        raise user_not_found()
    try:
        bar_uuid = UUID(bar_id)
    except ValueError:
        raise bar_not_found(bar_id) from None
    if session.scalar(select(Bar.id).where(Bar.id == bar_uuid).with_for_update()) is None:
        raise bar_not_found(bar_id)
    ownership = session.scalar(select(BarOwner).where(BarOwner.bar_id == bar_uuid, BarOwner.revoked_at.is_(None)))
    if ownership is None:
        raise bar_owner_not_found()
    ownership.revoked_at = now
    ownership.revoked_by_user_id = revoker_id
    session.commit()
