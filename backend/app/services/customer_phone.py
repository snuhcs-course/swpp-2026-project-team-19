"""The phone customers see for a bar (API spec 3.9, also shown to its managers in 3.6).

The bar's own phone comes first. Only when the bar has none, the contact phone of its current owner is
shown, and only if they agreed to that when applying (`contactPhonePublic`, spec 3.11.2). The number is
read through the current `bar_owners` row, so it disappears as soon as the owner is removed (3.11.10),
and a pending, rejected or canceled application, which has no such row, is never used. A bar has at most
one current owner (`uq_bar_owners_current_bar_id`).
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bar, BarOwner, BarOwnerApplication
from app.schemas.bar import PhoneSource

CustomerPhone = tuple[str | None, PhoneSource | None]


def customer_phones(session: Session, bars: Sequence[Bar]) -> dict[UUID, CustomerPhone]:
    """`(phone, source)` for each bar; `(None, None)` when customers see no phone. One query at most,
    and none when every bar has its own phone."""
    without_phone = [bar.id for bar in bars if not bar.phone]
    owner_phones: dict[UUID, str] = {}
    if without_phone:
        owner_phones = dict(
            session.execute(
                select(BarOwner.bar_id, BarOwnerApplication.contact_phone)
                .join(BarOwnerApplication, BarOwnerApplication.id == BarOwner.application_id)
                .where(
                    BarOwner.bar_id.in_(without_phone),
                    BarOwner.revoked_at.is_(None),
                    BarOwnerApplication.contact_phone_public.is_(True),
                )
            ).all()
        )
    result: dict[UUID, CustomerPhone] = {}
    for bar in bars:
        if bar.phone:
            result[bar.id] = (bar.phone, "bar")
        elif bar.id in owner_phones:
            result[bar.id] = (owner_phones[bar.id], "owner_contact")
        else:
            result[bar.id] = (None, None)
    return result
