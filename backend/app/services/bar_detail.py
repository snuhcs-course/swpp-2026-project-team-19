"""Bars with their management state (API spec 3.6), editing a bar (3.7), and the bars the caller owns (3.11.9).

`bar_details` loads the unfinished imports, current menus and current owners of many bars with one
query each, so a list of bars costs the same few queries as one bar.
"""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import validation_failed_fields
from app.core.security import Principal
from app.models import Bar, BarOwner, BarStatus, MenuBoard, MenuImport, User
from app.schemas.bar import ActiveMenuImport, BarDetail, BarOwnerSummary, BarUpdateInput, CurrentMenu
from app.services.bar_access import forbidden
from app.services.bar_menu import bar_not_found
from app.services.menu_import_upload import UNFINISHED_STATUSES


def my_bars(session: Session, principal: Principal) -> list[BarDetail]:
    """Bars the caller currently owns, by name; empty for a caller without a users row. Operators get
    only bars they own themselves, not every bar (that is 3.4)."""
    bars = session.scalars(
        select(Bar)
        .join(BarOwner, BarOwner.bar_id == Bar.id)
        .join(User, User.id == BarOwner.user_id)
        .where(User.auth_subject == principal.subject, BarOwner.revoked_at.is_(None))
        .order_by(Bar.name, Bar.id)
    ).all()
    return bar_details(session, bars)


def _load_bar(session: Session, bar_id: str) -> Bar:
    try:
        bar = session.get(Bar, UUID(bar_id))
    except ValueError:
        bar = None
    if bar is None:
        raise bar_not_found(bar_id)
    return bar


def get_bar_detail(session: Session, bar_id: str) -> BarDetail:
    """One bar, inactive ones included (3.6)."""
    return bar_details(session, [_load_bar(session, bar_id)])[0]


def update_bar(session: Session, bar_id: str, patch: BarUpdateInput, *, operator: bool) -> BarDetail:
    """Change the fields that were sent (3.7). Only an operator may change `status`."""
    bar = _load_bar(session, bar_id)
    sent = patch.model_fields_set
    if "status" in sent and not operator:
        raise forbidden()
    if ("latitude" in sent) != ("longitude" in sent):
        missing = "longitude" if "latitude" in sent else "latitude"
        raise validation_failed_fields(
            [{"path": missing, "code": "LAT_LNG_REQUIRED_TOGETHER", "message": "위도와 경도는 함께 보내야 합니다."}]
        )
    if "address" in sent and "latitude" not in sent:
        # A new address without coordinates would leave the bar's map position at the old address.
        raise validation_failed_fields(
            [
                {"path": path, "code": "COORDINATES_REQUIRED", "message": "주소를 바꾸면 위도와 경도도 함께 보내야 합니다."}
                for path in ("latitude", "longitude")
            ]
        )
    for field in ("name", "address", "phone"):
        if field in sent:
            setattr(bar, field, getattr(patch, field))
    if "latitude" in sent:
        bar.latitude = Decimal(str(patch.latitude))
        bar.longitude = Decimal(str(patch.longitude))
    if "status" in sent:
        bar.status = BarStatus(patch.status)
    # A value equal to the stored one is no change, so `updatedAt` moves only when something changed.
    session.commit()
    return bar_details(session, [bar])[0]


def bar_details(session: Session, bars: Sequence[Bar]) -> list[BarDetail]:
    if not bars:
        return []
    bar_ids = [bar.id for bar in bars]
    unfinished = dict(
        session.execute(
            select(MenuImport.bar_id, MenuImport).where(
                MenuImport.bar_id.in_(bar_ids), MenuImport.status.in_(UNFINISHED_STATUSES)
            )
        ).all()
    )
    boards = {board.bar_id: board for board in session.scalars(select(MenuBoard).where(MenuBoard.bar_id.in_(bar_ids)))}
    owners = {
        owner.bar_id: (owner, user)
        for owner, user in session.execute(
            select(BarOwner, User)
            .join(User, User.id == BarOwner.user_id)
            .where(BarOwner.bar_id.in_(bar_ids), BarOwner.revoked_at.is_(None))
        ).all()
    }
    return [_detail(bar, unfinished.get(bar.id), boards.get(bar.id), owners.get(bar.id)) for bar in bars]


def _detail(
    bar: Bar,
    menu_import: MenuImport | None,
    board: MenuBoard | None,
    owner: tuple[BarOwner, User] | None,
) -> BarDetail:
    return BarDetail(
        barId=bar.id,
        name=bar.name,
        address=bar.address,
        latitude=float(bar.latitude),
        longitude=float(bar.longitude),
        phone=bar.phone,
        status=bar.status.value,
        activeMenuImport=(
            ActiveMenuImport(menuImportId=menu_import.id, status=menu_import.status.value)
            if menu_import is not None
            else None
        ),
        currentMenu=CurrentMenu(menuBoardId=board.id, publishedAt=board.published_at) if board is not None else None,
        owner=(
            BarOwnerSummary(
                userId=owner[1].id,
                email=owner[1].email,
                displayName=owner[1].display_name,
                ownerSince=owner[0].created_at,
            )
            if owner is not None
            else None
        ),
        createdAt=bar.created_at,
        updatedAt=bar.updated_at,
    )
