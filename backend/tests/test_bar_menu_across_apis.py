"""One bar seen through every public API that lists it.

The bar menu (API spec 3.9), customer search (3.10), nearby bars (3.12) and map bars (3.13) must
agree on the bar's name, address, coordinates (3.9.4) and menu update time (`publishedAt` =
`menuUpdatedAt`): the app shows the time on result cards and on the bar detail. Bar-name search
(3.11.11) has no time but must agree on the rest, since the map moves to its coordinates. A menu
import that is not applied yet changes none of them (3.9.2); applying one moves the time in all of
them at once.

The owner's own changes that are not menu content, sold-out (3.14.8) and the confirmation (3.14.9), and a
discount set by editing an item (3.14.4), must reach every view the same way: the owner's menu, the
customer's (signed out or a customer account) and search show one stored state, the same whether the
owner wrote it from the app or the owner web (both send the same requests).
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models import BarStatus, ImportStatus, UserType
from tests.factories import make_bar, make_brand, make_owner, make_product, make_user, publish_menu
from tests.review_support import make_glenfiddich, upload_sample_review, valid_body

# Not UTC and with microseconds, so the APIs must also agree on the string format.
EARLIER = datetime(2026, 10, 4, 18, 15, 30, 123456, tzinfo=timezone(timedelta(hours=9)))
EARLIER_TEXT = "2026-10-04T09:15:30.123456Z"
SAMPLE_MENU = [("글렌피딕 12년", [8000, 17000]), ("글렌피딕 15년", [21000])]


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


@pytest.fixture
def sample(client, db_session, image_storage, operator, glenfiddich):
    """A bar selling Glenfiddich 12 and 15 since EARLIER, with a menu import ready for review."""
    sample = upload_sample_review(client, db_session, operator, glenfiddich)
    sample.board.published_at = EARLIER
    db_session.flush()
    return sample


def listings(client, bar) -> dict[str, list[dict]]:
    """The rows each listing API gives for the bar's surroundings, by API."""
    location = {"lat": float(bar.latitude), "lng": float(bar.longitude)}
    area = {"south": location["lat"] - 0.01, "north": location["lat"] + 0.01}
    area |= {"west": location["lng"] - 0.01, "east": location["lng"] + 0.01}
    requests = {
        "search": ("/api/search/bars", {"query": "글렌피딕", **location}),
        "nearby": ("/api/search/nearby-bars", location),
        "map": ("/api/search/map-bars", area),
        "names": ("/api/search/bar-names", {"query": bar.name}),
    }
    found = {}
    for api, (url, params) in requests.items():
        response = client.get(url, params=params)
        assert response.status_code == 200, response.text
        found[api] = response.json()["items"]
    return found


def bar_views(client, bar) -> tuple[dict, list[dict], list[dict]]:
    """The bar menu; the bar's rows with a menu time (search, nearby, map); its bar-name rows."""
    menu = client.get(f"/api/bars/{bar.id}/menu")
    assert menu.status_code == 200, menu.text
    found = listings(client, bar)

    def shape(row, keys):
        return {key: row[key] for key in keys} | {"name": row.get("barName", row.get("name"))}

    timed = [
        shape(row, ("address", "latitude", "longitude", "menuUpdatedAt"))
        for api in ("search", "nearby", "map")
        for row in found[api]
        if row["barId"] == str(bar.id)
    ]
    named = [shape(row, ("address", "latitude", "longitude")) for row in found["names"] if row["barId"] == str(bar.id)]
    return menu.json(), timed, named


def as_menu_shape(menu: dict, *, with_time: bool = True) -> dict:
    keys = ("name", "address", "latitude", "longitude")
    shape = {key: menu[key] for key in keys}
    return shape | {"menuUpdatedAt": menu["publishedAt"]} if with_time else shape


def menu_lines(menu: dict) -> list:
    return [(item["displayName"], [option["priceKrw"] for option in item["options"]]) for item in menu["items"]]


