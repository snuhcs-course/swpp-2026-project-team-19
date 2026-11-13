"""The operator's menu item check list (API spec 3.18.2). Reads only.

Open checks come oldest first, the order an operator works through them; resolved and dismissed checks
come newest first by when they closed. The cursor carries the filters, so a cursor from other filters is
INVALID_CURSOR instead of silently skipping rows. The number of queries does not grow with the page.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.adapters.storage import ImageStorage
from app.core.pagination import decode_cursor, encode_cursor
from app.models import (
    Bar,
    BarMenuItem,
    CheckStatus,
    ExtractedItem,
    ExtractionRun,
    MenuBoard,
    MenuBoardEntry,
    MenuImage,
    MenuItemCheck,
    Product,
)
from app.schemas.menu_check import (
    CheckBar,
    CheckItem,
    CheckItemOption,
    CheckProduct,
    CheckReasonResponse,
    CheckSource,
    DiscardedOption,
    MenuItemCheckPage,
    MenuItemCheckResponse,
)
from app.services.menu_import_review import source_boxes

StatusFilter = Literal["open", "resolved", "dismissed"]


def _absolute(url: str, base_url: str) -> str:
    # Object storage returns full signed URLs; local storage returns a path on this server.
    return url if url.startswith(("http://", "https://")) else base_url.rstrip("/") + url


def list_checks(
    session: Session,
    storage: ImageStorage,
    base_url: str,
    *,
    status: StatusFilter = "open",
    bar_id: UUID | None = None,
    limit: int = 100,
    cursor: str | None = None,
) -> MenuItemCheckPage:
    filters = [status, str(bar_id) if bar_id else None]
    oldest_first = status == "open"
    time = MenuItemCheck.created_at if oldest_first else MenuItemCheck.resolved_at
    stmt = select(MenuItemCheck).where(MenuItemCheck.status == CheckStatus(status))
    if bar_id is not None:
        stmt = stmt.where(MenuItemCheck.bar_id == bar_id)
    if cursor is not None:
        after_time, after_id = decode_cursor(cursor, lambda values: _cursor_key(values, filters))
        if oldest_first:
            stmt = stmt.where(tuple_(time, MenuItemCheck.id) > tuple_(after_time, after_id))
        else:
            # Newest first by time, then ids ascending within the same time.
            stmt = stmt.where((time < after_time) | ((time == after_time) & (MenuItemCheck.id > after_id)))
    stmt = stmt.order_by(time if oldest_first else time.desc(), MenuItemCheck.id)
    checks = list(session.scalars(stmt.options(selectinload(MenuItemCheck.reasons)).limit(limit + 1)))
    page, more = checks[:limit], len(checks) > limit
    last = page[-1] if page else None
    next_cursor = None
    if more:
        last_time = last.created_at if oldest_first else last.resolved_at
        next_cursor = encode_cursor([*filters, last_time.isoformat(), str(last.id)])
    return MenuItemCheckPage(items=check_responses(session, page, storage, base_url), nextCursor=next_cursor)


def _cursor_key(values: list, filters: list) -> tuple[datetime, UUID]:
    *stored_filters, time, check_id = values
    if stored_filters != filters or not isinstance(time, str) or not isinstance(check_id, str):
        raise ValueError("cursor from other filters")
    return datetime.fromisoformat(time), UUID(check_id)


def check_responses(
    session: Session, checks: list[MenuItemCheck], storage: ImageStorage, base_url: str
) -> list[MenuItemCheckResponse]:
    """The checks as the API sends them, loading what they refer to in a fixed number of queries."""
    if not checks:
        return []
    item_ids = {c.bar_menu_item_id for c in checks}
    items = {
        item.id: item
        for item in session.scalars(
            select(BarMenuItem)
            .where(BarMenuItem.id.in_(item_ids))
            .options(joinedload(BarMenuItem.product).joinedload(Product.brand))
        )
    }
    bars = {bar.id: bar for bar in session.scalars(select(Bar).where(Bar.id.in_({c.bar_id for c in checks})))}
    entries = {
        entry.bar_menu_item_id: entry
        for entry in session.scalars(
            select(MenuBoardEntry)
            .join(MenuBoard, MenuBoard.id == MenuBoardEntry.menu_board_id)
            .where(MenuBoardEntry.bar_menu_item_id.in_(item_ids))
            .options(selectinload(MenuBoardEntry.options))
        )
    }
    line_ids = {r.source_extracted_item_id for c in checks for r in c.reasons if r.source_extracted_item_id}
    sources = _sources(session, line_ids, storage, base_url)
    return [_response(c, items[c.bar_menu_item_id], bars[c.bar_id], entries, sources) for c in checks]


def _sources(session: Session, line_ids: set[UUID], storage: ImageStorage, base_url: str) -> dict[UUID, CheckSource]:
    if not line_ids:
        return {}
    rows = session.execute(
        select(ExtractedItem, ExtractionRun.raw_output, MenuImage.storage_key, MenuImage.menu_import_id)
        .join(ExtractionRun, ExtractionRun.id == ExtractedItem.extraction_run_id)
        .join(MenuImage, MenuImage.id == ExtractionRun.menu_image_id)
        .where(ExtractedItem.id.in_(line_ids))
    ).all()
    sources = {}
    for line, raw_output, storage_key, menu_import_id in rows:
        url, expires_at = storage.url(storage_key)
        sources[line.id] = CheckSource(
            menuImportId=menu_import_id,
            extractedItemId=line.id,
            rawText=line.raw_text,
            sourceBox=source_boxes(raw_output).get(line.item_order),
            imageUrl=_absolute(url, base_url),
            imageUrlExpiresAt=expires_at,
            extractedProductName=line.extracted_product_name,
            extractedBrandName=line.extracted_brand_name,
            extractedAgeYears=line.extracted_age_years,
            extractedEditionName=line.extracted_edition_name,
        )
    return sources


def _response(
    check: MenuItemCheck,
    item: BarMenuItem,
    bar: Bar,
    entries: dict[UUID, MenuBoardEntry],
    sources: dict[UUID, CheckSource],
) -> MenuItemCheckResponse:
    entry = entries.get(item.id)
    product = item.product
    return MenuItemCheckResponse(
        checkId=check.id,
        status=check.status,
        reasons=[
            CheckReasonResponse(
                reason=r.reason,
                addedAt=r.added_at,
                source=sources.get(r.source_extracted_item_id) if r.source_extracted_item_id else None,
            )
            for r in check.reasons
        ],
        createdAt=check.created_at,
        resolvedAt=check.resolved_at,
        resolution=check.resolution,
        resolvedProductId=check.resolved_product_id,
        discardedOptions=[DiscardedOption(**option) for option in check.discarded_options],
        bar=CheckBar(barId=bar.id, name=bar.name, status=bar.status.value),
        item=CheckItem(
            barMenuItemId=item.id,
            kind=item.kind,
            displayName=entry.display_name if entry is not None else check.display_name,
            onBoard=entry is not None,
            soldOut=item.sold_out_at is not None,
            product=(
                CheckProduct(
                    productId=product.id,
                    displayName=product.display_name,
                    brandId=product.brand_id,
                    brandName=product.brand.canonical_name,
                    category=product.category,
                    ageYears=product.age_years,
                    editionName=product.edition_name,
                )
                if product is not None
                else None
            ),
            options=[
                CheckItemOption(optionLabel=o.option_label, pourMl=o.pour_ml, priceKrw=o.price_krw)
                for o in (entry.options if entry is not None else [])
            ],
        ),
    )
