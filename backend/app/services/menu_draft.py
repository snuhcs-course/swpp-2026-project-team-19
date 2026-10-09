# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #12). Reviewed by Haeul Yang.
"""Draft diff of a menu import against its bar's current menu board, built from stored rows.

The proposal for each product item is its rank-1 resolution candidate (none when unmatched)
with the extracted options. Processing builds the first draft with this, and review
submission rebuilds it to tell whether the board changed since the draft was made.
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    ExtractedItem,
    ExtractionRun,
    LineType,
    MenuBoard,
    MenuBoardEntry,
    MenuImage,
    MenuImport,
    MenuImportChange,
    ResolutionCandidate,
)
from app.services.menu_diff import CurrentEntry, DraftChange, ProposedEntry, compute_draft_changes


def product_items(session: Session, menu_import: MenuImport) -> list[ExtractedItem]:
    """Items the AI classified as products, in menu order (image, then line), with options."""
    query = (
        select(ExtractedItem)
        .join(ExtractionRun, ExtractionRun.id == ExtractedItem.extraction_run_id)
        .join(MenuImage, MenuImage.id == ExtractionRun.menu_image_id)
        .where(MenuImage.menu_import_id == menu_import.id, ExtractedItem.extracted_line_type == LineType.PRODUCT)
        .order_by(MenuImage.image_order, ExtractedItem.item_order)
        .options(selectinload(ExtractedItem.options))
    )
    return list(session.scalars(query))


def current_board(session: Session, bar_id: UUID) -> list[CurrentEntry]:
    board = session.scalar(
        select(MenuBoard)
        .where(MenuBoard.bar_id == bar_id)
        .options(
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.options),
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.bar_menu_item),
        )
    )
    if board is None:
        return []
    return [
        CurrentEntry(
            bar_menu_item_id=entry.bar_menu_item_id,
            product_id=entry.bar_menu_item.product_id,
            options=tuple((o.option_label, o.pour_ml, o.price_krw) for o in entry.options),
        )
        for entry in board.entries
    ]


def build_draft(session: Session, menu_import: MenuImport) -> list[DraftChange]:
    """The draft changes as of now. Reads only."""
    items = product_items(session, menu_import)
    # Read candidates with a query rather than item.candidates, which may have been loaded
    # before processing added them in this session.
    proposed_products = dict(
        session.execute(
            select(ResolutionCandidate.extracted_item_id, ResolutionCandidate.product_id).where(
                ResolutionCandidate.extracted_item_id.in_([item.id for item in items]),
                ResolutionCandidate.candidate_rank == 1,
            )
        ).all()
    )
    proposed = [
        ProposedEntry(
            extracted_item_id=item.id,
            product_id=proposed_products.get(item.id),
            options=tuple((o.extracted_option_label, o.extracted_pour_ml, o.extracted_price_krw) for o in item.options),
        )
        for item in items
    ]
    return compute_draft_changes(proposed, current_board(session, menu_import.bar_id), menu_import.mode)


def replace_draft(session: Session, menu_import: MenuImport) -> None:
    """Replace the stored draft with a fresh one. Only the latest draft is kept, and
    regenerating it bumps review_version so submissions against the old one are rejected."""
    changes = build_draft(session, menu_import)
    session.execute(delete(MenuImportChange).where(MenuImportChange.menu_import_id == menu_import.id))
    for change in changes:
        session.add(
            MenuImportChange(
                menu_import_id=menu_import.id,
                change_type=change.change_type,
                bar_menu_item_id=change.bar_menu_item_id,
                extracted_item_id=change.extracted_item_id,
            )
        )
    menu_import.review_version += 1