@pytest.mark.parametrize(
    "status",
    [ImportStatus.READY_FOR_REVIEW, ImportStatus.UPLOADED, ImportStatus.PROCESSING, ImportStatus.FAILED],
)
def test_an_import_not_applied_changes_no_view(client, db_session, sample, status):
    sample.menu_import.status = status
    db_session.flush()

    menu, timed, named = bar_views(client, sample.bar)

    assert (menu["menuBoardId"], menu["publishedAt"]) == (str(sample.board.id), EARLIER_TEXT)
    assert menu_lines(menu) == SAMPLE_MENU
    # Two search rows (the 12 and the 15), the nearby item and the map item: same bar and time.
    assert timed == [as_menu_shape(menu)] * 4
    assert named == [as_menu_shape(menu, with_time=False)]


def test_applying_the_import_moves_the_time_in_every_view(client, db_session, sample, operator, glenfiddich):
    response = client.post(
        f"/api/menu-imports/{sample.menu_import.id}/review-and-apply",
        json=valid_body(sample, glenfiddich),
        headers=operator,
    )
    assert response.status_code == 200, response.text

    menu, timed, named = bar_views(client, sample.bar)

    assert menu["menuBoardId"] == str(sample.board.id)
    assert datetime.fromisoformat(menu["publishedAt"]) > EARLIER
    assert menu_lines(menu) != SAMPLE_MENU
    # The 15 was removed, so one search row (the 12), the nearby item and the map item.
    assert timed == [as_menu_shape(menu)] * 3
    assert named == [as_menu_shape(menu, with_time=False)]


def test_a_deactivated_bar_leaves_every_view(client, db_session):
    # Spec 3.9.3: the detail answers 404 and the app reloads the results, which no longer list it.
    product = make_product(db_session, make_brand(db_session, "Glenfiddich", aliases=("글렌피딕",)), "Glenfiddich 12")
    bar = make_bar(db_session, "Seorosang")
    publish_menu(db_session, bar, [(product, "글렌피딕 12년", [(None, 30, 17000)])], published_at=EARLIER)
    _, timed, named = bar_views(client, bar)
    assert (len(timed), len(named)) == (3, 1)

    bar.status = BarStatus.INACTIVE
    db_session.flush()

    menu = client.get(f"/api/bars/{bar.id}/menu")
    assert (menu.status_code, menu.json()["error"]["code"]) == (404, "BAR_NOT_FOUND")
    assert listings(client, bar) == {"search": [], "nearby": [], "map": [], "names": []}


# ---- the owner's discount, sold-out and confirmation (3.14.4, 3.14.8, 3.14.9) ----

OWNER_SUBJECT = "owner-subject"
SEOUL = ZoneInfo("Asia/Seoul")


@pytest.fixture
def owned(db_session, glenfiddich):
    """A bar selling the 12 (a glass and a bottle) and the 15 since EARLIER, at menu version 4."""
    bar = make_bar(db_session, "Seorosang")
    publish_menu(
        db_session,
        bar,
        [
            (glenfiddich[12], "글렌피딕 12년", [("잔", 30, 17000), ("병", None, 160000)]),
            (glenfiddich[15], "글렌피딕 15년", [("잔", 30, 21000)]),
        ],
        published_at=EARLIER,
        version=4,
    )
    db_session.commit()
    return bar


@pytest.fixture
def owner(db_session, supabase, owned):
    reviewer = make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)
    make_owner(db_session, make_user(db_session, OWNER_SUBJECT), owned, reviewer)
    db_session.commit()
    return {"Authorization": f"Bearer {supabase.token(sub=OWNER_SUBJECT)}"}


@pytest.fixture
def customer(supabase):
    # A Google account without a users row is a customer (AGENTS.md "API conventions").
    return {"Authorization": f"Bearer {supabase.token(sub='customer-subject')}"}


def ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()


def seoul_day_start(days_from_today: int) -> str:
    """A Seoul day's midnight as UTC, as the app and the owner web send a discount's days."""
    day = datetime.now(SEOUL).date() + timedelta(days=days_from_today)
    return datetime.combine(day, time(0), SEOUL).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def search_rows(client, bar) -> list[dict]:
    location = {"lat": float(bar.latitude), "lng": float(bar.longitude)}
    rows = ok(client.get("/api/search/bars", params={"query": "글렌피딕", **location}))["items"]
    return [row for row in rows if row["barId"] == str(bar.id)]


def customer_option(option: dict) -> dict:
    return {key: option[key] for key in ("optionLabel", "pourMl", "priceKrw", "discount", "sortOrder")}


