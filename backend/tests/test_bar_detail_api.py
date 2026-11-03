"""GET and PATCH /api/bars/{barId}: a bar with its management state, and editing it (API spec 3.6, 3.7).

Who may call them is in test_route_permissions.py; here an operator and the bar's owner use them.
"""

from datetime import datetime, time, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Bar, BarStatus, BarWeeklyHours, ImportMode, ImportStatus, MenuImport, UserType
from tests.factories import make_bar, make_brand, make_owner, make_product, make_user, publish_menu
from tests.sql_support import recorded_statements

OWNER_SUBJECT = "owner-subject"
DETAIL_FIELDS = {
    "barId",
    "name",
    "address",
    "latitude",
    "longitude",
    "phone",
    "description",
    "defaultPourMl",
    "tags",
    "weeklyHours",
    "operatingException",
    "photos",
    "status",
    "activeMenuImport",
    "currentMenu",
    "owner",
    "createdAt",
    "updatedAt",
}


def rfc3339(value) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def bar(db_session):
    return make_bar(db_session, "관악 위스키 바", latitude="37.478321", longitude="126.951234")


@pytest.fixture
def owner(db_session, supabase, bar):
    """Headers of the bar's current owner, a Supabase customer."""
    user = make_user(db_session, OWNER_SUBJECT, email="owner@example.com", display_name="김사장")
    reviewer = make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)
    make_owner(db_session, user, bar, reviewer)
    return {"Authorization": f"Bearer {supabase.token(sub=OWNER_SUBJECT)}"}


def patch(client, headers, bar, body):
    return client.patch(f"/api/bars/{bar.id}", headers=headers, json=body)


def reload(db_session, bar) -> Bar:
    db_session.expire_all()
    return db_session.get(Bar, bar.id)


# ---- GET ----


def test_the_owner_reads_the_bar_with_its_management_state(client, db_session, bar, owner):
    brand = make_brand(db_session, "Glenfiddich")
    board = publish_menu(db_session, bar, [(make_product(db_session, brand, "Glenfiddich 12"), "글렌피딕 12년", [(None, 30, 17000)])])
    menu_import = MenuImport(
        idempotency_key="k", request_fingerprint="0" * 64, bar_id=bar.id, mode=ImportMode.PARTIAL_UPDATE,
        status=ImportStatus.READY_FOR_REVIEW,
    )
    db_session.add(menu_import)
    db_session.flush()

    response = client.get(f"/api/bars/{bar.id}", headers=owner)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == DETAIL_FIELDS
    assert body["barId"] == str(bar.id)
    assert (body["name"], body["latitude"], body["longitude"]) == ("관악 위스키 바", 37.478321, 126.951234)
    assert body["activeMenuImport"] == {"menuImportId": str(menu_import.id), "status": "ready_for_review"}
    assert body["currentMenu"] == {
        "menuBoardId": str(board.id),
        "menuVersion": 1,
        "publishedAt": rfc3339(board.published_at),
        "confirmedAt": None,
    }
    assert body["owner"]["email"] == "owner@example.com"
    assert body["owner"]["displayName"] == "김사장"


def test_an_inactive_bar_is_returned(client, db_session, bar, operator):
    bar.status = BarStatus.INACTIVE
    db_session.flush()

    response = client.get(f"/api/bars/{bar.id}", headers=operator)

    assert response.status_code == 200
    assert response.json()["status"] == "inactive"
    assert response.json()["owner"] is None


@pytest.mark.parametrize("bar_id", ["99999999-9999-4999-8999-999999999999", "not-a-uuid"])
def test_an_unknown_bar_is_not_found(client, operator, bar_id):
    response = client.get(f"/api/bars/{bar_id}", headers=operator)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BAR_NOT_FOUND"
    assert response.json()["error"]["details"] == {"barId": bar_id}


# ---- PATCH ----


