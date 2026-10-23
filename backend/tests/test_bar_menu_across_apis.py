"""One bar seen through every public API that lists it.

The bar menu (API spec 3.9), customer search (3.10), nearby bars (3.12) and map bars (3.13) must
agree on the bar's name, address, coordinates (3.9.4) and menu update time (`publishedAt` =
`menuUpdatedAt`): the app shows the time on result cards and on the bar detail. Bar-name search
(3.11.11) has no time but must agree on the rest, since the map moves to its coordinates. A menu
import that is not applied yet changes none of them (3.9.2); applying one moves the time in all of
them at once.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import BarStatus, ImportStatus
from tests.factories import make_bar, make_brand, make_product, publish_menu
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
