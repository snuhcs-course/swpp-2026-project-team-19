"""GET /api/me/bars: the bars the caller currently owns (API spec, section 3.11.9)."""

from datetime import datetime, timezone

from app.models import BarStatus, ImportMode, ImportStatus, MenuImport, UserType
from tests.factories import make_bar, make_owner, make_user, publish_menu

SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"
PUBLISHED = datetime(2026, 10, 4, 9, 15, tzinfo=timezone.utc)


def my_bars(client, supabase):
    response = client.get("/api/me/bars", headers={"Authorization": f"Bearer {supabase.token(sub=SUBJECT)}"})
    assert response.status_code == 200
    return response.json()["items"]


def rfc3339(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def add_import(db_session, bar, status: ImportStatus) -> MenuImport:
    menu_import = MenuImport(
        idempotency_key=f"{bar.id}-{status.value}",
        request_fingerprint="0" * 64,
        bar_id=bar.id,
        mode=ImportMode.FULL_REPLACE,
        status=status,
    )
    db_session.add(menu_import)
    db_session.flush()
    return menu_import


def test_lists_my_bars_with_their_management_state(client, db_session, supabase):
    me = make_user(db_session, SUBJECT, email="owner@example.com", display_name="김사장")
    operator = make_user(db_session, "operator-subject", user_type=UserType.OPERATOR)
    busy, quiet = make_bar(db_session, "B 바"), make_bar(db_session, "A 바")
    owner = make_owner(db_session, me, busy, operator)
    make_owner(db_session, me, quiet, operator)
    unfinished = add_import(db_session, busy, ImportStatus.READY_FOR_REVIEW)
    add_import(db_session, quiet, ImportStatus.APPLIED)
    board = publish_menu(db_session, busy, [], published_at=PUBLISHED)
    db_session.refresh(busy)
    db_session.refresh(owner)

    items = my_bars(client, supabase)

    assert [item["name"] for item in items] == ["A 바", "B 바"]
    assert items[0]["activeMenuImport"] is None
    assert items[0]["currentMenu"] is None
    assert items[1] == {
        "barId": str(busy.id),
        "name": "B 바",
        "address": "B 바 address",
        "latitude": 37.478,
        "longitude": 126.951,
        "phone": "02-000-0000",
        "status": "active",
        "activeMenuImport": {"menuImportId": str(unfinished.id), "status": "ready_for_review"},
        "currentMenu": {"menuBoardId": str(board.id), "publishedAt": "2026-10-04T09:15:00Z"},
        "owner": {
            "userId": str(me.id),
            "email": "owner@example.com",
            "displayName": "김사장",
            "ownerSince": rfc3339(owner.created_at),
        },
        "createdAt": rfc3339(busy.created_at),
        "updatedAt": rfc3339(busy.updated_at),
    }


def test_an_inactive_bar_i_own_is_listed(client, db_session, supabase):
    me, operator = make_user(db_session, SUBJECT), make_user(db_session, "operator-subject")
    make_owner(db_session, me, make_bar(db_session, status=BarStatus.INACTIVE), operator)

    assert [item["status"] for item in my_bars(client, supabase)] == ["inactive"]


def test_revoked_and_other_owners_bars_are_not_listed(client, db_session, supabase):
    me, operator = make_user(db_session, SUBJECT), make_user(db_session, "operator-subject")
    revoked = make_owner(db_session, me, make_bar(db_session, "Revoked"), operator)
    revoked.revoked_at, revoked.revoked_by_user_id = PUBLISHED, operator.id
    make_owner(db_session, make_user(db_session, "other-subject"), make_bar(db_session, "Other"), operator)
    db_session.flush()

    assert my_bars(client, supabase) == []


def test_an_operator_gets_only_bars_they_own(client, db_session, supabase):
    me = make_user(db_session, SUBJECT, user_type=UserType.OPERATOR)
    make_bar(db_session, "Not mine")
    make_owner(db_session, me, make_bar(db_session, "Mine"), me)

    assert [item["name"] for item in my_bars(client, supabase)] == ["Mine"]


def test_empty_without_a_users_row(client, supabase):
    assert my_bars(client, supabase) == []


def test_needs_a_token(client):
    response = client.get("/api/me/bars")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
