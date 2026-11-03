"""Applying and canceling a bar's temporary closure (API spec 3.15.2, 3.15.3).

A bar has at most one closure; applying one replaces it, canceling deletes it. Inactive bars may
change theirs too (as with 3.7). Both take the bar row lock and check the caller again under it, so
an owner revoked meanwhile is refused and two applies run one after the other.

"Today" is the Seoul date when the request arrives. A request whose content equals the stored
closure changes nothing and skips the date checks, so a request retried after midnight still gets
`200` (3.15.2).
"""

from datetime import date, time

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import validation_failed
from app.core.security import Principal
from app.models import Bar, BarOperatingException, OperatingExceptionKind
from app.schemas.bar import BarDetail
from app.schemas.bar_hours import ClosedTodayInput, CustomHoursInput, OperatingExceptionInput, VacationInput
from app.services.bar_access import lock_bar_for_manager
from app.services.bar_detail import get_bar_detail
from app.services.bar_hours import seoul_today
from app.services.users import caller_user_id

_Values = tuple[OperatingExceptionKind, date, date, time | None, time | None, str | None]


def check_request(body: OperatingExceptionInput) -> None:
    """The rules that compare fields of the request on its own."""
    if isinstance(body, CustomHoursInput) and body.openTime == body.closeTime:
        raise validation_failed("closeTime", "SAME_OPEN_CLOSE", "시작과 종료 시각이 같을 수 없습니다.")
    if isinstance(body, VacationInput) and body.endDate < body.startDate:
        raise validation_failed("endDate", "END_BEFORE_START", "종료일은 시작일보다 빠를 수 없습니다.")


def _values(body: OperatingExceptionInput) -> _Values:
    kind = OperatingExceptionKind(body.kind)
    if isinstance(body, VacationInput):
        return kind, body.startDate, body.endDate, None, None, body.note
    if isinstance(body, CustomHoursInput):
        return kind, body.date, body.date, body.openTime, body.closeTime, body.note
    return kind, body.date, body.date, None, None, body.note


def _check_dates(body: OperatingExceptionInput, today: date) -> None:
    if isinstance(body, (ClosedTodayInput, CustomHoursInput)) and body.date != today:
        raise validation_failed("date", "DATE_NOT_TODAY", "날짜가 바뀌었습니다. 다시 적용해 주세요.")
    if isinstance(body, VacationInput) and body.startDate < today:
        raise validation_failed("startDate", "DATE_IN_PAST", "지난 날짜부터 시작할 수 없습니다.")


def apply_operating_exception(
    session: Session, principal: Principal, bar: Bar, body: OperatingExceptionInput
) -> BarDetail:
    """Replace the bar's closure with the request's (3.15.2); the bar as in spec 3.6."""
    today = seoul_today()
    check_request(body)
    lock_bar_for_manager(session, principal, bar.id)
    values = _values(body)
    current = session.scalar(select(BarOperatingException).where(BarOperatingException.bar_id == bar.id))
    stored = (
        (current.kind, current.start_date, current.end_date, current.open_time, current.close_time, current.note)
        if current is not None
        else None
    )
    if stored != values:
        _check_dates(body, today)
        if current is None:
            current = BarOperatingException(bar_id=bar.id)
            session.add(current)
        (
            current.kind,
            current.start_date,
            current.end_date,
            current.open_time,
            current.close_time,
            current.note,
        ) = values
        current.created_by_user_id = caller_user_id(session, principal)
        # clock_timestamp(), not now(): an apply that waited for the lock must not look older than the one before.
        current.created_at = func.clock_timestamp()
    # Also ends the transaction of an unchanged retry, releasing the lock.
    session.commit()
    return get_bar_detail(session, bar)


def cancel_operating_exception(session: Session, principal: Principal, bar: Bar) -> BarDetail:
    """Delete the bar's closure, if any (3.15.3); the bar as in spec 3.6."""
    lock_bar_for_manager(session, principal, bar.id)
    session.execute(delete(BarOperatingException).where(BarOperatingException.bar_id == bar.id))
    session.commit()
    return get_bar_detail(session, bar)
