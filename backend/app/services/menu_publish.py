"""Publishing a reviewed import to the bar's menu board (flow doc, chapter 17).

The reviewer's decisions are final, with one safeguard: nothing leaves the board unless the
reviewer approved its removal.

- Every product decision is published with its product and final priced options, unless the
  reviewer ignored the item's proposed change. When a product appears more than once, the
  first line wins.
- Compared with the current board that is an add (not on the board), an update (options
  differ) or no change. Changes the draft did not show, such as an update caused only by a
  price correction or an add after picking another product, are still the reviewer's own
  decisions and are applied.
- A board entry is removed only by an applied `remove` change, and kept anyway if a decision
  publishes its product again. The one exception is an unlinked entry a line takes over: a line the
  draft compared with a current unlinked entry (an applied update) and that is now published with a
  product links that entry instead of adding a second line (spec 5.4, 3.14.1).
- Entries are matched by their key: the product, or for an item without one its name key (spec
  3.14.1). A line published without a product (spec 8.10) is the board's unlinked entry of the same
  name key, or a new unlinked item; an unlinked item that left the board is never reused.
- Order: full_replace follows the photos, then the entries kept from the old board in their
  old order. partial_update keeps the old order with updates in place and appends adds.
- Every option row is rewritten, so a discount moves to the new option of the same product
  with the same label, pour size and list price. A changed price or a dropped option drops it,
  since the old discounted price may no longer fit (spec 8.7).
- Sold-out lives on the bar menu item, so it stays on entries that remain and is cleared on
  entries that leave the board (spec 3.14.8).

`plan_publish` decides all of this from plain data; `write_board` stores the result.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.models import (
    BarMenuItem,
    ImportMode,
    MenuBoard,
    MenuBoardEntry,
    MenuChangeDecision,
    MenuChangeType,
    MenuEntryOption,
    MenuItemKind,
    Product,
)
from app.services.menu_items import ItemKey, item_key, name_key
from app.services.menu_review_catalog import CatalogResult
from app.services.menu_review_validation import ValidatedReview

@dataclass(frozen=True)
class PublishedOption:
    label: str | None
    pour_ml: int | None
    price_krw: int
    source_extracted_option_id: UUID | None = None

    @property
    def key(self) -> tuple[str | None, int | None, int]:
        return (self.label, self.pour_ml, self.price_krw)


@dataclass(frozen=True)
class BoardEntry:
    """An entry on the current board, or one to be written. `bar_menu_item_id` is the current entry it
    takes the place of (None for a new one); `extracted_item_id` is the line it is published from."""

    product_id: UUID | None
    display_name: str
    options: tuple[PublishedOption, ...]
    bar_menu_item_id: UUID | None = None
    kind: MenuItemKind = MenuItemKind.WHISKY
    name_key: str | None = None
    extracted_item_id: UUID | None = None

    @property
    def key(self) -> ItemKey:
        return item_key(self.product_id, self.name_key)


@dataclass(frozen=True)
class Proposal:
    """A line to publish with its final product (None when published without one), menu name and options."""

    extracted_item_id: UUID
    product_id: UUID | None
    display_name: str
    options: tuple[PublishedOption, ...]
    kind: MenuItemKind = MenuItemKind.WHISKY
    name_key: str | None = None
    # The reviewer sent the menu name (correctedProductName); it replaces the board's name even when the
    # options are the same (spec 8.7). A name only read differently by the AI keeps the board's name.
    name_corrected: bool = False

    @property
    def key(self) -> ItemKey:
        return item_key(self.product_id, self.name_key)


@dataclass(frozen=True)
class AppliedChange:
    change_type: MenuChangeType
    extracted_item_id: UUID | None = None
    bar_menu_item_id: UUID | None = None


@dataclass(frozen=True)
class PublishPlan:
    entries: list[BoardEntry]
    changes: list[AppliedChange]
    # Unlinked items a line linked to a product (taken over, see plan_publish).
    linked_items: set[UUID] = field(default_factory=set)


def _same_options(a: tuple[PublishedOption, ...], b: tuple[PublishedOption, ...]) -> bool:
    return [o.key for o in a] == [o.key for o in b]


def plan_publish(
    proposals: list[Proposal],
    current: list[BoardEntry],
    *,
    mode: ImportMode,
    ignored_items: set[UUID],
    approved_removals: set[UUID],
    takeovers: dict[UUID, UUID] | None = None,
) -> PublishPlan:
    """proposals in menu order; current in board order; approved_removals are bar menu item ids;
    takeovers maps a line to the current unlinked item its applied update was compared with."""
    takeovers = takeovers or {}
    current_by_key = {entry.key: entry for entry in current}
    current_by_item = {entry.bar_menu_item_id: entry for entry in current}
    published: dict[ItemKey, BoardEntry] = {}  # by key, in menu order
    # What each current entry becomes, when a line is published in its place.
    slots: dict[UUID, BoardEntry] = {}
    linked_items: set[UUID] = set()
    changes: list[AppliedChange] = []

    for proposal in proposals:
        if proposal.extracted_item_id in ignored_items or proposal.key in published:
            continue
        on_board = current_by_key.get(proposal.key)
        taken = None
        if on_board is None and proposal.product_id is not None:
            taken = current_by_item.get(takeovers.get(proposal.extracted_item_id))
            if taken is not None and (taken.product_id is not None or taken.bar_menu_item_id in slots):
                taken = None
            on_board = taken
        if on_board is not None and on_board.bar_menu_item_id in slots:
            on_board = None
        unchanged = (
            on_board is not None
            and taken is None
            and on_board.kind == proposal.kind
            and _same_options(on_board.options, proposal.options)
            and not (proposal.name_corrected and proposal.display_name != on_board.display_name)
        )
        entry = on_board if unchanged else BoardEntry(
            proposal.product_id,
            proposal.display_name,
            proposal.options,
            on_board and on_board.bar_menu_item_id,
            kind=proposal.kind,
            name_key=proposal.name_key,
        )
        published[proposal.key] = replace(entry, extracted_item_id=proposal.extracted_item_id)
        if on_board is not None:
            slots[on_board.bar_menu_item_id] = published[proposal.key]
        if taken is not None:
            linked_items.add(taken.bar_menu_item_id)
        if unchanged:
            continue
        if on_board is None:
            changes.append(AppliedChange(MenuChangeType.ADD, extracted_item_id=proposal.extracted_item_id))
        else:
            changes.append(
                AppliedChange(
                    MenuChangeType.UPDATE,
                    extracted_item_id=proposal.extracted_item_id,
                    bar_menu_item_id=on_board.bar_menu_item_id,
                )
            )

    removed = [
        entry for entry in current if entry.bar_menu_item_id in approved_removals and entry.bar_menu_item_id not in slots
    ]
    changes.extend(AppliedChange(MenuChangeType.REMOVE, bar_menu_item_id=e.bar_menu_item_id) for e in removed)
    removed_ids = {entry.bar_menu_item_id for entry in removed}
    kept = [e for e in current if e.bar_menu_item_id not in removed_ids and e.bar_menu_item_id not in slots]

    if mode == ImportMode.FULL_REPLACE:
        entries = [*published.values(), *kept]
    else:
        in_place = [slots.get(e.bar_menu_item_id, e) for e in current if e.bar_menu_item_id not in removed_ids]
        entries = [*in_place, *(e for e in published.values() if e.bar_menu_item_id is None)]
    return PublishPlan(entries=entries, changes=changes, linked_items=linked_items)


def load_board(session: Session, bar_id: UUID) -> tuple[MenuBoard | None, list[BoardEntry]]:
    board = session.scalar(
        select(MenuBoard)
        .where(MenuBoard.bar_id == bar_id)
        .options(
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.options),
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.bar_menu_item),
        )
    )
    if board is None:
        return None, []
    return board, [
        BoardEntry(
            product_id=entry.bar_menu_item.product_id,
            display_name=entry.display_name,
            options=tuple(
                PublishedOption(o.option_label, o.pour_ml, o.price_krw, o.source_extracted_option_id)
                for o in entry.options
            ),
            bar_menu_item_id=entry.bar_menu_item_id,
            kind=entry.bar_menu_item.kind,
            name_key=entry.bar_menu_item.name_key,
        )
        for entry in board.entries
    ]


def proposals_from_review(session: Session, review: ValidatedReview, catalog: CatalogResult) -> list[Proposal]:
    """The lines published as menu items, in menu order. The menu name is the corrected name, else the
    extracted name, else the product's name (a line retyped as a product may have none). A line published
    without a product (spec 8.10) is keyed by its menu name."""
    product_names = dict(
        session.execute(
            select(Product.id, Product.display_name).where(Product.id.in_(set(catalog.product_ids.values())))
        ).all()
    )
    proposals = []
    for entry in review.items:
        if not entry.is_product:
            continue
        item = entry.item
        options = tuple(
            PublishedOption(o.label, o.pour_ml, o.price_krw, o.option.id if o.option else None) for o in entry.options
        )
        name_corrected = entry.decision.correctedProductName is not None
        if entry.is_unlinked:
            proposals.append(
                Proposal(
                    extracted_item_id=item.id,
                    product_id=None,
                    display_name=entry.menu_name,
                    options=options,
                    kind=MenuItemKind(entry.decision.kind),
                    name_key=name_key(entry.menu_name),
                    name_corrected=name_corrected,
                )
            )
            continue
        product_id = catalog.product_ids[item.id]
        proposals.append(
            Proposal(
                extracted_item_id=item.id,
                product_id=product_id,
                display_name=entry.menu_name or product_names[product_id],
                options=options,
                name_corrected=name_corrected,
            )
        )
    return proposals


def review_plan(
    session: Session, bar_id: UUID, mode: ImportMode, review: ValidatedReview, catalog: CatalogResult
) -> tuple[MenuBoard | None, PublishPlan]:
    """(board or None, plan) for a validated review whose catalog entries exist."""
    board, current = load_board(session, bar_id)
    decisions = review.change_decisions
    approved = {
        c.bar_menu_item_id
        for c in review.changes
        if c.change_type == MenuChangeType.REMOVE and decisions[c.id] == MenuChangeDecision.APPLY
    }
    # Every line of an applied update may be the one published in the compared entry's place.
    takeovers = {
        line: c.bar_menu_item_id
        for c in review.changes
        if c.change_type == MenuChangeType.UPDATE and decisions[c.id] == MenuChangeDecision.APPLY
        for line in review.change_lines.get(c.id, ())
    }
    plan = plan_publish(
        proposals_from_review(session, review, catalog),
        current,
        mode=mode,
        ignored_items=review.ignored_lines,
        approved_removals=approved,
        takeovers=takeovers,
    )
    return board, plan


def clear_sold_out(session: Session, bar_menu_item_ids: set[UUID]) -> None:
    """Put items that leave the board back on sale, so the same product added again starts on sale.

    An UPDATE that always touches the rows, rather than setting the attribute: a SERIALIZABLE request
    reads from a snapshot taken before it waited for the bar lock, so it may not see a sold-out mark
    committed meanwhile, and the ORM would skip a value it believes is already null. Touching the row
    turns that race into a serialization failure, and the retry sees the mark.
    """
    if bar_menu_item_ids:
        session.execute(
            update(BarMenuItem)
            .where(BarMenuItem.id.in_(bar_menu_item_ids))
            .values(sold_out_at=None)
        )


def _discounts(board: MenuBoard | None) -> dict[tuple, tuple]:
    """(discounted price, starts at, ends at) by (bar menu item, label, pour size, list price)."""
    if board is None:
        return {}
    return {
        (entry.bar_menu_item_id, o.option_label, o.pour_ml, o.price_krw): (
            o.discount_price_krw,
            o.discount_starts_at,
            o.discount_ends_at,
        )
        for entry in board.entries
        for o in entry.options
        if o.discount_price_krw is not None
    }


def _option(option: PublishedOption, sort_order: int, discount: tuple | None) -> MenuEntryOption:
    discount_price_krw, starts_at, ends_at = discount or (None, None, None)
    return MenuEntryOption(
        option_label=option.label,
        pour_ml=option.pour_ml,
        price_krw=option.price_krw,
        discount_price_krw=discount_price_krw,
        discount_starts_at=starts_at,
        discount_ends_at=ends_at,
        sort_order=sort_order,
        source_extracted_option_id=option.source_extracted_option_id,
    )


def _item_for(session: Session, bar_id: UUID, entry: BoardEntry, items: dict[UUID, BarMenuItem]) -> BarMenuItem:
    """The bar menu item `entry` is written with.

    - A product: the bar's item of that product (kept for good once the bar has sold it), or a new one.
      When the entry takes over a current unlinked item, that item is linked to the product, unless the
      bar sold the product before: its old item is used then and gets the unlinked item's sold-out mark.
    - No product: the current entry's item (its kind may change), or a new unlinked item.
    """
    current = items.get(entry.bar_menu_item_id) if entry.bar_menu_item_id else None
    if entry.product_id is None:
        if current is not None:
            current.kind = entry.kind
            return current
        item = BarMenuItem(bar_id=bar_id, kind=entry.kind, name_key=entry.name_key)
        session.add(item)
        session.flush()
        return item
    if current is not None and current.product_id == entry.product_id:
        return current
    sold_before = session.scalar(
        select(BarMenuItem).where(BarMenuItem.bar_id == bar_id, BarMenuItem.product_id == entry.product_id)
    )
    if current is not None and sold_before is None:
        current.product_id, current.name_key, current.kind = entry.product_id, None, MenuItemKind.WHISKY
        session.flush()
        return current
    if sold_before is None:
        sold_before = BarMenuItem(bar_id=bar_id, product_id=entry.product_id)
        session.add(sold_before)
        session.flush()
    elif current is not None:
        sold_before.sold_out_at = current.sold_out_at
    return sold_before


def write_board(
    session: Session,
    board: MenuBoard | None,
    bar_id: UUID,
    menu_import_id: UUID,
    entries: list[BoardEntry],
    *,
    published_at: datetime,
) -> tuple[MenuBoard, list[BarMenuItem]]:
    """Replace the bar's board contents with `entries`, mark it published by the import at
    `published_at`, and raise its version. The caller holds the bar row lock (spec 3.14.1).
    Returns the board and the bar menu item of each entry, in order."""
    discounts = _discounts(board)
    old_items = {entry.bar_menu_item_id: entry.bar_menu_item for entry in board.entries} if board is not None else {}
    if board is None:
        board = MenuBoard(bar_id=bar_id, published_at=published_at, version=1)
        session.add(board)
    else:
        board.version += 1
    board.published_at = published_at
    board.last_import_id = menu_import_id
    # Delete the old entries before inserting new ones: the unit of work would otherwise
    # insert first and hit the unique sort_order and bar_menu_item constraints.
    board.entries.clear()
    session.flush()

    items = [_item_for(session, bar_id, entry, old_items) for entry in entries]
    clear_sold_out(session, set(old_items) - {item.id for item in items})

    for sort_order, (entry, item) in enumerate(zip(entries, items), start=1):
        # A discount stays on the option of the same item, label, pour size and list price (spec 8.7).
        discount_item = entry.bar_menu_item_id or item.id
        board.entries.append(
            MenuBoardEntry(
                bar_menu_item_id=item.id,
                display_name=entry.display_name,
                sort_order=sort_order,
                options=[
                    _option(o, option_order, discounts.get((discount_item, *o.key)))
                    for option_order, o in enumerate(entry.options, start=1)
                ],
            )
        )
    session.flush()
    return board, items
