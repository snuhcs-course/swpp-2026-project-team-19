"""Draft diff between a menu import's proposed items and the bar's current menu board.

Pure functions over plain data so the rules are easy to test. The diff is a proposal for
the reviewer; the published menu is not touched here.
"""

from dataclasses import dataclass
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
    extracted_item_id: UUID | None = None


def compute_draft_changes(
    proposed: list[ProposedEntry], current: list[CurrentEntry], mode: ImportMode
) -> list[DraftChange]:
    """Rules (API spec 5.4, matching flow 13):

    - `proposed` is in menu order. A line with a proposed product is compared with that product's
      entry; a line without one is published without a product, so it is compared with the current
      unlinked entry of the same name key. When one product or name key appears more than once, the
      first line wins and the rest produce no change.
    - A line whose proposed product is not on the board, but whose name key matches a current unlinked
      entry, is compared with that entry: it is the same menu, now matched to a product (publishing it
      with a product links the entry instead of adding a second line).
    - add: nothing on the board to compare with, or a line without a usable name key.
    - update: the compared entry's options differ, or a line takes over an unlinked entry.
    - remove: only for full_replace, a board entry no line was compared with.
    - Same entry with the same options: no change.
    """
    by_product = {entry.product_id: entry for entry in current if entry.product_id is not None}
    unlinked_by_key = {entry.name_key: entry for entry in current if entry.product_id is None}
    seen: set[tuple[str, object]] = set()
    compared: set[UUID] = set()
    changes: list[DraftChange] = []

    for entry in proposed:
        taking_over = False
        if entry.product_id is not None:
            key: tuple[str, object] = ("product", entry.product_id)
            on_board = by_product.get(entry.product_id)
            if on_board is None and entry.name_key:
                on_board = unlinked_by_key.get(entry.name_key)
                taking_over = on_board is not None
        elif entry.name_key:
            key = ("name", entry.name_key)
            on_board = unlinked_by_key.get(entry.name_key)
        else:
            changes.append(DraftChange(MenuChangeType.ADD, extracted_item_id=entry.extracted_item_id))
            continue
        if key in seen or (on_board is not None and on_board.bar_menu_item_id in compared):
            continue
        seen.add(key)
        if on_board is None:
            changes.append(DraftChange(MenuChangeType.ADD, extracted_item_id=entry.extracted_item_id))
            continue
        compared.add(on_board.bar_menu_item_id)
        # Linking the unlinked entry is a change even with the same options.
        if taking_over or on_board.options != entry.options:
            changes.append(
                DraftChange(
                    MenuChangeType.UPDATE,
                    bar_menu_item_id=on_board.bar_menu_item_id,
                    extracted_item_id=entry.extracted_item_id,
                )
            )

    if mode == ImportMode.FULL_REPLACE:
        changes.extend(
            DraftChange(MenuChangeType.REMOVE, bar_menu_item_id=entry.bar_menu_item_id)
            for entry in current
            if entry.bar_menu_item_id not in compared
        )
    return changes
