"""Find active bars by part of their name or address (API spec, section 3.11.11).

Used to pick one's bar in an owner application and to find a bar on the customer map. The query
is matched as typed (after trimming), ignoring letter case; `%` and `_` are plain characters.
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Bar, BarStatus
from app.schemas.search import BarNameItem, BarNamesResponse
from app.services.search import validate_query_text

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def search_bar_names(session: Session, query: str, limit: int = DEFAULT_LIMIT) -> BarNamesResponse:
    text = validate_query_text(query)
    rows = session.execute(
        select(Bar.id, Bar.name, Bar.address, Bar.latitude, Bar.longitude)
        .where(
            Bar.status == BarStatus.ACTIVE,
            or_(Bar.name.icontains(text, autoescape=True), Bar.address.icontains(text, autoescape=True)),
        )
        .order_by(Bar.name, Bar.id)
        .limit(limit + 1)  # one more than asked tells whether there are more
    ).all()
    items = [
        BarNameItem(
            barId=bar_id,
            name=name,
            address=address,
            latitude=float(latitude),
            longitude=float(longitude),
            # Bar owners (bar_owners) come in Iteration 3; until then no bar has one.
            hasOwner=False,
        )
        for bar_id, name, address, latitude, longitude in rows[:limit]
    ]
    return BarNamesResponse(items=items, truncated=len(rows) > limit)
