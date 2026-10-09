# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #12). Reviewed by Haeul Yang.
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
  publishes its product again.
- Order: full_replace follows the photos, then the entries kept from the old board in their
  old order. partial_update keeps the old order with updates in place and appends adds.

`plan_publish` decides all of this from plain data; `write_board` stores the result.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    BarMenuItem,
    ImportMode,
    MenuBoard,
    MenuBoardEntry,
    MenuChangeDecision,
    MenuChangeType,
    MenuEntryOption,
    Product,
)
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
    """An entry on the current board, or one to be written."""

    product_id: UUID
    display_name: str
    options: tuple[PublishedOption, ...]
    bar_menu_item_id: UUID | None = None


@dataclass(frozen=True)
class Proposal:
    """A product decision with its final product, menu name and priced options."""

    extracted_item_id: UUID
    product_id: UUID
    display_name: str
    options: tuple[PublishedOption, ...]


@dataclass(frozen=True)
class AppliedChange:
    change_type: MenuChangeType
    extracted_item_id: UUID | None = None
    bar_menu_item_id: UUID | None = None


@dataclass(frozen=True)
class PublishPlan:
    entries: list[BoardEntry]
    changes: list[AppliedChange]


def _same_options(a: tuple[PublishedOption, ...], b: tuple[PublishedOption, ...]) -> bool:
    return [o.key for o in a] == [o.key for o in b]


def plan_publish(
    proposals: list[Proposal],
    current: list[BoardEntry],
    *,
    mode: ImportMode,
    ignored_items: set[UUID],
    approved_removals: set[UUID],
) -> PublishPlan:
    """proposals in menu order; current in board order; approved_removals are bar menu item ids."""
    current_by_product = {entry.product_id: entry for entry in current}
    published: dict[UUID, BoardEntry] = {}  # by product, in menu order
    changes: list[AppliedChange] = []

    for proposal in proposals:
        if proposal.extracted_item_id in ignored_items or proposal.product_id in published:
            continue
        on_board = current_by_product.get(proposal.product_id)
        if on_board is not None and _same_options(on_board.options, proposal.options):
            published[proposal.product_id] = on_board
            continue
        published[proposal.product_id] = BoardEntry(
            proposal.product_id, proposal.display_name, proposal.options, on_board and on_board.bar_menu_item_id
        )
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
        entry
        for entry in current
        if entry.bar_menu_item_id in approved_removals and entry.product_id not in published
    ]
    changes.extend(AppliedChange(MenuChangeType.REMOVE, bar_menu_item_id=e.bar_menu_item_id) for e in removed)
    removed_ids = {entry.bar_menu_item_id for entry in removed}
    kept = [e for e in current if e.bar_menu_item_id not in removed_ids and e.product_id not in published]

    if mode == ImportMode.FULL_REPLACE:
        entries = [*published.values(), *kept]
    else:
        in_place = [published.get(e.product_id, e) for e in current if e.bar_menu_item_id not in removed_ids]
        on_board = {e.product_id for e in current}
        entries = [*in_place, *(e for product_id, e in published.items() if product_id not in on_board)]
    return PublishPlan(entries=entries, changes=changes)


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
        )
        for entry in board.entries
    ]


def proposals_from_review(session: Session, review: ValidatedReview, catalog: CatalogResult) -> list[Proposal]:
    """The product decisions in menu order. The menu name is the corrected name, else the
    extracted name, else the product's name (a line retyped as a product may have none)."""
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
        product_id = catalog.product_ids[item.id]
        proposals.append(
            Proposal(
                extracted_item_id=item.id,
                product_id=product_id,
                display_name=(
                    entry.decision.correctedProductName or item.extracted_product_name or product_names[product_id]
                ),
                options=tuple(
                    PublishedOption(o.label, o.pour_ml, o.price_krw, o.option.id) for o in entry.priced_options
                ),
            )
        )
    return proposals


def review_plan(
    session: Session, bar_id: UUID, mode: ImportMode, review: ValidatedReview, catalog: CatalogResult
) -> tuple[MenuBoard | None, PublishPlan]:
    """(board or None, plan) for a validated review whose catalog entries exist."""
    board, current = load_board(session, bar_id)
    decisions = review.change_decisions
    ignored = {
        c.extracted_item_id
        for c in review.changes
        if c.extracted_item_id and decisions[c.id] == MenuChangeDecision.IGNORE
    }
    approved = {
        c.bar_menu_item_id
        for c in review.changes
        if c.change_type == MenuChangeType.REMOVE and decisions[c.id] == MenuChangeDecision.APPLY
    }
    plan = plan_publish(
        proposals_from_review(session, review, catalog),
        current,
        mode=mode,
        ignored_items=ignored,
        approved_removals=approved,
    )
    return board, plan


def write_board(
    session: Session, board: MenuBoard | None, bar_id: UUID, menu_import_id: UUID, entries: list[BoardEntry]
) -> MenuBoard:
    """Replace the bar's board contents with `entries` and mark it published by the import."""
    if board is None:
        board = MenuBoard(bar_id=bar_id, published_at=func.now())
        session.add(board)
    board.published_at = func.now()
    board.last_import_id = menu_import_id
    # Delete the old entries before inserting new ones: the unit of work would otherwise
    # insert first and hit the unique sort_order and bar_menu_item constraints.
    board.entries.clear()
    session.flush()

    item_ids = dict(
        session.execute(
            select(BarMenuItem.product_id, BarMenuItem.id).where(
                BarMenuItem.bar_id == bar_id, BarMenuItem.product_id.in_({e.product_id for e in entries})
            )
        ).all()
    )
    for entry in entries:
        if entry.product_id not in item_ids:
            # A bar menu item is kept for good once the bar has sold the product.
            item = BarMenuItem(bar_id=bar_id, product_id=entry.product_id)
            session.add(item)
            session.flush()
            item_ids[entry.product_id] = item.id

    for sort_order, entry in enumerate(entries, start=1):
        board.entries.append(
            MenuBoardEntry(
                bar_menu_item_id=item_ids[entry.product_id],
                display_name=entry.display_name,
                sort_order=sort_order,
                options=[
                    MenuEntryOption(
                        option_label=o.label,
                        pour_ml=o.pour_ml,
                        price_krw=o.price_krw,
                        sort_order=option_order,
                        source_extracted_option_id=o.source_extracted_option_id,
                    )
                    for option_order, o in enumerate(entry.options, start=1)
                ],
            )
        )
    session.flush()
    return board
