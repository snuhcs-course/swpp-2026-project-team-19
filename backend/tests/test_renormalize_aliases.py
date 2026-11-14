from datetime import datetime, timedelta
from uuid import UUID

from app.core.normalize import normalize
from scripts.renormalize_aliases import AliasRow, plan_renormalization

PRODUCT_A = UUID(int=1)
PRODUCT_B = UUID(int=2)
T0 = datetime(2026, 10, 6)


def row(n, owner, alias_text, stored, *, searchable=True, minutes=0):
    return AliasRow(UUID(int=100 + n), owner, alias_text, stored, T0 + timedelta(minutes=minutes), searchable)


def without_hyphens(text):
    """A hypothetical rule change: hyphens are dropped like spaces."""
    return normalize(text).replace("-", "")


def test_no_changes_when_rules_are_unchanged():
    rows = [row(1, PRODUCT_A, "글렌드로낙 12Y", "글렌드로낙12"), row(2, PRODUCT_A, "GlenDronach 12", "glendronach12")]

    plan = plan_renormalization(rows)

    assert plan.updates == {} and plan.deletes == [] and plan.newly_shared == {}


def test_changed_value_is_updated():
    rows = [row(1, PRODUCT_A, "Port-Charlotte 10", "port-charlotte10")]

    plan = plan_renormalization(rows, without_hyphens)

    assert plan.updates == {rows[0].id: "portcharlotte10"}
    assert plan.deletes == []


def test_aliases_merging_within_one_product_keep_the_unchanged_row():
    hyphen = row(1, PRODUCT_A, "Port-Charlotte 10", "port-charlotte10")
    space = row(2, PRODUCT_A, "Port Charlotte 10", "portcharlotte10", minutes=5)

    plan = plan_renormalization([hyphen, space], without_hyphens)

    assert plan.updates == {}
    assert plan.deletes == [(hyphen, space)]


def test_searchable_alias_is_kept_over_unsearchable_one():
    typo = row(1, PRODUCT_A, "Port-Charlotte 10", "port-charlotte10", searchable=False)
    other = row(2, PRODUCT_A, "Port Charlotte 10", "portcharlotte10", minutes=5)
    renamed = row(3, PRODUCT_B, "Glen-Grant", "glen-grant")
    renamed_typo = row(4, PRODUCT_B, "Glen Grant", "glengrant", searchable=False)

    plan = plan_renormalization([typo, other, renamed, renamed_typo], without_hyphens)

    assert plan.updates == {renamed.id: "glengrant"}
    assert plan.deletes == [(typo, other), (renamed_typo, renamed)]


def test_oldest_row_is_kept_when_both_values_change():
    newer = row(1, PRODUCT_A, "Port-Charlotte", "x", minutes=5)
    older = row(2, PRODUCT_A, "Port Charlotte", "y")

    plan = plan_renormalization([newer, older], without_hyphens)

    assert plan.updates == {older.id: "portcharlotte"}
    assert plan.deletes == [(newer, older)]


def test_empty_value_is_deleted():
    blank = row(1, PRODUCT_A, "!!", "old")

    plan = plan_renormalization([blank])

    assert plan.deletes == [(blank, None)]


def test_values_newly_shared_across_products_are_reported():
    rows = [
        row(1, PRODUCT_A, "Port-Charlotte", "port-charlotte"),
        row(2, PRODUCT_B, "Port Charlotte", "portcharlotte"),
    ]

    plan = plan_renormalization(rows, without_hyphens)

    assert plan.newly_shared == {"portcharlotte": {PRODUCT_A, PRODUCT_B}}


def test_values_already_shared_are_not_reported_again():
    rows = [row(1, PRODUCT_A, "Glen Grant", "glengrant"), row(2, PRODUCT_B, "Glen Grant", "glengrant")]

    assert plan_renormalization(rows).newly_shared == {}


