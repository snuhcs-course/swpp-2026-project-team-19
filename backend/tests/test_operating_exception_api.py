"""PUT and DELETE /api/bars/{barId}/operating-exception: a bar's temporary closure (API spec 3.15.2 to
3.15.4), and how long it is sent in the bar responses (3.6, 3.9, 3.11.9).

Who may call them is in test_route_permissions.py. Dates are relative to the server's Seoul date.
"""

from datetime import datetime, time, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.errors import ApiError
from app.core.security import Principal
from app.models import BarOperatingException, BarOwner, BarStatus, OperatingExceptionKind, UserType
from app.schemas.bar_hours import ClosedTodayInput
from app.services.bar_hours import seoul_today
from app.services.operating_exception import apply_operating_exception
from tests.factories import make_bar, make_owner, make_user
from tests.sql_support import recorded_statements

OWNER_SUBJECT = "owner-subject"
OLD = datetime(2026, 1, 1, tzinfo=timezone.utc)


def day(offset: int = 0) -> str:
    return (seoul_today() + timedelta(days=offset)).isoformat()


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def bar(db_session):
    return make_bar(db_session, "관악 위스키 바")


@pytest.fixture
def owner_user(db_session, bar):
    user = make_user(db_session, OWNER_SUBJECT)
    make_owner(db_session, user, bar, make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR))
    return user


@pytest.fixture
def owner(supabase, owner_user):
    return {"Authorization": f"Bearer {supabase.token(sub=OWNER_SUBJECT)}"}


def put(client, headers, bar, body):
    return client.put(f"/api/bars/{bar.id}/operating-exception", headers=headers, json=body)


def cancel(client, headers, bar):
    return client.delete(f"/api/bars/{bar.id}/operating-exception", headers=headers)


def stored(db_session, bar) -> BarOperatingException | None:
    db_session.expire_all()
    return db_session.scalar(select(BarOperatingException).where(BarOperatingException.bar_id == bar.id))


def add_exception(db_session, bar, kind, start, end, open_time=None, close_time=None, note=None):
    row = BarOperatingException(
        bar_id=bar.id,
        kind=kind,
        start_date=seoul_today() + timedelta(days=start),
        end_date=seoul_today() + timedelta(days=end),
        open_time=open_time,
        close_time=close_time,
        note=note,
        created_at=OLD,
    )
    db_session.add(row)
    db_session.flush()
    return row


def field_errors(response) -> list[tuple[str, str]]:
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    return [(error["path"], error["code"]) for error in response.json()["error"]["fieldErrors"]]


# ---- applying (3.15.2) ----


def test_the_owner_closes_the_bar_today(client, db_session, bar, owner, owner_user):
    response = put(client, owner, bar, {"kind": "closed_today", "date": day(), "note": "  내부 공사로 쉽니다 "})

    assert response.status_code == 200, response.text
    assert response.json()["operatingException"] == {
        "kind": "closed_today",
        "startDate": day(),
        "endDate": day(),
        "openTime": None,
        "closeTime": None,
        "note": "내부 공사로 쉽니다",
    }
    row = stored(db_session, bar)
    assert (row.kind, row.created_by_user_id) == (OperatingExceptionKind.CLOSED_TODAY, owner_user.id)
    assert row.created_at is not None


def test_todays_hours_may_end_past_midnight(client, db_session, bar, operator):
    response = put(client, operator, bar, {"kind": "custom_hours", "date": day(), "openTime": "20:00", "closeTime": "01:00"})

    assert response.status_code == 200, response.text
    sent = response.json()["operatingException"]
    assert (sent["kind"], sent["startDate"], sent["endDate"]) == ("custom_hours", day(), day())
    assert (sent["openTime"], sent["closeTime"], sent["note"]) == ("20:00", "01:00", None)
    row = stored(db_session, bar)
    assert (row.open_time, row.close_time) == (time(20), time(1))
    # A temporary-login operator has no users row.
    assert row.created_by_user_id is None


@pytest.mark.parametrize(("start", "end"), [(0, 0), (3, 5)])
def test_a_vacation_today_or_later_is_sent_before_it_starts(client, db_session, bar, owner, start, end):
    response = put(client, owner, bar, {"kind": "vacation", "startDate": day(start), "endDate": day(end), "note": None})

    assert response.status_code == 200, response.text
    sent = response.json()["operatingException"]
    assert (sent["kind"], sent["startDate"], sent["endDate"]) == ("vacation", day(start), day(end))


def test_applying_replaces_the_current_closure(client, db_session, bar, owner):
    planned = add_exception(db_session, bar, OperatingExceptionKind.VACATION, 3, 5, note="휴가")

    response = put(client, owner, bar, {"kind": "closed_today", "date": day()})

    assert response.json()["operatingException"]["kind"] == "closed_today"
    row = stored(db_session, bar)
    assert row.id == planned.id
    assert (row.kind, row.end_date, row.note) == (OperatingExceptionKind.CLOSED_TODAY, seoul_today(), None)
    assert row.created_at != OLD
    count = db_session.scalar(select(func.count()).select_from(BarOperatingException))
    assert count == 1


