from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.pagination import encode_cursor
from app.models import BarStatus, ImportMode, ImportStatus, MenuImage, MenuImport
from tests.factories import make_bar

T0 = datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


def get(client, path, headers, **params):
    response = client.get(path, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def make_import(session, bar, status, *, minutes=0, images=1, note=None):
    menu_import = MenuImport(
        idempotency_key=str(uuid4()),
        request_fingerprint="f",
        bar_id=bar.id,
        mode=ImportMode.FULL_REPLACE,
        status=status,
        owner_note=note,
        created_at=T0 + timedelta(minutes=minutes),
    )
    session.add(menu_import)
    session.flush()
    for order in range(1, images + 1):
        session.add(MenuImage(menu_import_id=menu_import.id, storage_key=f"menus/x/{uuid4()}.jpg", image_order=order))
    session.flush()
    return menu_import


# ---- GET /api/bars ----


def test_bar_list(client, db_session, operator):
    bokchun = make_bar(db_session, "Whisky Bokchun")
    seorosang = make_bar(db_session, "Seorosang")
    make_bar(db_session, "Closed Bar", status=BarStatus.INACTIVE)
    pending = make_import(db_session, seorosang, ImportStatus.READY_FOR_REVIEW)
    make_import(db_session, bokchun, ImportStatus.APPLIED)

    body = get(client, "/api/bars", operator)

    assert body["nextCursor"] is None
    assert [b["name"] for b in body["items"]] == ["Seorosang", "Whisky Bokchun"]
    assert body["items"][0] == {
        "barId": str(seorosang.id),
        "name": "Seorosang",
        "address": "Seorosang address",
        "latitude": 37.478,
        "longitude": 126.951,
        "phone": "02-000-0000",
        "status": "active",
        "activeMenuImport": {"menuImportId": str(pending.id), "status": "ready_for_review"},
    }
    # An applied import is not an active one.
    assert body["items"][1]["activeMenuImport"] is None


def test_bar_status_filter(client, db_session, operator):
    make_bar(db_session, "Open")
    make_bar(db_session, "Closed", status=BarStatus.INACTIVE)

    assert [b["name"] for b in get(client, "/api/bars", operator, status="inactive")["items"]] == ["Closed"]
    assert [b["name"] for b in get(client, "/api/bars", operator, status="all")["items"]] == ["Closed", "Open"]


def test_bar_query_matches_name_or_address(client, db_session, operator):
    make_bar(db_session, "Whisky Bokchun")
    make_bar(db_session, "Seorosang")
    make_bar(db_session, "100% Bar")

    assert [b["name"] for b in get(client, "/api/bars", operator, query="whisky")["items"]] == ["Whisky Bokchun"]
    assert [b["name"] for b in get(client, "/api/bars", operator, query="SEOROSANG ADD")["items"]] == ["Seorosang"]
    # % is matched literally, not as a wildcard.
    assert [b["name"] for b in get(client, "/api/bars", operator, query="0%")["items"]] == ["100% Bar"]


def test_bar_pages(client, db_session, operator):
    for name in ("A", "B", "C"):
        make_bar(db_session, name)

    first = get(client, "/api/bars", operator, limit=2)
    second = get(client, "/api/bars", operator, limit=2, cursor=first["nextCursor"])

    assert [b["name"] for b in first["items"]] == ["A", "B"]
    assert [b["name"] for b in second["items"]] == ["C"]
    assert second["nextCursor"] is None


@pytest.mark.parametrize(
    ("params", "path", "code"),
    [
        ({"query": "  "}, "query", "BLANK"),
        ({"status": "closed"}, "status", "LITERAL_ERROR"),
        ({"limit": 101}, "limit", "LESS_THAN_EQUAL"),
        ({"cursor": "not-a-cursor"}, "cursor", "INVALID_CURSOR"),
        ({"cursor": encode_cursor(["A"])}, "cursor", "INVALID_CURSOR"),
        ({"cursor": encode_cursor(["A", "not-a-uuid"])}, "cursor", "INVALID_CURSOR"),
        ({"cursor": encode_cursor([1, str(uuid4())])}, "cursor", "INVALID_CURSOR"),
        ({"cursor": encode_cursor({"name": "A"})}, "cursor", "INVALID_CURSOR"),
    ],
)
def test_bar_list_validation(client, operator, params, path, code):
    response = client.get("/api/bars", params=params, headers=operator)

    assert response.status_code == 422
    [error] = response.json()["error"]["fieldErrors"]
    assert (error["path"], error["code"]) == (path, code)


# ---- GET /api/bars/{barId}/menu-imports ----


def test_menu_import_history(client, db_session, operator):
    bar = make_bar(db_session)
    other = make_bar(db_session, "Other")
    old = make_import(db_session, bar, ImportStatus.APPLIED, minutes=0, images=2, note="10월 메뉴")
    old.completed_at = T0 + timedelta(minutes=5)
    failed = make_import(db_session, bar, ImportStatus.FAILED, minutes=10)
    pending = make_import(db_session, bar, ImportStatus.PROCESSING, minutes=20)
    make_import(db_session, other, ImportStatus.UPLOADED, minutes=30)
    db_session.flush()

    body = get(client, f"/api/bars/{bar.id}/menu-imports", operator)

    assert [i["menuImportId"] for i in body["items"]] == [str(pending.id), str(failed.id), str(old.id)]
    assert body["items"][2] == {
        "menuImportId": str(old.id),
        "mode": "full_replace",
        "status": "applied",
        "imageCount": 2,
        "reviewVersion": 0,
        "ownerNote": "10월 메뉴",
        "createdAt": "2026-10-04T09:00:00Z",
        "completedAt": "2026-10-04T09:05:00Z",
    }
    assert body["nextCursor"] is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [("active", ["processing", "uploaded"]), ("failed", ["failed"]), ("all", ["processing", "failed", "uploaded"])],
)
def test_menu_import_status_filter(client, db_session, operator, status, expected):
    bar = make_bar(db_session)
    make_import(db_session, bar, ImportStatus.UPLOADED, minutes=0)
    make_import(db_session, bar, ImportStatus.FAILED, minutes=1)
    make_import(db_session, bar, ImportStatus.PROCESSING, minutes=2)

    body = get(client, f"/api/bars/{bar.id}/menu-imports", operator, status=status)

    assert [i["status"] for i in body["items"]] == expected


