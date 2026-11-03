"""The sold-out mark (API spec 3.14.8) and the sales info confirmation (3.14.9)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.errors import ApiError
from app.core.security import Principal
from app.models import BarMenuItem, BarStatus, ImportMode, ImportStatus, MenuBoard, MenuImport, User, UserType
from app.services.menu_status import confirm_menu, set_sold_out
from tests.factories import make_bar, make_owner, make_user, publish_menu
from tests.review_support import make_glenfiddich, upload_sample_review, valid_body
from tests.sql_support import recorded_statements

PUBLISHED = datetime.now(timezone.utc) - timedelta(days=3)
OWNER_SUBJECT = "owner-subject"


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


# A failed request rolls the session back, which in tests also drops rows that were only flushed, so
# the setup is committed first (the test's outer transaction still undoes it afterwards).


@pytest.fixture
def bar(db_session, glenfiddich):
    """A bar selling the 12 and the 15, at menu version 4."""
    bar = make_bar(db_session, "Seorosang")
    publish_menu(
        db_session,
        bar,
        [
            (glenfiddich[12], "글렌피딕 12년", [("잔", 30, 17000)]),
            (glenfiddich[15], "글렌피딕 15년", [("잔", 30, 21000)]),
        ],
        published_at=PUBLISHED,
        version=4,
    )
    db_session.commit()
    return bar


def menu_of(client, bar, headers=None) -> dict:
    response = client.get(f"/api/bars/{bar.id}/menu", headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def item_id(client, bar, product, headers) -> str:
    return next(i["barMenuItemId"] for i in menu_of(client, bar, headers)["items"] if i["productId"] == str(product.id))


def mark(client, bar_id, bar_menu_item_id, body, headers):
    return client.put(f"/api/bars/{bar_id}/menu/items/{bar_menu_item_id}/sold-out", json=body, headers=headers)


def confirm(client, bar_id, body, headers):
    return client.post(f"/api/bars/{bar_id}/menu/confirm", json=body, headers=headers)


def error(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def field_errors(response) -> list[tuple[str, str]]:
    assert error(response) == (422, "VALIDATION_FAILED"), response.text
    return [(e["path"], e["code"]) for e in response.json()["error"]["fieldErrors"]]


def stored_sold_out(db_session, bar_menu_item_id):
    db_session.expire_all()
    return db_session.get(BarMenuItem, bar_menu_item_id).sold_out_at


def owner_of(db_session, supabase, bar) -> dict:
    reviewer = make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)
    make_owner(db_session, make_user(db_session, OWNER_SUBJECT), bar, reviewer)
    db_session.commit()
    return {"Authorization": f"Bearer {supabase.token(sub=OWNER_SUBJECT)}"}


def add_import(db_session, bar, status=ImportStatus.READY_FOR_REVIEW) -> MenuImport:
    menu_import = MenuImport(
        idempotency_key=str(uuid4()),
        request_fingerprint="0" * 64,
        bar_id=bar.id,
        mode=ImportMode.PARTIAL_UPDATE,
        status=status,
    )
    db_session.add(menu_import)
    db_session.commit()
    return menu_import


def revoked_owner(db_session, bar) -> Principal:
    reviewer = make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)
    ownership = make_owner(db_session, make_user(db_session, OWNER_SUBJECT), bar, reviewer)
    ownership.revoked_at, ownership.revoked_by_user_id = datetime.now(timezone.utc), reviewer.id
    db_session.commit()
    return Principal(kind="supabase", subject=OWNER_SUBJECT, claims={})


# ---- sold-out (3.14.8) ----


def test_marking_sold_out_hides_the_item_from_customers_only(client, db_session, operator, bar, glenfiddich):
    twelve = item_id(client, bar, glenfiddich[12], operator)
    before = menu_of(client, bar, operator)

    response = mark(client, bar.id, twelve, {"soldOut": True}, operator)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == menu_of(client, bar, operator)
    assert [(i["displayName"], i["soldOut"]) for i in body["items"]] == [("글렌피딕 12년", True), ("글렌피딕 15년", False)]
    # Stock state, not menu content: neither the version nor the published time moves.
    assert (body["menuVersion"], body["publishedAt"]) == (before["menuVersion"], before["publishedAt"])
    assert [i["displayName"] for i in menu_of(client, bar)["items"]] == ["글렌피딕 15년"]
    found = client.get("/api/search/bars", params={"query": "글렌피딕 12년"}).json()["items"]
    assert found == []


def test_putting_an_item_back_on_sale_shows_it_again(client, db_session, operator, bar, glenfiddich):
    twelve = item_id(client, bar, glenfiddich[12], operator)
    mark(client, bar.id, twelve, {"soldOut": True}, operator)

    body = mark(client, bar.id, twelve, {"soldOut": False}, operator).json()

    assert [i["soldOut"] for i in body["items"]] == [False, False]
    assert stored_sold_out(db_session, twelve) is None
    assert len(menu_of(client, bar)["items"]) == 2


def test_marking_again_keeps_the_first_mark(client, db_session, operator, bar, glenfiddich):
    twelve = item_id(client, bar, glenfiddich[12], operator)
    first = mark(client, bar.id, twelve, {"soldOut": True}, operator).json()
    marked_at = stored_sold_out(db_session, twelve)

    again = mark(client, bar.id, twelve, {"soldOut": True}, operator)

    assert (again.status_code, again.json()) == (200, first)
    assert stored_sold_out(db_session, twelve) == marked_at
    # Putting an item on sale that is on sale is fine too.
    fifteen = item_id(client, bar, glenfiddich[15], operator)
    assert mark(client, bar.id, fifteen, {"soldOut": False}, operator).status_code == 200


def test_the_mark_is_taken_after_the_lock(client, db_session, operator, bar, glenfiddich):
    twelve = item_id(client, bar, glenfiddich[12], operator)

    with recorded_statements(db_session) as statements:
        assert mark(client, bar.id, twelve, {"soldOut": True}, operator).status_code == 200

    lock = next(i for i, sql in enumerate(statements) if "FOR UPDATE" in sql)
    assert "FROM bars" in statements[lock]
    board = next(i for i, sql in enumerate(statements) if "FROM menu_boards" in sql)
    stamp = next(i for i, sql in enumerate(statements) if "clock_timestamp()" in sql)
    assert lock < board < stamp


@pytest.mark.parametrize("status", [ImportStatus.UPLOADED, ImportStatus.PROCESSING, ImportStatus.READY_FOR_REVIEW])
def test_sold_out_is_accepted_during_an_unfinished_import(client, db_session, operator, bar, glenfiddich, status):
    add_import(db_session, bar, status)
    twelve = item_id(client, bar, glenfiddich[12], operator)

    assert mark(client, bar.id, twelve, {"soldOut": True}, operator).status_code == 200


def test_a_sold_out_mark_during_a_review_does_not_outdate_it(client, db_session, operator, glenfiddich, image_storage):
    sample = upload_sample_review(client, db_session, operator, glenfiddich)
    twelve = item_id(client, sample.bar, glenfiddich[12], operator)
    assert mark(client, sample.bar.id, twelve, {"soldOut": True}, operator).status_code == 200

    response = client.post(
        f"/api/menu-imports/{sample.menu_import.id}/review-and-apply",
        json=valid_body(sample, glenfiddich),
        headers=operator,
    )

    assert response.status_code == 200, response.text
    assert stored_sold_out(db_session, twelve) is not None


@pytest.mark.parametrize("target", ["deleted", "other bar", "random", "not-a-uuid"])
def test_an_item_not_on_this_menu_is_not_found(client, db_session, operator, bar, glenfiddich, target):
    if target == "deleted":
        bar_menu_item_id = item_id(client, bar, glenfiddich[15], operator)
        assert client.delete(
            f"/api/bars/{bar.id}/menu/items/{bar_menu_item_id}", params={"menuVersion": 4}, headers=operator
        ).status_code == 200
    elif target == "other bar":
        other = make_bar(db_session, "Other")
        publish_menu(db_session, other, [(glenfiddich[12], "글렌피딕 12년", [("잔", 30, 17000)])])
        db_session.commit()
        bar_menu_item_id = item_id(client, other, glenfiddich[12], operator)
    else:
        bar_menu_item_id = str(uuid4()) if target == "random" else target

    response = mark(client, bar.id, bar_menu_item_id, {"soldOut": True}, operator)

    assert error(response) == (404, "MENU_ITEM_NOT_FOUND")
    assert response.json()["error"]["details"] == {"barMenuItemId": bar_menu_item_id}
    if target == "deleted":
        # A deleted item is not left sold out.
        assert stored_sold_out(db_session, bar_menu_item_id) is None


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, [("soldOut", "MISSING")]),
        ({"soldOut": "true"}, [("soldOut", "BOOL_TYPE")]),
        ({"soldOut": 1}, [("soldOut", "BOOL_TYPE")]),
        ({"soldOut": None}, [("soldOut", "BOOL_TYPE")]),
        ({"soldOut": True, "menuVersion": 4}, [("menuVersion", "EXTRA_FORBIDDEN")]),
    ],
    ids=["missing", "string", "number", "null", "extra field"],
)
def test_sold_out_must_be_a_boolean(client, operator, bar, body, expected):
    # A missing bar too: the request is checked first.
    assert field_errors(mark(client, uuid4(), uuid4(), body, operator)) == expected


def test_sold_out_on_a_missing_or_inactive_bar(client, db_session, operator, bar, glenfiddich, token_for):
    twelve = item_id(client, bar, glenfiddich[12], operator)
    assert error(mark(client, uuid4(), twelve, {"soldOut": True}, operator)) == (404, "BAR_NOT_FOUND")
    bar.status = BarStatus.INACTIVE
    db_session.commit()

    assert error(mark(client, bar.id, twelve, {"soldOut": True}, operator)) == (404, "BAR_NOT_FOUND")
    # A temporary token takes its role from the server setting, so the customer is issued last.
    customer = {"Authorization": f"Bearer {token_for('customer')}"}
    assert error(mark(client, bar.id, twelve, {"soldOut": True}, customer)) == (403, "FORBIDDEN")


def test_the_bars_owner_may_mark_sold_out(client, db_session, supabase, bar, glenfiddich):
    owner = owner_of(db_session, supabase, bar)
    twelve = item_id(client, bar, glenfiddich[12], owner)

    assert mark(client, bar.id, twelve, {"soldOut": True}, owner).json()["items"][0]["soldOut"] is True


def test_an_owner_revoked_before_the_sold_out_lock_is_forbidden(client, db_session, operator, bar, glenfiddich):
    twelve = item_id(client, bar, glenfiddich[12], operator)
    owner = revoked_owner(db_session, bar)

    with pytest.raises(ApiError) as caught:
        set_sold_out(db_session, owner, bar.id, twelve, True, base_url="")

    assert (caught.value.status_code, caught.value.code) == (403, "FORBIDDEN")


# ---- the sales info confirmation (3.14.9) ----


def current_menu(client, bar, headers) -> dict:
    return client.get(f"/api/bars/{bar.id}", headers=headers).json()["currentMenu"]


def test_confirming_records_the_time_and_keeps_the_menu(client, db_session, operator, bar):
    before = current_menu(client, bar, operator)
    assert (before["menuVersion"], before["confirmedAt"]) == (4, None)
    customer_view = menu_of(client, bar)

    response = confirm(client, bar.id, {"menuVersion": 4}, operator)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == client.get(f"/api/bars/{bar.id}", headers=operator).json()
    menu = body["currentMenu"]
    assert (menu["menuVersion"], menu["publishedAt"]) == (4, before["publishedAt"])
    assert menu["confirmedAt"] > menu["publishedAt"]
    # Customers keep the published time as the menu date.
    assert menu_of(client, bar) == customer_view


def test_confirming_again_moves_the_time(client, db_session, operator, bar):
    first = confirm(client, bar.id, {"menuVersion": 4}, operator).json()["currentMenu"]["confirmedAt"]

    second = confirm(client, bar.id, {"menuVersion": 4}, operator).json()["currentMenu"]["confirmedAt"]

    assert second > first


def test_a_confirmation_records_who_confirmed(client, db_session, supabase, operator, bar):
    owner = owner_of(db_session, supabase, bar)
    board = db_session.scalar(select(MenuBoard).where(MenuBoard.bar_id == bar.id))

    confirm(client, bar.id, {"menuVersion": 4}, owner)
    db_session.expire_all()
    owner_id = db_session.scalar(select(User.id).where(User.auth_subject == OWNER_SUBJECT))
    assert db_session.get(MenuBoard, board.id).confirmed_by_user_id == owner_id

    # A temporary-login operator has no users row.
    confirm(client, bar.id, {"menuVersion": 4}, operator)
    db_session.expire_all()
    assert db_session.get(MenuBoard, board.id).confirmed_by_user_id is None


def test_the_confirmation_is_stamped_after_the_lock(client, db_session, operator, bar):
    with recorded_statements(db_session) as statements:
        assert confirm(client, bar.id, {"menuVersion": 4}, operator).status_code == 200

    lock = next(i for i, sql in enumerate(statements) if "FOR UPDATE" in sql)
    assert "FROM bars" in statements[lock]
    stamp = next(i for i, sql in enumerate(statements) if "clock_timestamp()" in sql)
    assert lock < stamp


def test_edits_and_publishes_keep_the_confirmation(client, db_session, operator, bar, glenfiddich):
    confirmed = confirm(client, bar.id, {"menuVersion": 4}, operator).json()["currentMenu"]["confirmedAt"]
    fifteen = item_id(client, bar, glenfiddich[15], operator)

    client.delete(f"/api/bars/{bar.id}/menu/items/{fifteen}", params={"menuVersion": 4}, headers=operator)

    menu = current_menu(client, bar, operator)
    assert (menu["menuVersion"], menu["confirmedAt"]) == (5, confirmed)
    assert menu["publishedAt"] > confirmed


@pytest.mark.parametrize("status", [ImportStatus.UPLOADED, ImportStatus.PROCESSING, ImportStatus.READY_FOR_REVIEW])
def test_confirming_is_accepted_during_an_unfinished_import(client, db_session, operator, bar, status):
    add_import(db_session, bar, status)

    assert confirm(client, bar.id, {"menuVersion": 4}, operator).status_code == 200


def test_sold_out_items_count_as_items(client, db_session, operator, bar, glenfiddich):
    for product in (glenfiddich[12], glenfiddich[15]):
        mark(client, bar.id, item_id(client, bar, product, operator), {"soldOut": True}, operator)

    assert confirm(client, bar.id, {"menuVersion": 4}, operator).status_code == 200


@pytest.mark.parametrize("menu_version", [None, 1])
def test_a_bar_without_a_menu_has_nothing_to_confirm_whatever_the_version(client, db_session, operator, menu_version):
    bar = make_bar(db_session, "Empty")
    db_session.commit()

    response = confirm(client, bar.id, {"menuVersion": menu_version}, operator)

    assert error(response) == (409, "NO_PUBLISHED_MENU")


def test_an_empty_menu_has_nothing_to_confirm_before_the_version_is_checked(client, db_session, operator, bar):
    assert client.post(f"/api/bars/{bar.id}/menu/reset", json={"menuVersion": 4}, headers=operator).status_code == 200

    # Version 5 now; an older one still gets NO_PUBLISHED_MENU.
    assert error(confirm(client, bar.id, {"menuVersion": 4}, operator)) == (409, "NO_PUBLISHED_MENU")


@pytest.mark.parametrize("submitted", [None, 3, 5], ids=["null for a menu", "older", "newer"])
def test_a_different_menu_version_is_not_confirmed(client, db_session, operator, bar, submitted):
    response = confirm(client, bar.id, {"menuVersion": submitted}, operator)

    assert error(response) == (409, "MENU_OUTDATED")
    assert response.json()["error"]["details"] == {"submittedMenuVersion": submitted, "currentMenuVersion": 4}
    assert current_menu(client, bar, operator)["confirmedAt"] is None


@pytest.mark.parametrize(
    ("body", "expected"),
    [({}, [("menuVersion", "MISSING")]), ({"menuVersion": "four"}, [("menuVersion", "INT_PARSING")])],
    ids=["missing", "not an integer"],
)
def test_the_confirmation_needs_the_version_field(client, operator, body, expected):
    # A missing bar too: the request is checked first.
    assert field_errors(confirm(client, uuid4(), body, operator)) == expected


def test_confirming_on_a_missing_or_inactive_bar(client, db_session, operator, bar, token_for):
    assert error(confirm(client, uuid4(), {"menuVersion": 4}, operator)) == (404, "BAR_NOT_FOUND")
    bar.status = BarStatus.INACTIVE
    db_session.commit()

    assert error(confirm(client, bar.id, {"menuVersion": 4}, operator)) == (404, "BAR_NOT_FOUND")
    customer = {"Authorization": f"Bearer {token_for('customer')}"}
    assert error(confirm(client, bar.id, {"menuVersion": 4}, customer)) == (403, "FORBIDDEN")


def test_an_owner_revoked_before_the_confirmation_lock_is_forbidden(db_session, bar):
    owner = revoked_owner(db_session, bar)

    with pytest.raises(ApiError) as caught:
        confirm_menu(db_session, owner, bar.id, 4, base_url="")

    assert (caught.value.status_code, caught.value.code) == (403, "FORBIDDEN")


def test_my_bars_carry_the_version_and_the_confirmation(client, db_session, supabase, bar):
    owner = owner_of(db_session, supabase, bar)
    confirmed = confirm(client, bar.id, {"menuVersion": 4}, owner).json()["currentMenu"]

    [mine] = client.get("/api/me/bars", headers=owner).json()["items"]

    assert mine["currentMenu"] == confirmed
