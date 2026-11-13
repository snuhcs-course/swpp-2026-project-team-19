"""Unlinked menu items, menu item kinds and operator menu item checks in the database
(docs/schema_guide.md 7.1, 7.7, 7.8 and 8.4; migration 5c3e9a1f7d24)."""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    BarMenuItem,
    CheckReason,
    CheckResolution,
    CheckStatus,
    MenuItemCheck,
    MenuItemCheckReason,
    MenuItemKind,
)
from tests.conftest import BACKEND_DIR
from tests.factories import make_bar, make_brand, make_product

NOW = datetime(2026, 11, 13, 9, tzinfo=timezone.utc)
BEFORE = "bec46a7503af"


def _flush_fails(session: Session) -> None:
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# ---- bar_menu_items ----


def test_existing_items_are_linked_whiskies(db_session):
    """Insert with plain SQL so the columns get the database defaults, as rows from before the migration did."""
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    item_id = uuid4()
    db_session.execute(
        text("INSERT INTO bar_menu_items (id, bar_id, product_id) VALUES (:id, :bar, :product)"),
        {"id": item_id, "bar": make_bar(db_session).id, "product": product.id},
    )

    row = db_session.execute(text("SELECT kind, name_key FROM bar_menu_items WHERE id = :id"), {"id": item_id}).one()
    assert tuple(row) == ("whisky", None)


@pytest.mark.parametrize("kind", [MenuItemKind.WHISKY, MenuItemKind.OTHER])
def test_an_unlinked_item_of_either_kind_has_a_name_key(db_session, kind):
    item = BarMenuItem(bar_id=make_bar(db_session).id, kind=kind, name_key="하이볼")
    db_session.add(item)
    db_session.flush()

    assert (item.product_id, item.kind) == (None, kind)


def test_an_unlinked_item_needs_a_name_key(db_session):
    db_session.add(BarMenuItem(bar_id=make_bar(db_session).id, kind=MenuItemKind.WHISKY))
    _flush_fails(db_session)


def test_a_linked_item_has_no_name_key(db_session):
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    db_session.add(BarMenuItem(bar_id=make_bar(db_session).id, product_id=product.id, name_key="glenfiddich12"))
    _flush_fails(db_session)


def test_an_other_item_is_never_linked(db_session):
    product = make_product(db_session, make_brand(db_session, "Glenfiddich"), "Glenfiddich 12")
    db_session.add(BarMenuItem(bar_id=make_bar(db_session).id, product_id=product.id, kind=MenuItemKind.OTHER))
    _flush_fails(db_session)


def test_unlinked_items_may_share_a_name_key(db_session):
    """Only the current board's unlinked items must differ, which the service checks under the bar lock;
    an item that left the board keeps its key and is not reused."""
    bar = make_bar(db_session)
    db_session.add_all([BarMenuItem(bar_id=bar.id, name_key="하이볼"), BarMenuItem(bar_id=bar.id, name_key="하이볼")])
    db_session.flush()


# ---- menu_item_checks and menu_item_check_reasons ----


def _unlinked_item(session: Session) -> BarMenuItem:
    item = BarMenuItem(bar_id=make_bar(session).id, name_key="글렌알라키10cs")
    session.add(item)
    session.flush()
    return item


def _check(item: BarMenuItem, **values) -> MenuItemCheck:
    return MenuItemCheck(bar_id=item.bar_id, bar_menu_item_id=item.id, display_name="글렌알라키 10 CS", **values)


def test_a_new_check_is_open_with_no_discarded_options(db_session):
    item = _unlinked_item(db_session)
    check = _check(item, reasons=[MenuItemCheckReason(reason=CheckReason.UNLINKED)])
    db_session.add(check)
    db_session.flush()
    db_session.refresh(check)

    assert (check.status, check.discarded_options, check.resolution, check.resolved_at) == (
        CheckStatus.OPEN,
        [],
        None,
        None,
    )
    assert [r.reason for r in check.reasons] == [CheckReason.UNLINKED]
    assert check.reasons[0].source_menu_import_id is None


def test_an_item_has_at_most_one_open_check(db_session):
    item = _unlinked_item(db_session)
    db_session.add_all([_check(item), _check(item)])
    _flush_fails(db_session)


def test_an_item_can_have_many_closed_checks(db_session):
    item = _unlinked_item(db_session)
    db_session.add_all(
        [
            _check(item, status=CheckStatus.DISMISSED, resolved_at=NOW),
            _check(item, status=CheckStatus.RESOLVED, resolution=CheckResolution.MARK_AS_OTHER, resolved_at=NOW),
            _check(item),
        ]
    )
    db_session.flush()


@pytest.mark.parametrize(
    "values",
    [
        {"status": CheckStatus.RESOLVED, "resolved_at": NOW},
        {"status": CheckStatus.DISMISSED, "resolution": CheckResolution.KEEP, "resolved_at": NOW},
        {"status": CheckStatus.DISMISSED},
        {"resolved_at": NOW},
    ],
    ids=["resolved-without-resolution", "dismissed-with-resolution", "closed-without-time", "open-with-time"],
)
def test_a_check_state_must_be_consistent(db_session, values):
    db_session.add(_check(_unlinked_item(db_session), **values))
    _flush_fails(db_session)


def test_a_reason_source_names_both_the_import_and_the_line(db_session):
    item = _unlinked_item(db_session)
    db_session.add(_check(item, reasons=[MenuItemCheckReason(reason=CheckReason.UNLINKED, source_menu_import_id=uuid4())]))
    _flush_fails(db_session)


# ---- the migration ----


@pytest.fixture
def migrations(db_engine, monkeypatch):
    """Move the test database between revisions; the schema is back at head and the rows gone afterwards."""
    monkeypatch.setenv("POSTGRES_DATABASE", os.environ["POSTGRES_TEST_DATABASE"])
    config = Config(str(BACKEND_DIR / "alembic.ini"))

    class Migrations:
        def down(self) -> None:
            command.downgrade(config, BEFORE)

        def up(self) -> None:
            command.upgrade(config, "head")

    try:
        yield Migrations()
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM bar_menu_items WHERE product_id IS NULL"))
            conn.execute(text("DELETE FROM bars WHERE name = 'Migration Bar'"))
        command.upgrade(config, "head")


def test_the_downgrade_refuses_while_items_are_unlinked(db_engine, migrations):
    with Session(db_engine) as session:
        session.add(BarMenuItem(bar_id=make_bar(session, name="Migration Bar").id, name_key="하이볼"))
        session.commit()

    with pytest.raises(RuntimeError, match="1 bar menu items have no product"):
        migrations.down()

    with db_engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) != BEFORE


def test_the_migration_round_trips_without_unlinked_items(db_engine, migrations):
    migrations.down()
    with db_engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == BEFORE
        assert conn.scalar(text("SELECT to_regclass('menu_item_checks')")) is None
    migrations.up()
    with db_engine.connect() as conn:
        assert conn.scalar(text("SELECT to_regclass('menu_item_checks')")) == "menu_item_checks"
