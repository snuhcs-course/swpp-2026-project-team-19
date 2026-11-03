"""The bars columns, bar_weekly_hours and bar_operating_exceptions enforce the rules of
docs/schema_guide.md 5.2, 5.6 and 5.7 in the database, whatever the API lets through."""

from datetime import date, time

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import BarOperatingException, BarWeeklyHours, OperatingExceptionKind
from tests.factories import make_bar

DAY = date(2026, 11, 6)


def test_a_new_bar_has_no_description_pour_or_tags(db_session):
    bar = make_bar(db_session)
    db_session.refresh(bar)

    assert (bar.description, bar.default_pour_ml, bar.tags) == (None, None, [])


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"default_pour_ml": 0}, id="pour below 1"),
        pytest.param({"default_pour_ml": 1000}, id="pour above 999"),
        pytest.param({"tags": ["a", "b", "c", "d", "e", "f"]}, id="six tags"),
    ],
)
def test_bar_checks(db_session, change):
    bar = make_bar(db_session)

    for name, value in change.items():
        setattr(bar, name, value)
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    ("day", "closed", "open_time", "close_time"),
    [
        pytest.param(5, False, time(18), time(2), id="past midnight"),
        pytest.param(1, True, None, None, id="day off"),
    ],
)
def test_valid_weekly_hours(db_session, day, closed, open_time, close_time):
    db_session.add(
        BarWeeklyHours(
            bar_id=make_bar(db_session).id, day_of_week=day, is_closed=closed, open_time=open_time, close_time=close_time
        )
    )
    db_session.flush()


@pytest.mark.parametrize(
    ("day", "closed", "open_time", "close_time"),
    [
        pytest.param(0, False, time(18), time(2), id="day 0"),
        pytest.param(8, False, time(18), time(2), id="day 8"),
        pytest.param(5, True, time(18), None, id="day off with a time"),
        pytest.param(5, False, time(18), None, id="open day without a close"),
        pytest.param(5, False, time(18), time(18), id="same open and close"),
    ],
)
def test_weekly_hours_checks(db_session, day, closed, open_time, close_time):
    db_session.add(
        BarWeeklyHours(
            bar_id=make_bar(db_session).id, day_of_week=day, is_closed=closed, open_time=open_time, close_time=close_time
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_one_row_per_weekday(db_session):
    bar = make_bar(db_session)
    db_session.add(BarWeeklyHours(bar_id=bar.id, day_of_week=5, is_closed=True))
    db_session.flush()
    db_session.add(BarWeeklyHours(bar_id=bar.id, day_of_week=5, is_closed=True))
    with pytest.raises(IntegrityError):
        db_session.flush()


def exception(bar, kind, start=DAY, end=DAY, open_time=None, close_time=None) -> BarOperatingException:
    return BarOperatingException(
        bar_id=bar.id, kind=kind, start_date=start, end_date=end, open_time=open_time, close_time=close_time
    )


@pytest.mark.parametrize(
    "values",
    [
        pytest.param((OperatingExceptionKind.CLOSED_TODAY,), id="closed_today"),
        pytest.param((OperatingExceptionKind.CUSTOM_HOURS, DAY, DAY, time(20), time(1)), id="custom_hours"),
        pytest.param((OperatingExceptionKind.VACATION, DAY, date(2026, 11, 9)), id="vacation"),
    ],
)
def test_valid_operating_exceptions(db_session, values):
    row = exception(make_bar(db_session), *values)
    db_session.add(row)
    db_session.flush()
    db_session.refresh(row)

    assert row.created_at is not None


@pytest.mark.parametrize(
    "values",
    [
        pytest.param((OperatingExceptionKind.VACATION, DAY, date(2026, 11, 5)), id="end before start"),
        pytest.param((OperatingExceptionKind.CLOSED_TODAY, DAY, date(2026, 11, 7)), id="closed_today over two days"),
        pytest.param((OperatingExceptionKind.CUSTOM_HOURS, DAY, date(2026, 11, 7), time(20), time(1)), id="custom_hours over two days"),
        pytest.param((OperatingExceptionKind.CUSTOM_HOURS,), id="custom_hours without times"),
        pytest.param((OperatingExceptionKind.CUSTOM_HOURS, DAY, DAY, time(20), time(20)), id="custom_hours same times"),
        pytest.param((OperatingExceptionKind.CLOSED_TODAY, DAY, DAY, time(20), time(1)), id="closed_today with times"),
    ],
)
def test_operating_exception_checks(db_session, values):
    db_session.add(exception(make_bar(db_session), *values))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_one_operating_exception_per_bar(db_session):
    bar = make_bar(db_session)
    db_session.add(exception(bar, OperatingExceptionKind.CLOSED_TODAY))
    db_session.flush()
    db_session.add(exception(bar, OperatingExceptionKind.VACATION))
    with pytest.raises(IntegrityError):
        db_session.flush()
