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
    """A product item from the import with its rank-1 candidate (None when unmatched)."""

    extracted_item_id: UUID
    product_id: UUID | None
    options: tuple[OptionKey, ...]


@dataclass(frozen=True)
class CurrentEntry:
    """An entry on the bar's current menu board."""

    bar_menu_item_id: UUID
    product_id: UUID
    options: tuple[OptionKey, ...]


@dataclass(frozen=True)
class DraftChange:
    change_type: MenuChangeType
    bar_menu_item_id: UUID | None = None
    extracted_item_id: UUID | None = None


def compute_draft_changes(
    proposed: list[ProposedEntry], current: list[CurrentEntry], mode: ImportMode
) -> list[DraftChange]:
    """Rules:

    - `proposed` is in menu order; when one product appears more than once, the first wins
      and the rest produce no change.
    - add: the product is not on the current board, or the item is unmatched (the reviewer
      picks or creates the product).
    - update: the product is on the board but its options differ.
    - remove: only for full_replace, a board product that the import does not contain.
    - Same product with the same options: no change.
    """
    current_by_product = {entry.product_id: entry for entry in current}
    seen_products: set[UUID] = set()
    changes: list[DraftChange] = []

    for entry in proposed:
        if entry.product_id is None:
            changes.append(DraftChange(MenuChangeType.ADD, extracted_item_id=entry.extracted_item_id))
            continue
        if entry.product_id in seen_products:
            continue
        seen_products.add(entry.product_id)
        on_board = current_by_product.get(entry.product_id)
        if on_board is None:
            changes.append(DraftChange(MenuChangeType.ADD, extracted_item_id=entry.extracted_item_id))
        elif on_board.options != entry.options:
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
            if entry.product_id not in seen_products
        )
    return changes