def test_an_owners_discount_sold_out_and_confirmation_reach_every_view_alike(client, owned, owner, customer):
    items = {item["displayName"]: item for item in ok(client.get(f"/api/bars/{owned.id}/menu", headers=owner))["items"]}
    discount = {"discountedPriceKrw": 14000, "startsAt": seoul_day_start(0), "endsAt": seoul_day_start(8)}
    # The edit as the app and the owner web send it: every option, the other one's discount as it came.
    edited = ok(
        client.put(
            f"/api/bars/{owned.id}/menu/items/{items['글렌피딕 12년']['barMenuItemId']}",
            json={
                "menuVersion": 4,
                "displayName": "글렌피딕 12년",
                "options": [
                    {"optionLabel": "잔", "pourMl": 30, "priceKrw": 17000, "discount": discount},
                    {"optionLabel": "병", "pourMl": None, "priceKrw": 160000, "discount": None},
                ],
            },
            headers=owner,
        )
    )
    published = (edited["menuVersion"], edited["publishedAt"])
    assert published[0] == 5

    marked = ok(
        client.put(
            f"/api/bars/{owned.id}/menu/items/{items['글렌피딕 15년']['barMenuItemId']}/sold-out",
            json={"soldOut": True},
            headers=owner,
        )
    )
    confirmed = ok(client.post(f"/api/bars/{owned.id}/menu/confirm", json={"menuVersion": 5}, headers=owner))

    # Sold-out and the confirmation are not menu content: neither moves the version or the published time.
    assert (marked["menuVersion"], marked["publishedAt"]) == published
    current = confirmed["currentMenu"]
    assert (current["menuVersion"], current["publishedAt"]) == published
    assert current["confirmedAt"] > current["publishedAt"]

    # The owner's menu: the sold-out 15 in its place, the discount as sent.
    owners = ok(client.get(f"/api/bars/{owned.id}/menu", headers=owner))
    assert owners == marked
    assert [(i["displayName"], i["soldOut"]) for i in owners["items"]] == [("글렌피딕 12년", False), ("글렌피딕 15년", True)]
    twelve = owners["items"][0]
    assert [o["discount"] for o in twelve["options"]] == [discount, None]

    # Customers, signed out or signed in: the same menu without the sold-out item.
    signed_out = ok(client.get(f"/api/bars/{owned.id}/menu"))
    signed_in = ok(client.get(f"/api/bars/{owned.id}/menu", headers=customer))
    assert signed_out == signed_in
    assert signed_out == owners | {"items": [twelve]}

    # Search: the same options and discount, the published time, and no sold-out item.
    rows = search_rows(client, owned)
    assert [row["menuDisplayName"] for row in rows] == ["글렌피딕 12년"]
    assert rows[0]["options"] == [customer_option(option) for option in twelve["options"]]
    assert rows[0]["menuUpdatedAt"] == published[1]

    # The owner's bar and bar list carry the same summary, with the confirmation.
    assert ok(client.get(f"/api/bars/{owned.id}", headers=owner))["currentMenu"] == current
    [mine] = ok(client.get("/api/me/bars", headers=owner))["items"]
    assert mine["currentMenu"] == current


def test_an_item_back_on_sale_returns_to_every_view(client, owned, owner, customer):
    items = {item["displayName"]: item for item in ok(client.get(f"/api/bars/{owned.id}/menu", headers=owner))["items"]}
    fifteen = f"/api/bars/{owned.id}/menu/items/{items['글렌피딕 15년']['barMenuItemId']}/sold-out"
    ok(client.put(fifteen, json={"soldOut": True}, headers=owner))
    assert [row["menuDisplayName"] for row in search_rows(client, owned)] == ["글렌피딕 12년"]

    back = ok(client.put(fifteen, json={"soldOut": False}, headers=owner))

    assert (back["menuVersion"], back["publishedAt"]) == (4, EARLIER_TEXT)
    owners = ok(client.get(f"/api/bars/{owned.id}/menu", headers=owner))
    for view in (ok(client.get(f"/api/bars/{owned.id}/menu")), ok(client.get(f"/api/bars/{owned.id}/menu", headers=customer))):
        assert view == owners
    assert sorted(row["menuDisplayName"] for row in search_rows(client, owned)) == ["글렌피딕 12년", "글렌피딕 15년"]