def test_swapped_values_are_both_updated():
    first = row(1, PRODUCT_A, "B", "a")
    second = row(2, PRODUCT_A, "A", "b")

    plan = plan_renormalization([first, second])

    assert plan.updates == {first.id: "b", second.id: "a"}


# ---- name keys of unlinked bar menu items (schema guide 7.1) ----

from app.models import BarMenuItem, MenuImport  # noqa: E402
from scripts.renormalize_aliases import (  # noqa: E402
    NameKeyRow,
    apply_name_keys,
    imports_in_review,
    load_name_key_rows,
    lock_menus,
    plan_name_keys,
    rebuild_drafts,
)

BAR, OTHER_BAR = UUID(int=900), UUID(int=901)


def key_row(n: int, name: str, key: str, bar: UUID = BAR) -> NameKeyRow:
    return NameKeyRow(UUID(int=n), bar, key, name)


def test_name_keys_follow_the_board_lines_name():
    rows = [key_row(1, "Glen Allachie 10", "glenallachie10"), key_row(2, "하이볼", "old-하이볼")]

    plan = plan_name_keys(rows, lambda text: text.replace(" ", "").lower())

    assert (plan.updates, plan.blocked) == ({UUID(int=2): "하이볼"}, False)


def test_lines_of_one_board_meeting_on_a_key_block_the_run():
    rows = [
        key_row(1, "글렌알라키 10 CS", "a"),
        key_row(2, "글렌알라키10CS", "b"),
        key_row(3, "글렌알라키10CS", "c", bar=OTHER_BAR),  # another bar may have the same key
        key_row(4, "!!", "d"),
    ]

    plan = plan_name_keys(rows, normalize)

    assert list(plan.collisions) == [(BAR, normalize("글렌알라키 10 CS"))]
    assert [row.item_id for row in plan.collisions[(BAR, normalize("글렌알라키 10 CS"))]] == [UUID(int=1), UUID(int=2)]
    assert [row.item_id for row in plan.empty] == [UUID(int=4)]
    assert plan.blocked


def test_the_database_parts(client, db_session, image_storage, token_for):
    """Only unlinked items on a board are read and updated; imports in review get a rebuilt draft."""
    from tests.review_support import make_glenfiddich, upload_sample_review

    operator = {"Authorization": f"Bearer {token_for('operator')}"}
    sample = upload_sample_review(client, db_session, operator, make_glenfiddich(db_session))
    board = sample.board
    on_board = BarMenuItem(bar_id=sample.bar.id, name_key="stale")
    off_board = BarMenuItem(bar_id=sample.bar.id, name_key="left")
    db_session.add_all([on_board, off_board])
    db_session.flush()
    from app.models import MenuBoardEntry

    board.entries.append(MenuBoardEntry(bar_menu_item_id=on_board.id, display_name="Mystery Cask", sort_order=9))
    db_session.flush()
    conn = db_session.connection()

    rows = load_name_key_rows(conn)
    assert [(row.item_id, row.display_name) for row in rows] == [(on_board.id, "Mystery Cask")]
    apply_name_keys(conn, plan_name_keys(rows))
    assert imports_in_review(conn) == [sample.menu_import.id]
    rebuild_drafts(conn, [sample.menu_import.id])

    db_session.expire_all()
    assert db_session.get(BarMenuItem, on_board.id).name_key == "mysterycask"
    assert db_session.get(BarMenuItem, off_board.id).name_key == "left"
    assert db_session.get(MenuImport, sample.menu_import.id).review_version == 2


def test_apply_locks_the_bars_before_the_imports(db_session):
    """The order every menu request locks in (spec 3.14.1), so the run cannot deadlock with one."""
    from tests.sql_support import recorded_statements

    conn = db_session.connection()
    with recorded_statements(db_session) as statements:
        lock_menus(conn)
        imports_in_review(conn, lock=True)

    locks = [sql for sql in statements if "FOR UPDATE" in sql]
    assert ["FROM bars" in locks[0], "FROM menu_imports" in locks[1]] == [True, True]
