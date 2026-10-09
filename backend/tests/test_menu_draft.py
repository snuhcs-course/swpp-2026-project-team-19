# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #12). Reviewed by Haeul Yang.
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import MenuChangeType, MenuEntryOption, MenuImport, MenuImportChange
from app.services.menu_draft import build_draft, replace_draft
from tests.factories import make_bar, make_brand, make_product, publish_menu

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    brand = make_brand(db_session, "Glenfiddich", aliases=("글렌피딕",))
    return {
        12: make_product(db_session, brand, "Glenfiddich 12", aliases=("글렌피딕 12년",), age_years=12),
        15: make_product(db_session, brand, "Glenfiddich 15", aliases=("글렌피딕 15년",), age_years=15),
    }


def stored(db_session, menu_import):
    rows = db_session.scalars(select(MenuImportChange).where(MenuImportChange.menu_import_id == menu_import.id))
    return sorted((c.change_type, c.extracted_item_id, c.bar_menu_item_id) for c in rows)


def built(db_session, menu_import):
    return sorted((c.change_type, c.extracted_item_id, c.bar_menu_item_id) for c in build_draft(db_session, menu_import))


@pytest.fixture
def imported(client, db_session, image_storage, operator, glenfiddich):
    """A sample import (exact 12, ambiguous 12, unknown) for a bar selling 12 at the menu price and 15."""
    bar = make_bar(db_session)
    board = publish_menu(
        db_session,
        bar,
        [
            (glenfiddich[12], "글렌피딕 12년", [(None, 15, 9000), (None, 30, 17000)]),
            (glenfiddich[15], "글렌피딕 15년", [(None, 30, 21000)]),
        ],
    )
    response = client.post(
        f"/api/bars/{bar.id}/menu-imports",
        headers={**operator, "Idempotency-Key": str(uuid4())},
        data={"mode": "full_replace"},
        files=[("images", ("sample.jpg", JPEG, "image/jpeg"))],
    )
    assert response.status_code == 202, response.text
    db_session.expire_all()
    return db_session.get(MenuImport, response.json()["menuImportId"]), board


def test_rebuilt_draft_matches_the_stored_one(db_session, imported):
    menu_import, _ = imported

    assert built(db_session, menu_import) == stored(db_session, menu_import)
    assert [change_type for change_type, _, _ in stored(db_session, menu_import)] == [
        MenuChangeType.ADD,
        MenuChangeType.REMOVE,
    ]


def test_board_change_shows_in_the_rebuilt_draft(db_session, imported):
    menu_import, board = imported
    twelve = board.entries[0]
    db_session.execute(
        MenuEntryOption.__table__.update()
        .where(MenuEntryOption.menu_board_entry_id == twelve.id, MenuEntryOption.pour_ml == 15)
        .values(price_krw=8000)
    )

    rebuilt = built(db_session, menu_import)

    assert rebuilt != stored(db_session, menu_import)
    assert (MenuChangeType.UPDATE, twelve.bar_menu_item_id) in {(t, item) for t, _, item in rebuilt}


def test_replace_draft_swaps_rows_and_bumps_the_version(db_session, imported):
    menu_import, board = imported
    old_ids = {c.id for c in db_session.scalars(select(MenuImportChange).where(MenuImportChange.menu_import_id == menu_import.id))}
    board.entries.pop(1)  # Glenfiddich 15 leaves the board (delete-orphan), so no remove any more
    db_session.flush()

    replace_draft(db_session, menu_import)
    db_session.flush()

    rows = list(db_session.scalars(select(MenuImportChange).where(MenuImportChange.menu_import_id == menu_import.id)))
    assert menu_import.review_version == 2
    assert [r.change_type for r in rows] == [MenuChangeType.ADD]
    assert not old_ids & {r.id for r in rows}