def test_menu_import_pages_with_the_same_creation_time(client, db_session, operator):
    bar = make_bar(db_session)
    imports = [make_import(db_session, bar, ImportStatus.FAILED) for _ in range(3)]

    first = get(client, f"/api/bars/{bar.id}/menu-imports", operator, limit=2)
    second = get(client, f"/api/bars/{bar.id}/menu-imports", operator, limit=2, cursor=first["nextCursor"])

    seen = [i["menuImportId"] for i in first["items"] + second["items"]]
    assert sorted(seen) == sorted(str(i.id) for i in imports)
    assert second["nextCursor"] is None


def test_menu_imports_of_inactive_bars_are_listed(client, db_session, operator):
    bar = make_bar(db_session, status=BarStatus.INACTIVE)
    make_import(db_session, bar, ImportStatus.APPLIED)

    assert len(get(client, f"/api/bars/{bar.id}/menu-imports", operator)["items"]) == 1


@pytest.mark.parametrize("bar_id", [str(uuid4()), "not-a-uuid"])
def test_menu_imports_of_an_unknown_bar(client, operator, bar_id):
    response = client.get(f"/api/bars/{bar_id}/menu-imports", headers=operator)

    assert (response.status_code, response.json()["error"]["code"]) == (404, "BAR_NOT_FOUND")


@pytest.mark.parametrize("path", ["/api/bars", "/api/bars/{bar_id}/menu-imports"])
def test_operators_only(client, db_session, token_for, path):
    bar = make_bar(db_session)
    url = path.format(bar_id=bar.id)
    customer = {"Authorization": f"Bearer {token_for('customer')}"}

    assert client.get(url, headers=customer).status_code == 403
    assert client.get(url).status_code == 401
