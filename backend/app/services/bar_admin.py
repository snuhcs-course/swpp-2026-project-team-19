"""Operator lookups: the bar list (API spec 3.4) and a bar's menu imports (3.8)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.pagination import decode_cursor, encode_cursor
from app.models import Bar, BarStatus, ImportStatus, MenuImage, MenuImport
from app.schemas.bar import ActiveMenuImport, BarListItem, BarListResponse
from app.schemas.menu_import import MenuImportListItem, MenuImportListResponse
from app.services.bar_menu import bar_not_found
from app.services.menu_import_upload import UNFINISHED_STATUSES
from app.services.search import validate_query_text

BarStatusFilter = Literal["active", "inactive", "all"]
ImportStatusFilter = Literal["active", "uploaded", "processing", "ready_for_review", "applied", "failed", "all"]


def _text(value) -> str:
    if not isinstance(value, str):
        raise TypeError("expected a string")
    return value


def _bar_key(values: list) -> tuple[str, UUID]:
    name, bar_id = values
    return _text(name), UUID(_text(bar_id))


def _import_key(values: list) -> tuple[datetime, UUID]:
    created_at, import_id = values
    return datetime.fromisoformat(_text(created_at)), UUID(_text(import_id))


def list_bars(
    session: Session,
    *,
    query: str | None = None,
    status: BarStatusFilter = "active",
    limit: int = 20,
    cursor: str | None = None,
) -> BarListResponse:
    """Bars sorted by name, then id. `query` matches part of the name or address, ignoring case."""
    stmt = select(Bar)
    if query is not None:
        text = validate_query_text(query)
        stmt = stmt.where(or_(Bar.name.icontains(text, autoescape=True), Bar.address.icontains(text, autoescape=True)))
    if status != "all":
        stmt = stmt.where(Bar.status == BarStatus(status))
    if cursor is not None:
        stmt = stmt.where(tuple_(Bar.name, Bar.id) > tuple_(*decode_cursor(cursor, _bar_key)))
    bars = list(session.scalars(stmt.order_by(Bar.name, Bar.id).limit(limit + 1)))
    page, more = bars[:limit], len(bars) > limit

    unfinished = dict(
        session.execute(
            select(MenuImport.bar_id, MenuImport)
            .where(MenuImport.bar_id.in_([bar.id for bar in page]), MenuImport.status.in_(UNFINISHED_STATUSES))
        ).all()
    )
    return BarListResponse(
        items=[
            BarListItem(
                barId=bar.id,
                name=bar.name,
                address=bar.address,
                latitude=float(bar.latitude),
                longitude=float(bar.longitude),
                phone=bar.phone,
                status=bar.status.value,
                activeMenuImport=(
                    ActiveMenuImport(menuImportId=unfinished[bar.id].id, status=unfinished[bar.id].status.value)
                    if bar.id in unfinished
                    else None
                ),
            )
            for bar in page
        ],
        nextCursor=encode_cursor([page[-1].name, str(page[-1].id)]) if more else None,
    )


def list_menu_imports(
    session: Session,
    bar_id: str,
    *,
    status: ImportStatusFilter = "all",
    limit: int = 20,
    cursor: str | None = None,
) -> MenuImportListResponse:
    """A bar's imports, newest first. `active` means unfinished (uploaded, processing, ready_for_review)."""
    try:
        bar = session.get(Bar, UUID(bar_id))
    except ValueError:
        bar = None
    if bar is None:
        raise bar_not_found(bar_id)

    image_count = (
        select(func.count()).where(MenuImage.menu_import_id == MenuImport.id).correlate(MenuImport).scalar_subquery()
    )
    stmt = select(MenuImport, image_count).where(MenuImport.bar_id == bar.id)
    if status == "active":
        stmt = stmt.where(MenuImport.status.in_(UNFINISHED_STATUSES))
    elif status != "all":
        stmt = stmt.where(MenuImport.status == ImportStatus(status))
    if cursor is not None:
        after = decode_cursor(cursor, _import_key)
        stmt = stmt.where(tuple_(MenuImport.created_at, MenuImport.id) < tuple_(*after))
    rows = session.execute(
        stmt.order_by(MenuImport.created_at.desc(), MenuImport.id.desc()).limit(limit + 1)
    ).all()
    page, more = rows[:limit], len(rows) > limit
    last = page[-1][0] if page else None
    return MenuImportListResponse(
        items=[
            MenuImportListItem(
                menuImportId=menu_import.id,
                mode=menu_import.mode,
                status=menu_import.status,
                imageCount=count,
                reviewVersion=menu_import.review_version,
                ownerNote=menu_import.owner_note,
                createdAt=menu_import.created_at,
                completedAt=menu_import.completed_at,
            )
            for menu_import, count in page
        ],
        nextCursor=encode_cursor([last.created_at.isoformat(), str(last.id)]) if more else None,
    )
