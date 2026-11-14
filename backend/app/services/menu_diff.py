"""Draft diff between a menu import's proposed items and the bar's current menu board.

Pure functions over plain data so the rules are easy to test. The diff is a proposal for
the reviewer; the published menu is not touched here.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID

from app.models import ImportMode, MenuChangeType

# (option label, pour ml, price krw), compared in display order.
OptionKey = tuple[str | None, int | None, int | None]


@dataclass(frozen=True)
class ProposedEntry:
    """A product item from the import with its rank-1 candidate (None when unmatched) and the name key
    of its extracted name ("" when it has none)."""

    extracted_item_id: UUID
    product_id: UUID | None
    options: tuple[OptionKey, ...]
    name_key: str = ""


@dataclass(frozen=True)
class CurrentEntry:
    """An entry on the bar's current menu board. An unlinked item has no product and a name key."""

    bar_menu_item_id: UUID
    product_id: UUID | None
    options: tuple[OptionKey, ...]
    name_key: str | None = None


@dataclass(frozen=True)
class DraftChange:
    change_type: MenuChangeType
    bar_menu_item_id: UUID | None = None
    # The first line of the change; `extracted_item_ids` are all its lines in menu order (spec 5.4).
    extracted_item_id: UUID | None = None
    extracted_item_ids: tuple[UUID, ...] = field(default=(), compare=False)


def group_lines(keys: Iterable[tuple[UUID, tuple[str, object] | None]]) -> dict[UUID, tuple[UUID, ...]]:
    """Lines in menu order grouped by what they were proposed as (spec 8.12): the same product, or for
    a line without one the same name key. Maps each group's first line to all its lines. A line with no
    product and no usable name key is a group of its own (key None, or a name key that is empty).

    The groups are not stored: the draft, the review data and the submission each call this on the
    same stored proposals, so they agree."""
    groups: dict[object, list[UUID]] = {}
    for line, key in keys:
        if key is None or (key[0] == "name" and not key[1]):
            key = ("line", line)
        groups.setdefault(key, []).append(line)
    return {lines[0]: tuple(lines) for lines in groups.values()}


def merge_options(option_lists: Iterable[Iterable[OptionKey]]) -> tuple[OptionKey, ...]:
    """The options of several lines one after another, an option equal to an earlier one kept once
    (the same board photographed twice, spec 8.12)."""
    merged: dict[OptionKey, None] = {}
    for options in option_lists:
        for option in options:
            merged.setdefault(option, None)
    return tuple(merged)


def _key(entry: ProposedEntry) -> tuple[str, object] | None:
    if entry.product_id is not None:
        return ("product", entry.product_id)
    return ("name", entry.name_key) if entry.name_key else None


def compute_draft_changes(
    proposed: list[ProposedEntry], current: list[CurrentEntry], mode: ImportMode
) -> list[DraftChange]:
    """Rules (API spec 5.4 and 8.12, matching flow 13):

    - `proposed` is in menu order. Lines proposed as the same product, or without a product under the
      same name key, make one change with their options merged (`group_lines`, `merge_options`). A
      group with a product is compared with that product's entry; one without is published without a
      product, so it is compared with the current unlinked entry of the same name key.
    - A group whose product is not on the board, but one of whose lines has the name key of a current
      unlinked entry, is compared with that entry: it is the same menu, now matched to a product
      (publishing it with a product links the entry instead of adding a second line).
    - add: nothing on the board to compare with, a line without a usable name key, or an entry another
      group was already compared with.
    - update: the compared entry's options differ from the merged ones, or a group takes over an
      unlinked entry.
    - remove: only for full_replace, a board entry no group was compared with.
    - Same entry with the same options: no change.
    """
    by_product = {entry.product_id: entry for entry in current if entry.product_id is not None}
    unlinked_by_key = {entry.name_key: entry for entry in current if entry.product_id is None}
    by_line = {entry.extracted_item_id: entry for entry in proposed}
    compared: set[UUID] = set()
    changes: list[DraftChange] = []

    for first, lines in group_lines((entry.extracted_item_id, _key(entry)) for entry in proposed).items():
        entries = [by_line[line] for line in lines]
        head = entries[0]
        taking_over = False
        if head.product_id is not None:
            on_board = by_product.get(head.product_id)
            if on_board is None:
                on_board = next(
                    (
                        unlinked_by_key[e.name_key]
                        for e in entries
                        if e.name_key in unlinked_by_key
                        and unlinked_by_key[e.name_key].bar_menu_item_id not in compared
                    ),
                    None,
                )
                taking_over = on_board is not None
        elif head.name_key:
            on_board = unlinked_by_key.get(head.name_key)
        else:
            on_board = None
        if on_board is not None and on_board.bar_menu_item_id in compared:
            on_board = None
        if on_board is None:
            changes.append(DraftChange(MenuChangeType.ADD, extracted_item_id=first, extracted_item_ids=lines))
            continue
        compared.add(on_board.bar_menu_item_id)
        # Linking the unlinked entry is a change even with the same options.
        if taking_over or on_board.options != merge_options(e.options for e in entries):
            changes.append(
                DraftChange(
                    MenuChangeType.UPDATE,
                    bar_menu_item_id=on_board.bar_menu_item_id,
                    extracted_item_id=first,
                    extracted_item_ids=lines,
                )
            )

    if mode == ImportMode.FULL_REPLACE:
        changes.extend(
            DraftChange(MenuChangeType.REMOVE, bar_menu_item_id=entry.bar_menu_item_id)
            for entry in current
            if entry.bar_menu_item_id not in compared
        )
    return changes
