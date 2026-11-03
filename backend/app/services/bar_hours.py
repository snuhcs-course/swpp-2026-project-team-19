"""Opening hours and temporary closures in the bar responses (API spec 3.15), and the rules of the
weekly hours and tags that PATCH /api/bars/{barId} sends (3.7, 3.15.1).

The server sends the hours and the closure, never an open or closed status: the app computes that
from the device clock (3.15.5). A closure is sent through the day after its `end_date`, which the
app needs for the status early that morning, and hidden from the day after that (3.15.4). Ended
rows are not deleted; the next apply or cancel replaces or deletes them.
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import BarOperatingException, BarWeeklyHours
from app.schemas.bar_hours import OperatingException, WeeklyHours, WeeklyHoursInput
from app.services.request_limits import kst_date


def seoul_today() -> date:
    """Today's date in Seoul, which the dates of the hours and closures are in."""
    return kst_date(datetime.now(timezone.utc))


def weekly_hours_by_bar(session: Session, bar_ids: Sequence[UUID]) -> dict[UUID, list[WeeklyHours]]:
    hours: dict[UUID, list[WeeklyHours]] = {bar_id: [] for bar_id in bar_ids}
    rows = session.scalars(
        select(BarWeeklyHours)
        .where(BarWeeklyHours.bar_id.in_(bar_ids))
        .order_by(BarWeeklyHours.bar_id, BarWeeklyHours.day_of_week)
    )
    for row in rows:
        hours[row.bar_id].append(
            WeeklyHours(dayOfWeek=row.day_of_week, closed=row.is_closed, openTime=row.open_time, closeTime=row.close_time)
        )
    return hours


def operating_exceptions_by_bar(
    session: Session, bar_ids: Sequence[UUID], today: date
) -> dict[UUID, OperatingException]:
    """The closures still sent: those whose `end_date` is yesterday or later."""
    rows = session.scalars(
        select(BarOperatingException).where(
            BarOperatingException.bar_id.in_(bar_ids), BarOperatingException.end_date >= today - timedelta(days=1)
        )
    )
    return {
        row.bar_id: OperatingException(
            kind=row.kind.value,
            startDate=row.start_date,
            endDate=row.end_date,
            openTime=row.open_time,
            closeTime=row.close_time,
            note=row.note,
        )
        for row in rows
    }


# ---- PATCH /api/bars/{barId}: the rules that compare fields ----


def _error(path: str, code: str, message: str) -> dict[str, str]:
    return {"path": path, "code": code, "message": message}


def tag_errors(tags: list[str]) -> list[dict[str, str]]:
    """A tag equal to an earlier one ignoring case is `DUPLICATE_TAG` (spec 3.7)."""
    seen: set[str] = set()
    errors = []
    for index, tag in enumerate(tags):
        key = tag.casefold()
        if key in seen:
            errors.append(_error(f"tags[{index}]", "DUPLICATE_TAG", "같은 태그가 이미 있습니다."))
        seen.add(key)
    return errors


def weekly_hours_errors(hours: list[WeeklyHoursInput]) -> list[dict[str, str]]:
    """The rules of spec 3.15.1 that the schema cannot check field by field."""
    seen: set[int] = set()
    errors = []
    for index, day in enumerate(hours):
        path = f"weeklyHours[{index}]"
        if day.dayOfWeek in seen:
            errors.append(_error(f"{path}.dayOfWeek", "DUPLICATE_DAY", "같은 요일이 두 번 있습니다."))
        seen.add(day.dayOfWeek)
        if day.closed:
            for field in ("openTime", "closeTime"):
                if getattr(day, field) is not None:
                    errors.append(_error(f"{path}.{field}", "TIME_ON_CLOSED_DAY", "휴무일에는 영업시간을 보내지 않습니다."))
            continue
        missing = [field for field in ("openTime", "closeTime") if getattr(day, field) is None]
        for field in missing:
            errors.append(_error(f"{path}.{field}", "MISSING", "영업일에는 시작과 종료 시각이 필요합니다."))
        if not missing and day.openTime == day.closeTime:
            errors.append(_error(f"{path}.closeTime", "SAME_OPEN_CLOSE", "시작과 종료 시각이 같을 수 없습니다."))
    return errors


def replace_weekly_hours(session: Session, bar_id: UUID, hours: list[WeeklyHoursInput]) -> bool:
    """Make the bar's regular hours exactly `hours`; True when that changed them. The caller holds the
    bar row lock, so two requests never replace the rows at the same time."""
    new = sorted((day.dayOfWeek, day.closed, day.openTime, day.closeTime) for day in hours)
    old = [
        (row.day_of_week, row.is_closed, row.open_time, row.close_time)
        for row in session.scalars(
            select(BarWeeklyHours).where(BarWeeklyHours.bar_id == bar_id).order_by(BarWeeklyHours.day_of_week)
        )
    ]
    if new == old:
        return False
    session.execute(delete(BarWeeklyHours).where(BarWeeklyHours.bar_id == bar_id))
    session.add_all(
        BarWeeklyHours(bar_id=bar_id, day_of_week=day, is_closed=closed, open_time=open_time, close_time=close_time)
        for day, closed, open_time, close_time in new
    )
    return True
