"""Bars with their management state (API spec 3.6), editing a bar (3.7), and the bars the caller owns (3.11.9).

`bar_details` loads the unfinished imports, current menus, current owners, weekly hours,
operating exceptions and photos of many bars with one query each, so a list of bars costs the same few
queries as one bar.
"""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import validation_failed_fields
from app.core.security import Principal
from app.models import Bar, BarOwner, BarStatus, MenuBoard, MenuImport, User
from app.schemas.bar import ActiveMenuImport, BarDetail, BarOwnerSummary, BarPhotoResponse, BarUpdateInput, CurrentMenu
from app.schemas.bar_hours import OperatingException, WeeklyHours
from app.services.bar_access import forbidden
from app.services.bar_hours import (
    operating_exceptions_by_bar,
    replace_weekly_hours,
    seoul_today,
    tag_errors,
    weekly_hours_by_bar,
    weekly_hours_errors,
)
from app.services.bar_photo_links import photos_by_bar
from app.services.menu_import_upload import UNFINISHED_STATUSES


def my_bars(session: Session, principal: Principal, *, base_url: str) -> list[BarDetail]:
    """Bars the caller currently owns, by name; empty for a caller without a users row. Operators get
    only bars they own themselves, not every bar (that is 3.4)."""
    bars = session.scalars(
        select(Bar)
        .join(BarOwner, BarOwner.bar_id == Bar.id)
        .join(User, User.id == BarOwner.user_id)
        .where(User.auth_subject == principal.subject, BarOwner.revoked_at.is_(None))
        .order_by(Bar.name, Bar.id)
    ).all()
    return bar_details(session, bars, base_url=base_url)


def get_bar_detail(session: Session, bar: Bar, *, base_url: str) -> BarDetail:
    """One bar, inactive ones included (3.6)."""
    return bar_details(session, [bar], base_url=base_url)[0]


def update_bar(session: Session, bar: Bar, patch: BarUpdateInput, *, operator: bool, base_url: str) -> BarDetail:
    """Change the fields that were sent (3.7). Only an operator may change `status`."""
    sent = patch.model_fields_set
    if "status" in sent and not operator:
        raise forbidden()
    errors = []
    if ("latitude" in sent) != ("longitude" in sent):
        missing = "longitude" if "latitude" in sent else "latitude"
        errors.append({"path": missing, "code": "LAT_LNG_REQUIRED_TOGETHER", "message": "위도와 경도는 함께 보내야 합니다."})
    elif "address" in sent and "latitude" not in sent:
        # A new address without coordinates would leave the bar's map position at the old address.
        errors += [
            {"path": path, "code": "COORDINATES_REQUIRED", "message": "주소를 바꾸면 위도와 경도도 함께 보내야 합니다."}
            for path in ("latitude", "longitude")
        ]
    if patch.tags is not None:
        errors += tag_errors(patch.tags)
    if patch.weeklyHours is not None:
        errors += weekly_hours_errors(patch.weeklyHours)
    if errors:
        raise validation_failed_fields(errors)
    for field, column in (
        ("name", "name"),
        ("address", "address"),
        ("phone", "phone"),
        ("description", "description"),
        ("defaultPourMl", "default_pour_ml"),
        ("tags", "tags"),
    ):
        if field in sent:
            setattr(bar, column, getattr(patch, field))
    if "latitude" in sent:
        bar.latitude = Decimal(str(patch.latitude))
        bar.longitude = Decimal(str(patch.longitude))
    if "status" in sent:
        bar.status = BarStatus(patch.status)
    if patch.weeklyHours is not None:
        # The bar row lock orders concurrent replacements, which would otherwise insert the same days twice.
        session.execute(select(Bar.id).where(Bar.id == bar.id).with_for_update())
        if replace_weekly_hours(session, bar.id, patch.weeklyHours):
            # The hours live in their own table, so the bars row would not change by itself. clock_timestamp(),
            # not now(): a request that waited for the lock must not look older than the one it waited for.
            bar.updated_at = func.clock_timestamp()
    # A value equal to the stored one is no change, so `updatedAt` moves only when something changed.
    session.commit()
    return bar_details(session, [bar], base_url=base_url)[0]


def bar_details(session: Session, bars: Sequence[Bar], *, base_url: str) -> list[BarDetail]:
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
    hours = weekly_hours_by_bar(session, bar_ids)
    exceptions = operating_exceptions_by_bar(session, bar_ids, seoul_today())
    photos = photos_by_bar(session, bar_ids, base_url)
    return [
        _detail(
            bar,
            hours[bar.id],
            exceptions.get(bar.id),
            photos[bar.id],
            unfinished.get(bar.id),
            boards.get(bar.id),
            owners.get(bar.id),
        )
        for bar in bars
    ]


def _detail(
    bar: Bar,
    hours: list[WeeklyHours],
    operating_exception: OperatingException | None,
    photos: list[BarPhotoResponse],
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
        description=bar.description,
        defaultPourMl=bar.default_pour_ml,
        tags=list(bar.tags),
        weeklyHours=hours,
        operatingException=operating_exception,
        photos=photos,
        status=bar.status.value,
        activeMenuImport=(
            ActiveMenuImport(menuImportId=menu_import.id, status=menu_import.status.value)
            if menu_import is not None
            else None
        ),
        currentMenu=(
            CurrentMenu(
                menuBoardId=board.id,
                menuVersion=board.version,
                publishedAt=board.published_at,
                confirmedAt=board.confirmed_at,
            )
            if board is not None
            else None
        ),
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
