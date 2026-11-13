"""Identity of bar menu items without a product (API spec 3.14.1, schema guide 7.1).

An item linked to a product is identified by (bar, product). An unlinked item has no product, so it is
identified within the bar by its name key: the menu name normalized with the alias function. Only the
current board's unlinked items must have different keys, which the caller checks while holding the bar
row lock; an unlinked item that left the board is never reused.
"""

from collections.abc import Iterable
from uuid import UUID

from app.core.normalize import normalize
from app.models import MenuBoardEntry


# ("product", product id) for an item linked to a product, ("name", name key) for one without.
ItemKey = tuple[str, object]


def item_key(product_id: UUID | None, key: str | None) -> ItemKey:
    return ("product", product_id) if product_id is not None else ("name", key)


def name_key(display_name: str) -> str:
    """The name key of a menu name; empty when nothing in it normalizes (the caller answers NOT_NORMALIZABLE)."""
    return normalize(display_name)


def unlinked_entry_with_key(
    entries: Iterable[MenuBoardEntry], key: str, *, except_item_id: UUID | None = None
) -> MenuBoardEntry | None:
    """The current board's entry of an unlinked item with this name key, other than `except_item_id`."""
    return next(
        (
            entry
            for entry in entries
            if entry.bar_menu_item.product_id is None
            and entry.bar_menu_item.name_key == key
            and entry.bar_menu_item_id != except_item_id
        ),
        None,
    )
