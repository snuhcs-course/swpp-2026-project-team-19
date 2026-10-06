"""Operator lookups: the bar list (API spec 3.4)."""

from typing import Literal
from uuid import UUID

from sqlalchemy import or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.pagination import decode_cursor, encode_cursor
from app.models import Bar, BarStatus, MenuImport
from app.schemas.bar import ActiveMenuImport, BarListItem, BarListResponse
from app.services.menu_import_upload import UNFINISHED_STATUSES
from app.services.search import validate_query_text

BarStatusFilter = Literal["active", "inactive", "all"]


def _text(value) -> str:
    if not isinstance(value, str):
        raise TypeError("expected a string")
    return value


def _bar_key(values: list) -> tuple[str, UUID]:
    name, bar_id = values
    return _text(name), UUID(_text(bar_id))


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