def test_a_retry_after_midnight_changes_nothing(client, db_session, bar, owner):
    """The same request sent again once its date has passed skips the date checks (3.15.2)."""
    row = add_exception(db_session, bar, OperatingExceptionKind.CUSTOM_HOURS, -1, -1, time(20), time(1), "늦게 엽니다")
    body = {"kind": "custom_hours", "date": day(-1), "openTime": "20:00", "closeTime": "01:00", "note": " 늦게 엽니다 "}

    response = put(client, owner, bar, body)

    assert response.status_code == 200, response.text
    assert response.json()["operatingException"]["startDate"] == day(-1)
    assert (stored(db_session, bar).id, stored(db_session, bar).created_at) == (row.id, OLD)


def test_a_retried_vacation_that_has_started_changes_nothing(client, db_session, bar, owner):
    add_exception(db_session, bar, OperatingExceptionKind.VACATION, -2, 1)

    response = put(client, owner, bar, {"kind": "vacation", "startDate": day(-2), "endDate": day(1)})

    assert response.status_code == 200, response.text
    assert stored(db_session, bar).created_at == OLD


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"kind": "closed_today", "date": "DAY", "note": "다른 문구"}, id="another note"),
        pytest.param({"kind": "custom_hours", "date": "DAY", "openTime": "20:00", "closeTime": "02:00"}, id="other times"),
    ],
)
def test_a_changed_request_for_yesterday_is_not_today(client, db_session, bar, owner, body):
    add_exception(db_session, bar, OperatingExceptionKind.CUSTOM_HOURS, -1, -1, time(20), time(1))

    response = put(client, owner, bar, {**body, "date": day(-1)})

    assert field_errors(response) == [("date", "DATE_NOT_TODAY")]
    assert stored(db_session, bar).created_at == OLD


@pytest.mark.parametrize("offset", [-1, 1])
def test_only_today_can_be_closed(client, db_session, bar, owner, offset):
    response = put(client, owner, bar, {"kind": "closed_today", "date": day(offset)})

    assert field_errors(response) == [("date", "DATE_NOT_TODAY")]
    assert stored(db_session, bar) is None


def test_a_vacation_cannot_start_in_the_past(client, db_session, bar, owner):
    response = put(client, owner, bar, {"kind": "vacation", "startDate": day(-1), "endDate": day(2)})

    assert field_errors(response) == [("startDate", "DATE_IN_PAST")]
    assert stored(db_session, bar) is None


@pytest.mark.parametrize(
    ("body", "errors"),
    [
        ({"date": "DAY"}, [("", "UNION_TAG_NOT_FOUND")]),
        ({"kind": "holiday", "date": "DAY"}, [("", "UNION_TAG_INVALID")]),
        ({"kind": "closed_today"}, [("date", "MISSING")]),
        ({"kind": "closed_today", "date": "DAY", "openTime": "20:00"}, [("openTime", "EXTRA_FORBIDDEN")]),
        ({"kind": "vacation", "startDate": "DAY", "endDate": "DAY", "date": "DAY"}, [("date", "EXTRA_FORBIDDEN")]),
        ({"kind": "custom_hours", "date": "DAY", "openTime": "20:00"}, [("closeTime", "MISSING")]),
        ({"kind": "custom_hours", "date": "DAY", "openTime": "20:07", "closeTime": "01:00"}, [("openTime", "INVALID_TIME")]),
        ({"kind": "custom_hours", "date": "DAY", "openTime": "20:00", "closeTime": "20:00"}, [("closeTime", "SAME_OPEN_CLOSE")]),
        ({"kind": "vacation", "startDate": "DAY+2", "endDate": "DAY+1"}, [("endDate", "END_BEFORE_START")]),
        ({"kind": "closed_today", "date": "2026/11/06"}, [("date", "DATE_FROM_DATETIME_PARSING")]),
        ({"kind": "closed_today", "date": "2026-02-30"}, [("date", "DATE_FROM_DATETIME_PARSING")]),
        ({"kind": "closed_today", "date": 20261106}, [("date", "DATE_FROM_DATETIME_PARSING")]),
        ({"kind": "closed_today", "date": "DAY", "note": "가" * 101}, [("note", "STRING_TOO_LONG")]),
        ({"kind": "closed_today", "date": "DAY", "note": "첫 줄\n둘째 줄"}, [("note", "INVALID_CHARACTER")]),
    ],
)
def test_request_rules(client, db_session, bar, owner, body, errors):
    dates = {"DAY": day(), "DAY+1": day(1), "DAY+2": day(2)}
    body = {key: dates.get(value, value) if isinstance(value, str) else value for key, value in body.items()}

    assert field_errors(put(client, owner, bar, body)) == errors
    assert stored(db_session, bar) is None


def test_a_blank_note_is_null(client, db_session, bar, owner):
    response = put(client, owner, bar, {"kind": "closed_today", "date": day(), "note": "   "})

    assert response.json()["operatingException"]["note"] is None


