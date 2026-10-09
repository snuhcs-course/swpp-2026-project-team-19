# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #8). Reviewed by Haeul Yang.
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
