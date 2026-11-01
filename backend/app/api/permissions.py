"""Route dependencies for the APIs an operator or the bar's approved owner may call (API spec 2.2).

The order is the spec's: a valid token (`401`), then the target bar or import exists (`404`), then
the caller is an operator or the target bar's current owner (`403`). Like `require_operator`, they
run before the endpoint, so a caller without access never reaches the request's own checks.

They return what they found, so the services do not look it up again. The bar is loaded with the
request's session, which the route shares.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_user
from app.db.session import get_session
from app.models import Bar, BarStatus, MenuImport
from app.services.bar_access import can_manage_bar, forbidden, is_operator, owns_any_bar
from app.services.bar_menu import bar_not_found
from app.services.menu_import_review import menu_import_not_found

BarId = Annotated[str, Path(alias="barId", description="Bar id (UUID)")]
MenuImportId = Annotated[str, Path(alias="menuImportId", description="Menu import id (UUID)")]


def _bar(session: Session, bar_id: str) -> Bar | None:
    try:
        return session.get(Bar, UUID(bar_id))
    except ValueError:
        return None


def require_bar_manager(
    bar_id: BarId,
    # Declared before the session so a request without a valid token never opens a database session.
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Bar:
    """The bar, for an operator or its current owner; inactive bars included."""
    bar = _bar(session, bar_id)
    if bar is None:
        raise bar_not_found(bar_id)
    if not can_manage_bar(session, principal, bar.id):
        raise forbidden()
    return bar


def require_active_bar_manager(
    bar_id: BarId,
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Bar:
    """As require_bar_manager, but an inactive bar is `404` for everyone (spec 4.4)."""
    bar = _bar(session, bar_id)
    if bar is None or bar.status != BarStatus.ACTIVE:
        raise bar_not_found(bar_id)
    if not can_manage_bar(session, principal, bar.id):
        raise forbidden()
    return bar


def require_import_manager(
    menu_import_id: MenuImportId,
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UUID:
    """The import's id, for an operator or the current owner of its bar. Only the id: review-and-apply
    loads the import again in its own transaction."""
    try:
        import_id = UUID(menu_import_id)
    except ValueError:
        raise menu_import_not_found(menu_import_id) from None
    bar_id = session.scalar(select(MenuImport.bar_id).where(MenuImport.id == import_id))
    if bar_id is None:
        raise menu_import_not_found(menu_import_id)
    if not can_manage_bar(session, principal, bar_id):
        raise forbidden()
    return import_id


def require_operator_or_owner(
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Principal:
    """An operator, or the current owner of at least one bar (the catalog search APIs)."""
    if not (is_operator(session, principal) or owns_any_bar(session, principal)):
        raise forbidden()
    return principal
