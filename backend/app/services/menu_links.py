"""Linking a board line to a product (API spec 3.14.1, "연결 바꾸기").

An item linked to a product never changes its product: (bar, product) names one item for good. So a line
is moved to the right item instead:

- An item without a product gets the product, unless the bar sold that product before: then the line
  moves to that old item.
- A line of product P linked to Q moves to Q's item (the old one, or a new one); P's item stays off the
  board for a later add.
- Unlinking a line of product P (a corrected name that names no product, spec 3.14.4) moves it to a new
  unlinked whisky item named by the line; P's item stays off the board.
- When Q is already another line on the board, the two lines merge. The line that was Q's stays, with its
  name, position and sold-out mark; the moving line's options are added after its own, and an option with
  the same label and pour size but another price keeps the staying line's price and discount. The prices
  dropped this way are returned, for the caller to raise a price_conflict check (spec 3.18.1).

A moved line keeps its name, position, options, discounts and sold-out mark. The caller holds the bar row
lock (spec 3.14.1) and handles the operator checks.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BarMenuItem, ExtractedOption, MenuBoard, MenuBoardEntry, MenuEntryOption, MenuItemKind


@dataclass
class LinkResult:
    # The board line the moving line ended up as: itself (moved or not), or the line it merged into.
    entry: MenuBoardEntry
    # The item the line was on before, when it is no longer on the board.
    left_item_id: UUID | None = None
    # Options dropped while merging, as discardedOptions entries (spec 3.18.2).
    discarded: list[dict[str, Any]] = field(default_factory=list)


def link_entry(session: Session, board: MenuBoard, entry: MenuBoardEntry, product_id: UUID) -> LinkResult:
    item = entry.bar_menu_item
    if item.product_id == product_id:
        return LinkResult(entry)
    staying = next((e for e in board.entries if e is not entry and e.bar_menu_item.product_id == product_id), None)
    if staying is not None:
        return _merge(session, board, entry, staying)

    sold_before = session.scalar(
        select(BarMenuItem).where(BarMenuItem.bar_id == board.bar_id, BarMenuItem.product_id == product_id)
    )
    if item.product_id is None and sold_before is None:
        item.product_id, item.name_key, item.kind = product_id, None, MenuItemKind.WHISKY
        session.flush()
        return LinkResult(entry)
    target = sold_before
    if target is None:
        target = BarMenuItem(bar_id=board.bar_id, product_id=product_id)
        session.add(target)
        session.flush()
    target.sold_out_at, item.sold_out_at = item.sold_out_at, None
    entry.bar_menu_item = target
    session.flush()
    return LinkResult(entry, left_item_id=item.id)


def unlink_entry(session: Session, entry: MenuBoardEntry, key: str) -> LinkResult:
    """Move a line linked to a product to a new unlinked whisky item with name key `key`. The caller has
    checked that no other unlinked line on the board has that key (spec 3.14.4)."""
    item = entry.bar_menu_item
    target = BarMenuItem(bar_id=item.bar_id, kind=MenuItemKind.WHISKY, name_key=key)
    session.add(target)
    session.flush()
    target.sold_out_at, item.sold_out_at = item.sold_out_at, None
    entry.bar_menu_item = target
    session.flush()
    return LinkResult(entry, left_item_id=item.id)


def _merge(session: Session, board: MenuBoard, moving: MenuBoardEntry, staying: MenuBoardEntry) -> LinkResult:
    prices = {(o.option_label, o.pour_ml): o.price_krw for o in staying.options}
    lines = _source_lines(session, moving.options)
    discarded: list[dict[str, Any]] = []
    next_order = max((o.sort_order for o in staying.options), default=0) + 1
    for option in moving.options:
        key = (option.option_label, option.pour_ml)
        if key in prices:
            if prices[key] != option.price_krw:
                discarded.append(
                    {
                        "optionLabel": option.option_label,
                        "pourMl": option.pour_ml,
                        "priceKrw": option.price_krw,
                        "displayName": moving.display_name,
                        "extractedItemId": lines.get(option.source_extracted_option_id),
                    }
                )
            continue
        prices[key] = option.price_krw
        staying.options.append(
            MenuEntryOption(
                option_label=option.option_label,
                pour_ml=option.pour_ml,
                price_krw=option.price_krw,
                discount_price_krw=option.discount_price_krw,
                discount_starts_at=option.discount_starts_at,
                discount_ends_at=option.discount_ends_at,
                sort_order=next_order,
                source_extracted_option_id=option.source_extracted_option_id,
            )
        )
        next_order += 1
    left = moving.bar_menu_item
    left.sold_out_at = None
    board.entries.remove(moving)
    session.flush()
    return LinkResult(staying, left_item_id=left.id, discarded=discarded)


def _source_lines(session: Session, options: list[MenuEntryOption]) -> dict[UUID, str]:
    """The extracted line (as a string id) each option came from, for discardedOptions."""
    ids = {o.source_extracted_option_id for o in options if o.source_extracted_option_id}
    if not ids:
        return {}
    rows = session.execute(
        select(ExtractedOption.id, ExtractedOption.extracted_item_id).where(ExtractedOption.id.in_(ids))
    ).all()
    return {option_id: str(item_id) for option_id, item_id in rows}
