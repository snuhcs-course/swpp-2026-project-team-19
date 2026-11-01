"""GET and PATCH /api/bars/{barId}: a bar with its management state, and editing it (API spec 3.6, 3.7).

Who may call them is in test_route_permissions.py; here an operator and the bar's owner use them.
"""

from datetime import timezone
from decimal import Decimal

import pytest

from app.models import Bar, BarStatus, ImportMode, ImportStatus, MenuImport, UserType
from tests.factories import make_bar, make_brand, make_owner, make_product, make_user, publish_menu

OWNER_SUBJECT = "owner-subject"
DETAIL_FIELDS = {
    "barId",
    "name",
    "address",
    "latitude",
    "longitude",
    "phone",
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
    assert body["currentMenu"] == {"menuBoardId": str(board.id), "publishedAt": rfc3339(board.published_at)}
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