def test_a_note_of_100_characters_fits(client, db_session, bar, owner):
    response = put(client, owner, bar, {"kind": "closed_today", "date": day(), "note": "가" * 100})

    assert response.status_code == 200, response.text


def test_an_inactive_bar_can_change_its_closure(client, db_session, bar, owner):
    bar.status = BarStatus.INACTIVE
    db_session.flush()

    assert put(client, owner, bar, {"kind": "closed_today", "date": day()}).status_code == 200
    assert cancel(client, owner, bar).status_code == 200


def test_the_closure_does_not_move_updated_at(client, db_session, bar, owner):
    bar.updated_at = OLD
    db_session.flush()

    applied = put(client, owner, bar, {"kind": "closed_today", "date": day()})
    canceled = cancel(client, owner, bar)

    assert applied.json()["updatedAt"] == canceled.json()["updatedAt"] == "2026-01-01T00:00:00Z"


def test_the_closure_is_changed_under_the_bar_lock(client, db_session, bar, owner):
    with recorded_statements(db_session) as statements:
        assert put(client, owner, bar, {"kind": "closed_today", "date": day()}).status_code == 200

    lock = next(i for i, sql in enumerate(statements) if "FOR UPDATE" in sql)
    assert "FROM bars" in statements[lock]
    write = next(i for i, sql in enumerate(statements) if sql.startswith("INSERT INTO bar_operating_exceptions"))
    # Stamped by the clock after the lock, not the transaction start (now()).
    stamp = next(i for i, sql in enumerate(statements) if "clock_timestamp()" in sql)
    assert lock < write <= stamp


def test_an_owner_revoked_before_the_lock_is_forbidden(db_session, bar, owner_user):
    """The route found the caller to be the owner; the check under the lock refuses a revocation since."""
    ownership = db_session.scalar(select(BarOwner).where(BarOwner.user_id == owner_user.id))
    ownership.revoked_at, ownership.revoked_by_user_id = datetime.now(timezone.utc), owner_user.id
    db_session.flush()
    caller = Principal(kind="supabase", subject=OWNER_SUBJECT, claims={})

    with pytest.raises(ApiError) as caught:
        apply_operating_exception(
            db_session, caller, bar, ClosedTodayInput(kind="closed_today", date=day()), base_url=""
        )

    assert (caught.value.status_code, caught.value.code) == (403, "FORBIDDEN")
    assert stored(db_session, bar) is None


# ---- canceling (3.15.3) ----


def test_canceling_deletes_the_closure(client, db_session, bar, owner):
    add_exception(db_session, bar, OperatingExceptionKind.VACATION, 0, 3)

    response = cancel(client, owner, bar)

    assert response.status_code == 200, response.text
    assert response.json()["operatingException"] is None
    assert stored(db_session, bar) is None


def test_canceling_without_a_closure_is_fine(client, db_session, bar, owner):
    first, again = cancel(client, owner, bar), cancel(client, owner, bar)

    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json()["operatingException"] is None


# ---- how long it is sent (3.15.4) ----


def sent_everywhere(client, bar, headers) -> list:
    """`operatingException` in the bar detail (3.6), the customer bar menu (3.9) and my bars (3.11.9)."""
    [mine] = client.get("/api/me/bars", headers=headers).json()["items"]
    return [
        client.get(f"/api/bars/{bar.id}", headers=headers).json()["operatingException"],
        client.get(f"/api/bars/{bar.id}/menu").json()["operatingException"],
        mine["operatingException"],
    ]


@pytest.mark.parametrize(
    ("kind", "start", "end"),
    [
        pytest.param(OperatingExceptionKind.VACATION, 5, 7, id="not started"),
        pytest.param(OperatingExceptionKind.VACATION, -3, 2, id="running"),
        pytest.param(OperatingExceptionKind.CLOSED_TODAY, 0, 0, id="today"),
        pytest.param(OperatingExceptionKind.CLOSED_TODAY, -1, -1, id="ended yesterday"),
    ],
)
def test_a_closure_is_sent_through_the_day_after_it_ends(client, db_session, bar, owner, kind, start, end):
    add_exception(db_session, bar, kind, start, end)

    assert [sent and (sent["kind"], sent["endDate"]) for sent in sent_everywhere(client, bar, owner)] == [
        (kind.value, day(end))
    ] * 3


def test_a_closure_that_ended_before_yesterday_is_not_sent(client, db_session, bar, owner):
    add_exception(db_session, bar, OperatingExceptionKind.VACATION, -5, -2)

    assert sent_everywhere(client, bar, owner) == [None, None, None]
    # The row stays until the next apply or cancel replaces or deletes it.
    assert stored(db_session, bar) is not None


def test_a_hidden_closure_is_replaced_by_the_next_one(client, db_session, bar, owner):
    add_exception(db_session, bar, OperatingExceptionKind.CLOSED_TODAY, -2, -2)

    response = put(client, owner, bar, {"kind": "closed_today", "date": day()})

    assert response.json()["operatingException"]["startDate"] == day()
