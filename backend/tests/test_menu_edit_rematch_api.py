"""Renaming a whisky in a manual edit matches it again (API spec 3.14.4, the rules of 8.11)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import BarMenuItem, CheckReason, CheckStatus, MenuItemCheck
from tests.factories import make_bar, make_product, publish_menu
from tests.review_support import make_glenfiddich

NOW = datetime.now(timezone.utc)


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


@pytest.fixture
def bar(db_session, glenfiddich):
    """A bar selling the 12 (glass and bottle) and the 15 (glass), at menu version 4."""
    bar = make_bar(db_session, "Seorosang")
    publish_menu(
        db_session,
        bar,
        [
            (glenfiddich[12], "글렌피딕 12년", [("잔", 30, 17000), ("병", None, 160000)]),
            (glenfiddich[15], "글렌피딕 15년", [("잔", 30, 21000)]),
        ],
        version=4,
    )
    db_session.commit()
    return bar


def menu(client, bar, headers) -> dict:
    return client.get(f"/api/bars/{bar.id}/menu", headers=headers).json()


def items(body) -> list[tuple]:
    return [(i["displayName"], i["productId"], [o["priceKrw"] for o in i["options"]]) for i in body["items"]]


def item_id(body, name) -> str:
    return next(i["barMenuItemId"] for i in body["items"] if i["displayName"] == name)


def rename(client, bar, headers, name, new_name, options=None):
    current = menu(client, bar, headers)
    entry = next(i for i in current["items"] if i["displayName"] == name)
    body = {
        "menuVersion": current["menuVersion"],
        "displayName": new_name,
        "options": options
        if options is not None
        else [
            {"optionLabel": o["optionLabel"], "pourMl": o["pourMl"], "priceKrw": o["priceKrw"], "discount": None}
            for o in entry["options"]
        ],
    }
    return client.put(f"/api/bars/{bar.id}/menu/items/{entry['barMenuItemId']}", json=body, headers=headers)


def open_reasons(db_session, item_id) -> list[tuple]:
    db_session.expire_all()
    check = db_session.scalar(
        select(MenuItemCheck).where(MenuItemCheck.bar_menu_item_id == item_id, MenuItemCheck.status == CheckStatus.OPEN)
    )
    return [(r.reason, r.source_extracted_item_id) for r in check.reasons] if check else []


def test_a_name_of_another_product_off_the_board_moves_the_line_to_its_item(
    client, db_session, operator, bar, glenfiddich
):
    eighteen = make_product(db_session, glenfiddich["brand"], "Glenfiddich 18", aliases=("글렌피딕 18년",), age_years=18)
    twelve = item_id(menu(client, bar, operator), "글렌피딕 12년")
    db_session.get(BarMenuItem, twelve).sold_out_at = NOW
    db_session.commit()

    response = rename(client, bar, operator, "글렌피딕 12년", "글렌피딕 18년")

    assert response.status_code == 200, response.text
    body = response.json()
    assert items(body)[0] == ("글렌피딕 18년", str(eighteen.id), [17000, 160000])
    moved = item_id(body, "글렌피딕 18년")
    assert moved != twelve
    db_session.expire_all()
    assert db_session.get(BarMenuItem, moved).sold_out_at is not None
    assert (db_session.get(BarMenuItem, twelve).product_id, db_session.get(BarMenuItem, twelve).sold_out_at) == (
        glenfiddich[12].id,
        None,
    )
    # A reason from a manual edit has no source line (spec 3.18.1).
    assert open_reasons(db_session, moved) == [(CheckReason.RELINKED_BY_NAME, None)]


def test_a_name_of_a_product_already_on_the_board_merges_the_lines(client, db_session, operator, bar, glenfiddich):
    response = rename(client, bar, operator, "글렌피딕 12년", "글렌피딕 15년")

    assert response.status_code == 200, response.text
    # The 15's line stays with its name and glass price; the 12's bottle joins it, its glass price is dropped.
    assert items(response.json()) == [("글렌피딕 15년", str(glenfiddich[15].id), [21000, 160000])]
    fifteen = item_id(response.json(), "글렌피딕 15년")
    assert open_reasons(db_session, fifteen) == [
        (CheckReason.RELINKED_BY_NAME, None),
        (CheckReason.PRICE_CONFLICT, None),
    ]
    check = db_session.scalar(select(MenuItemCheck).where(MenuItemCheck.bar_menu_item_id == fifteen))
    assert [(o["priceKrw"], o["displayName"]) for o in check.discarded_options] == [(17000, "글렌피딕 15년")]


def test_a_name_of_no_product_unlinks_the_line(client, db_session, operator, bar, glenfiddich):
    response = rename(client, bar, operator, "글렌피딕 12년", "글렌피딕 미스터리 캐스크")

    assert response.status_code == 200, response.text
    assert items(response.json())[0] == ("글렌피딕 미스터리 캐스크", None, [17000, 160000])
    unlinked = item_id(response.json(), "글렌피딕 미스터리 캐스크")
    assert db_session.get(BarMenuItem, unlinked).name_key == "글렌피딕미스터리캐스크"
    assert open_reasons(db_session, unlinked) == [(CheckReason.UNLINKED_BY_NAME, None)]
    # Not found by customers until an operator links it.
    found = client.get("/api/search/bars", params={"query": "글렌피딕 12년"}).json()
    assert found["items"] == []


def test_unlinking_to_the_name_of_another_unlinked_line_is_refused(client, db_session, operator, bar, glenfiddich):
    current = menu(client, bar, operator)
    added = client.post(
        f"/api/bars/{bar.id}/menu/items",
        json={
            "menuVersion": current["menuVersion"],
            "kind": "whisky",
            "displayName": "Mystery Cask",
            "options": [{"priceKrw": 9000}],
        },
        headers=operator,
    )
    assert added.status_code == 201, added.text

    response = rename(client, bar, operator, "글렌피딕 12년", "mystery  cask")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MENU_ITEM_EXISTS"


def test_an_unlinked_whisky_renamed_to_a_product_is_linked(client, db_session, operator, bar, glenfiddich):
    eighteen = make_product(db_session, glenfiddich["brand"], "Glenfiddich 18", aliases=("글렌피딕 18년",), age_years=18)
    db_session.commit()
    current = menu(client, bar, operator)
    added = client.post(
        f"/api/bars/{bar.id}/menu/items",
        json={"menuVersion": current["menuVersion"], "kind": "whisky", "displayName": "피딕 18", "options": [{"priceKrw": 9000}]},
        headers=operator,
    )
    unlinked = item_id(added.json(), "피딕 18")

    response = rename(client, bar, operator, "피딕 18", "글렌피딕 18년")

    assert response.status_code == 200, response.text
    assert item_id(response.json(), "글렌피딕 18년") == unlinked  # linked in place: the bar never sold the 18
    db_session.expire_all()
    assert db_session.get(BarMenuItem, unlinked).product_id == eighteen.id
    # Its unlinked reason no longer holds, so that check closed; the new link waits for an operator.
    assert open_reasons(db_session, unlinked) == [(CheckReason.RELINKED_BY_NAME, None)]


@pytest.mark.parametrize("new_name", ["글렌피딕12년", "Glenfiddich 12"])
def test_a_name_still_naming_the_same_product_keeps_the_link(client, db_session, operator, bar, glenfiddich, new_name):
    """Spacing alone is not a new name; another spelling of the same product is matched to it again."""
    response = rename(client, bar, operator, "글렌피딕 12년", new_name)

    assert response.status_code == 200, response.text
    assert items(response.json())[0][:2] == (new_name, str(glenfiddich[12].id))
    assert open_reasons(db_session, item_id(response.json(), new_name)) == []


def test_a_non_whisky_menu_is_not_matched(client, db_session, operator, bar, glenfiddich):
    current = menu(client, bar, operator)
    added = client.post(
        f"/api/bars/{bar.id}/menu/items",
        json={"menuVersion": current["menuVersion"], "kind": "other", "displayName": "하이볼", "options": [{"priceKrw": 9000}]},
        headers=operator,
    )
    assert added.status_code == 201, added.text

    response = rename(client, bar, operator, "하이볼", "글렌피딕 15년")

    assert response.status_code == 200, response.text
    assert ("글렌피딕 15년", None, [9000]) in items(response.json())