def test_the_owner_edits_the_fields_sent(client, db_session, bar, owner):
    bar.phone = "02-000-0000"
    db_session.flush()

    response = patch(client, owner, bar, {"name": "  관악 위스키 하우스 ", "phone": "02-111-2222"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == DETAIL_FIELDS
    assert (body["name"], body["phone"], body["address"]) == ("관악 위스키 하우스", "02-111-2222", bar.address)
    stored = reload(db_session, bar)
    assert (stored.name, stored.phone) == ("관악 위스키 하우스", "02-111-2222")


@pytest.mark.parametrize("phone", [None, "   "])
def test_null_or_blank_phone_removes_it(client, db_session, bar, owner, phone):
    bar.phone = "02-000-0000"
    db_session.flush()

    response = patch(client, owner, bar, {"phone": phone})

    assert response.status_code == 200
    assert response.json()["phone"] is None
    assert reload(db_session, bar).phone is None


def test_a_new_address_moves_the_bar_with_its_coordinates(client, db_session, bar, owner):
    body = {"address": "서울특별시 관악구 신림로 2", "latitude": 37.4812345, "longitude": 126.9523}

    response = patch(client, owner, bar, body)

    assert response.status_code == 200, response.text
    stored = reload(db_session, bar)
    assert stored.address == "서울특별시 관악구 신림로 2"
    # Stored to 6 decimal places.
    assert (stored.latitude, stored.longitude) == (Decimal("37.481235"), Decimal("126.952300"))


def test_coordinates_alone_correct_the_position(client, db_session, bar, owner):
    response = patch(client, owner, bar, {"latitude": 37.5, "longitude": 127.0})

    assert response.status_code == 200
    stored = reload(db_session, bar)
    assert (stored.latitude, stored.longitude, stored.address) == (Decimal("37.5"), Decimal("127.0"), bar.address)


def test_an_empty_body_changes_nothing(client, db_session, bar, owner):
    before = client.get(f"/api/bars/{bar.id}", headers=owner).json()

    response = patch(client, owner, bar, {})

    assert response.status_code == 200
    assert response.json() == before


def test_the_operator_deactivates_the_bar(client, db_session, bar, operator):
    response = patch(client, operator, bar, {"status": "inactive"})

    assert response.status_code == 200
    assert response.json()["status"] == "inactive"
    assert reload(db_session, bar).status == BarStatus.INACTIVE
    # An inactive bar takes no new upload, even from the operator (spec 4.4).
    upload = client.post(
        f"/api/bars/{bar.id}/menu-imports",
        headers={**operator, "Idempotency-Key": "k"},
        data={"mode": "full_replace"},
        files=[("images", ("page.jpg", b"\xff\xd8\xff\xe0jpeg", "image/jpeg"))],
    )
    assert upload.json()["error"]["code"] == "BAR_NOT_FOUND"


@pytest.mark.parametrize("status", ["inactive", "active"])
def test_an_owner_cannot_change_the_status(client, db_session, bar, owner, status):
    response = patch(client, owner, bar, {"status": status, "name": "Renamed"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    stored = reload(db_session, bar)
    assert (stored.status, stored.name) == (BarStatus.ACTIVE, "관악 위스키 바")


@pytest.mark.parametrize(
    ("body", "errors"),
    [
        ({"name": None}, [("name", "NULL_NOT_ALLOWED")]),
        ({"address": None, "latitude": 37.5, "longitude": 127.0}, [("address", "NULL_NOT_ALLOWED")]),
        ({"status": None}, [("status", "NULL_NOT_ALLOWED")]),
        ({"name": "   "}, [("name", "STRING_TOO_SHORT")]),
        ({"name": "가" * 151}, [("name", "STRING_TOO_LONG")]),
        ({"phone": "0" * 31}, [("phone", "STRING_TOO_LONG")]),
        ({"latitude": 91, "longitude": 127.0}, [("latitude", "LESS_THAN_EQUAL")]),
        ({"status": "closed"}, [("status", "LITERAL_ERROR")]),
        ({"ownerId": "x"}, [("ownerId", "EXTRA_FORBIDDEN")]),
        ({"latitude": 37.5}, [("longitude", "LAT_LNG_REQUIRED_TOGETHER")]),
        ({"longitude": 127.0}, [("latitude", "LAT_LNG_REQUIRED_TOGETHER")]),
        (
            {"address": "서울특별시 관악구 신림로 2"},
            [("latitude", "COORDINATES_REQUIRED"), ("longitude", "COORDINATES_REQUIRED")],
        ),
    ],
)
def test_field_rules(client, db_session, bar, owner, body, errors):
    response = patch(client, owner, bar, body)

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert [(field["path"], field["code"]) for field in error["fieldErrors"]] == errors
    assert reload(db_session, bar).name == "관악 위스키 바"


def test_an_inactive_bar_can_be_edited_by_its_owner(client, db_session, bar, owner):
    bar.status = BarStatus.INACTIVE
    db_session.flush()

    response = patch(client, owner, bar, {"phone": "02-333-4444"})

    assert response.status_code == 200
    assert response.json()["phone"] == "02-333-4444"


# ---- PATCH: description, default pour, tags and weekly hours (spec 3.7, 3.15.1) ----

FRIDAY_LATE = {"dayOfWeek": 5, "closed": False, "openTime": "18:00", "closeTime": "02:00"}
MONDAY_OFF = {"dayOfWeek": 1, "closed": True, "openTime": None, "closeTime": None}
OLD = datetime(2026, 1, 1, tzinfo=timezone.utc)


def stored_hours(db_session, bar) -> list[tuple]:
    db_session.expire_all()
    rows = db_session.scalars(
        select(BarWeeklyHours).where(BarWeeklyHours.bar_id == bar.id).order_by(BarWeeklyHours.day_of_week)
    )
    return [(row.day_of_week, row.is_closed, row.open_time, row.close_time) for row in rows]


def test_the_owner_sets_the_bar_profile(client, db_session, bar, owner):
    body = {
        "description": "  싱글몰트 위주의\n조용한 바  ",
        "defaultPourMl": 30,
        "tags": [" 싱글몰트 ", "Peat", "조용한 분위기"],
        # A day off sent without times; days in any order.
        "weeklyHours": [FRIDAY_LATE, {"dayOfWeek": 1, "closed": True}],
    }

    response = patch(client, owner, bar, body)

    assert response.status_code == 200, response.text
    sent = response.json()
    assert sent["description"] == "싱글몰트 위주의\n조용한 바"
    assert sent["defaultPourMl"] == 30
    assert sent["tags"] == ["싱글몰트", "Peat", "조용한 분위기"]
    assert sent["weeklyHours"] == [MONDAY_OFF, FRIDAY_LATE]
    assert sent["operatingException"] is None
    stored = reload(db_session, bar)
    assert (stored.description, stored.default_pour_ml, stored.tags) == (
        "싱글몰트 위주의\n조용한 바",
        30,
        ["싱글몰트", "Peat", "조용한 분위기"],
    )
    assert stored_hours(db_session, bar) == [(1, True, None, None), (5, False, time(18), time(2))]
    assert client.get(f"/api/bars/{bar.id}", headers=owner).json() == sent


def test_customers_see_the_profile_but_not_the_default_pour(client, db_session, bar, owner):
    patch(client, owner, bar, {"description": "소개", "defaultPourMl": 30, "tags": ["싱글몰트"], "weeklyHours": [FRIDAY_LATE]})

    menu = client.get(f"/api/bars/{bar.id}/menu").json()

    assert (menu["description"], menu["tags"], menu["weeklyHours"]) == ("소개", ["싱글몰트"], [FRIDAY_LATE])
    assert "defaultPourMl" not in menu


def test_the_operator_sets_the_profile_too(client, db_session, bar, operator):
    response = patch(client, operator, bar, {"tags": ["버번"], "weeklyHours": [MONDAY_OFF]})

    assert response.status_code == 200, response.text
    assert (response.json()["tags"], response.json()["weeklyHours"]) == (["버번"], [MONDAY_OFF])


@pytest.mark.parametrize("description", [None, "  \n "])
def test_null_or_blank_description_removes_it(client, db_session, bar, owner, description):
    bar.description = "소개"
    db_session.flush()

    response = patch(client, owner, bar, {"description": description})

    assert response.status_code == 200
    assert response.json()["description"] is None
    assert reload(db_session, bar).description is None


def test_null_default_pour_removes_it(client, db_session, bar, owner):
    bar.default_pour_ml = 45
    db_session.flush()

    response = patch(client, owner, bar, {"defaultPourMl": None})

    assert response.json()["defaultPourMl"] is None
    assert reload(db_session, bar).default_pour_ml is None


def test_tags_and_hours_are_replaced_as_a_whole(client, db_session, bar, owner):
    patch(client, owner, bar, {"tags": ["a", "b"], "weeklyHours": [MONDAY_OFF, FRIDAY_LATE]})

    response = patch(client, owner, bar, {"tags": ["c"], "weeklyHours": [{**FRIDAY_LATE, "closeTime": "00:00"}]})

    assert response.json()["tags"] == ["c"]
    assert response.json()["weeklyHours"] == [{**FRIDAY_LATE, "closeTime": "00:00"}]
    assert stored_hours(db_session, bar) == [(5, False, time(18), time(0))]


def test_empty_arrays_remove_tags_and_hours(client, db_session, bar, owner):
    patch(client, owner, bar, {"tags": ["a"], "weeklyHours": [MONDAY_OFF]})

    response = patch(client, owner, bar, {"tags": [], "weeklyHours": []})

    assert (response.json()["tags"], response.json()["weeklyHours"]) == ([], [])
    assert reload(db_session, bar).tags == []
    assert stored_hours(db_session, bar) == []


def test_fields_left_out_keep_their_values(client, db_session, bar, owner):
    patch(client, owner, bar, {"description": "소개", "defaultPourMl": 30, "tags": ["a"], "weeklyHours": [MONDAY_OFF]})

    response = patch(client, owner, bar, {"phone": "02-555-5555"})

    sent = response.json()
    assert (sent["description"], sent["defaultPourMl"], sent["tags"], sent["weeklyHours"]) == ("소개", 30, ["a"], [MONDAY_OFF])


def test_changed_hours_move_updated_at(client, db_session, bar, owner):
    bar.updated_at = OLD
    db_session.flush()

    response = patch(client, owner, bar, {"weeklyHours": [FRIDAY_LATE]})

    assert response.json()["updatedAt"] != rfc3339(OLD)
    assert reload(db_session, bar).updated_at != OLD


def test_the_same_hours_again_change_nothing(client, db_session, bar, owner):
    patch(client, owner, bar, {"weeklyHours": [FRIDAY_LATE, MONDAY_OFF]})
    bar.updated_at = OLD
    db_session.flush()

    response = patch(client, owner, bar, {"weeklyHours": [MONDAY_OFF, FRIDAY_LATE]})

    assert response.json()["updatedAt"] == rfc3339(OLD)
    assert stored_hours(db_session, bar) == [(1, True, None, None), (5, False, time(18), time(2))]


def hours(**change) -> dict:
    return {"weeklyHours": [{**FRIDAY_LATE, **change}]}


@pytest.mark.parametrize(
    ("body", "errors"),
    [
        ({"description": "가" * 101}, [("description", "STRING_TOO_LONG")]),
        ({"defaultPourMl": 0}, [("defaultPourMl", "GREATER_THAN_EQUAL")]),
        ({"defaultPourMl": 1000}, [("defaultPourMl", "LESS_THAN_EQUAL")]),
        ({"tags": None}, [("tags", "NULL_NOT_ALLOWED")]),
        ({"tags": ["a", "b", "c", "d", "e", "f"]}, [("tags", "TOO_LONG")]),
        ({"tags": ["ok", "  "]}, [("tags[1]", "STRING_TOO_SHORT")]),
        ({"tags": ["가" * 25]}, [("tags[0]", "STRING_TOO_LONG")]),
        ({"tags": ["싱글\n몰트"]}, [("tags[0]", "INVALID_CHARACTER")]),
        ({"tags": ["a\tb"]}, [("tags[0]", "INVALID_CHARACTER")]),
        ({"tags": ["Peat", "x", "peat", "PEAT"]}, [("tags[2]", "DUPLICATE_TAG"), ("tags[3]", "DUPLICATE_TAG")]),
        ({"weeklyHours": None}, [("weeklyHours", "NULL_NOT_ALLOWED")]),
        (hours(dayOfWeek=0), [("weeklyHours[0].dayOfWeek", "GREATER_THAN_EQUAL")]),
        (hours(dayOfWeek=8), [("weeklyHours[0].dayOfWeek", "LESS_THAN_EQUAL")]),
        (hours(closed="no"), [("weeklyHours[0].closed", "BOOL_TYPE")]),
        ({"weeklyHours": [{"dayOfWeek": 5}]}, [("weeklyHours[0].closed", "MISSING")]),
        (hours(openTime="24:00"), [("weeklyHours[0].openTime", "INVALID_TIME")]),
        (hours(openTime="18:03"), [("weeklyHours[0].openTime", "INVALID_TIME")]),
        (hours(openTime="9:00"), [("weeklyHours[0].openTime", "INVALID_TIME")]),
        (hours(closeTime="02:00:00"), [("weeklyHours[0].closeTime", "INVALID_TIME")]),
        (hours(closeTime=200), [("weeklyHours[0].closeTime", "INVALID_TIME")]),
        (hours(closeTime=None), [("weeklyHours[0].closeTime", "MISSING")]),
        (
            {"weeklyHours": [{"dayOfWeek": 5, "closed": False}]},
            [("weeklyHours[0].openTime", "MISSING"), ("weeklyHours[0].closeTime", "MISSING")],
        ),
        (hours(closeTime="18:00"), [("weeklyHours[0].closeTime", "SAME_OPEN_CLOSE")]),
        (hours(closed=True), [("weeklyHours[0].openTime", "TIME_ON_CLOSED_DAY"), ("weeklyHours[0].closeTime", "TIME_ON_CLOSED_DAY")]),
        ({"weeklyHours": [MONDAY_OFF, FRIDAY_LATE, {**MONDAY_OFF}]}, [("weeklyHours[2].dayOfWeek", "DUPLICATE_DAY")]),
        ({"operatingException": None}, [("operatingException", "EXTRA_FORBIDDEN")]),
        ({"photos": []}, [("photos", "EXTRA_FORBIDDEN")]),
        # Rules that compare fields are reported together.
        (
            {"latitude": 37.5, "tags": ["a", "A"], "weeklyHours": [{"dayOfWeek": 5, "closed": False, "openTime": "18:00"}]},
            [
                ("longitude", "LAT_LNG_REQUIRED_TOGETHER"),
                ("tags[1]", "DUPLICATE_TAG"),
                ("weeklyHours[0].closeTime", "MISSING"),
            ],
        ),
    ],
)
def test_profile_field_rules(client, db_session, bar, owner, body, errors):
    response = patch(client, owner, bar, {"description": "새 소개", **body})

    assert response.status_code == 422, response.text
    assert [(field["path"], field["code"]) for field in response.json()["error"]["fieldErrors"]] == errors
    stored = reload(db_session, bar)
    assert (stored.description, stored.tags) == (None, [])
    assert stored_hours(db_session, bar) == []


def test_a_description_of_100_characters_with_line_breaks_fits(client, db_session, bar, owner):
    description = ("가" * 49 + "\n") * 2

    response = patch(client, owner, bar, {"description": description})

    assert response.status_code == 200, response.text
    # The last line break is trimmed, so 99 characters are stored.
    assert reload(db_session, bar).description == description.strip()


def test_hours_are_replaced_under_the_bar_lock(client, db_session, bar, owner):
    """The bar row lock orders concurrent replacements, which would otherwise insert the same weekdays twice."""
    with recorded_statements(db_session) as statements:
        assert patch(client, owner, bar, {"weeklyHours": [MONDAY_OFF]}).status_code == 200

    lock = next(i for i, sql in enumerate(statements) if "FOR UPDATE" in sql)
    assert "FROM bars" in statements[lock]
    replace = next(i for i, sql in enumerate(statements) if sql.startswith("DELETE FROM bar_weekly_hours"))
    # Stamped by the clock after the lock, not the transaction start (now()).
    stamp = next(i for i, sql in enumerate(statements) if "updated_at=clock_timestamp()" in sql.replace(" ", ""))
    assert lock < replace < stamp


def test_other_fields_take_no_lock(client, db_session, bar, owner):
    with recorded_statements(db_session) as statements:
        assert patch(client, owner, bar, {"tags": ["a"]}).status_code == 200

    assert not any("FOR UPDATE" in sql for sql in statements)
