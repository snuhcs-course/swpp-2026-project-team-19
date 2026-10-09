# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #11). Reviewed by Haeul Yang.
"""Read side of a menu import: progress while processing, the failure, or the full review payload."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.adapters.storage import ImageStorage
from app.core.errors import ApiError
from app.models import (
    ExtractedItem,
    ExtractionRun,
    ImportStatus,
    LineType,
    MenuBoard,
    MenuBoardEntry,
    MenuChangeType,
    MenuImage,
    MenuImport,
    MenuImportChange,
    PipelineStatus,
    Product,
)
from app.schemas.menu_import import (
    ChangeAfter,
    ChangeAfterOption,
    ChangeBefore,
    ChangeBeforeOption,
    ImportAppliedResponse,
    ImportFailedResponse,
    ImportFailure,
    ImportProcessingResponse,
    ImportProgress,
    ImportReviewResponse,
    MenuImportStatusResponse,
    NewProductDraft,
    ProposedChange,
    ReviewCandidate,
    ReviewImage,
    ReviewItem,
    ReviewOption,
)

POLL_AFTER_MS = 3000


def menu_import_not_found(menu_import_id: str) -> ApiError:
    return ApiError(
        404, "MENU_IMPORT_NOT_FOUND", "메뉴 등록 작업을 찾을 수 없습니다.", details={"menuImportId": menu_import_id}
    )


def _float(value) -> float | None:
    return float(value) if value is not None else None


def _load_import(session: Session, menu_import_id: str) -> MenuImport:
    try:
        import_id = UUID(menu_import_id)
    except ValueError:
        raise menu_import_not_found(menu_import_id) from None
    menu_import = session.scalar(
        select(MenuImport)
        .where(MenuImport.id == import_id)
        .options(
            selectinload(MenuImport.images)
            .selectinload(MenuImage.extraction_run)
            .selectinload(ExtractionRun.items)
            .options(selectinload(ExtractedItem.options), selectinload(ExtractedItem.candidates))
        )
    )
    if menu_import is None:
        raise menu_import_not_found(menu_import_id)
    return menu_import


def _progress(menu_import: MenuImport) -> ImportProgress:
    statuses = [image.extraction_run.status for image in menu_import.images]
    return ImportProgress(
        totalImages=len(statuses),
        completedImages=statuses.count(PipelineStatus.SUCCEEDED),
        failedImages=statuses.count(PipelineStatus.FAILED),
    )


def _absolute(url: str, base_url: str) -> str:
    # Object storage returns full signed URLs; local storage returns a path on this server.
    return url if url.startswith(("http://", "https://")) else base_url.rstrip("/") + url


def _candidate(candidate, products: dict[UUID, Product]) -> ReviewCandidate:
    product = products[candidate.product_id]
    return ReviewCandidate(
        productId=product.id,
        candidateRank=candidate.candidate_rank,
        displayName=product.display_name,
        brandId=product.brand_id,
        brandName=product.brand.canonical_name,
        category=product.category,
        ageYears=product.age_years,
        editionName=product.edition_name,
        abv=_float(product.abv),
        matchMethod=candidate.method,
        score=_float(candidate.score),
        evidence=candidate.evidence or {},
    )


def _review_item(item: ExtractedItem, products: dict[UUID, Product]) -> ReviewItem:
    effective = item.corrected_line_type or item.extracted_line_type
    return ReviewItem(
        extractedItemId=item.id,
        itemOrder=item.item_order,
        rawText=item.raw_text,
        extractedLineType=item.extracted_line_type,
        correctedLineType=item.corrected_line_type,
        effectiveLineType=effective,
        initialResolutionStatus=item.initial_resolution_status,
        extractedProductName=item.extracted_product_name,
        extractedBrandName=item.extracted_brand_name,
        extractedAgeYears=item.extracted_age_years,
        extractedEditionName=item.extracted_edition_name,
        extractedAbv=_float(item.extracted_abv),
        extractionConfidence=_float(item.extraction_confidence),
        proposedProductId=item.candidates[0].product_id if item.candidates else None,
        options=[
            ReviewOption(
                extractedOptionId=option.id,
                optionOrder=option.option_order,
                extractedOptionLabel=option.extracted_option_label,
                extractedPourMl=option.extracted_pour_ml,
                extractedPriceKrw=option.extracted_price_krw,
            )
            for option in item.options
        ],
        candidates=[_candidate(candidate, products) for candidate in item.candidates],
        newProductDraft=(
            NewProductDraft(
                brandText=item.extracted_brand_name,
                category="whisky",
                displayName=item.extracted_product_name,
                ageYears=item.extracted_age_years,
                editionName=item.extracted_edition_name,
                abv=_float(item.extracted_abv),
            )
            if effective == LineType.PRODUCT
            else None
        ),
    )


def _summary(change_type: MenuChangeType, name: str | None, option_count: int) -> str:
    name = name or "이름 없는 항목"
    if change_type == MenuChangeType.ADD:
        return f"{name} 추가 (가격 옵션 {option_count}개)"
    if change_type == MenuChangeType.UPDATE:
        return f"{name} 가격·용량 변경"
    return f"{name} 삭제"


def _review(session: Session, menu_import: MenuImport, storage: ImageStorage, base_url: str) -> ImportReviewResponse:
    items = {item.id: item for image in menu_import.images for item in image.extraction_run.items}
    menu_order = {
        item.id: (image.image_order, item.item_order) for image in menu_import.images for item in image.extraction_run.items
    }
    changes = list(
        session.scalars(select(MenuImportChange).where(MenuImportChange.menu_import_id == menu_import.id))
    )
    board = session.scalar(
        select(MenuBoard)
        .where(MenuBoard.bar_id == menu_import.bar_id)
        .options(
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.options),
            selectinload(MenuBoard.entries).selectinload(MenuBoardEntry.bar_menu_item),
        )
    )
    board_entries = {entry.bar_menu_item_id: entry for entry in (board.entries if board else [])}

    product_ids = {c.product_id for item in items.values() for c in item.candidates}
    product_ids |= {entry.bar_menu_item.product_id for entry in board_entries.values()}
    products = {
        product.id: product
        for product in session.scalars(
            select(Product).where(Product.id.in_(product_ids)).options(joinedload(Product.brand))
        )
    }

    proposed = []
    for change in changes:
        item = items.get(change.extracted_item_id) if change.extracted_item_id else None
        entry = board_entries.get(change.bar_menu_item_id) if change.bar_menu_item_id else None
        before = (
            ChangeBefore(
                productId=entry.bar_menu_item.product_id,
                displayName=products[entry.bar_menu_item.product_id].display_name,
                options=[
                    ChangeBeforeOption(
                        menuEntryOptionId=o.id, optionLabel=o.option_label, pourMl=o.pour_ml, priceKrw=o.price_krw
                    )
                    for o in entry.options
                ],
            )
            if entry is not None
            else None
        )
        after = None
        if item is not None:
            product_id = item.candidates[0].product_id if item.candidates else None
            after = ChangeAfter(
                productId=product_id,
                displayName=products[product_id].display_name if product_id else item.extracted_product_name,
                options=[
                    ChangeAfterOption(
                        extractedOptionId=o.id,
                        optionLabel=o.extracted_option_label,
                        pourMl=o.extracted_pour_ml,
                        priceKrw=o.extracted_price_krw,
                    )
                    for o in item.options
                ],
            )
        # add/update follow the photos (image, line); removes come last in board order.
        if item is not None:
            order = (0, *menu_order[item.id])
        else:
            order = (1, entry.sort_order if entry else 0, 0)
        name = (after or before).displayName if (after or before) else None
        proposed.append(
            (
                order,
                ProposedChange(
                    changeId=change.id,
                    changeType=change.change_type,
                    barMenuItemId=change.bar_menu_item_id,
                    extractedItemId=change.extracted_item_id,
                    before=before,
                    after=after,
                    summary=_summary(change.change_type, name, len(after.options) if after else 0),
                    decision=change.decision,
                ),
            )
        )
    proposed.sort(key=lambda pair: pair[0])

    images = []
    for image in menu_import.images:
        url, expires_at = storage.url(image.storage_key)
        images.append(
            ReviewImage(
                imageId=image.id,
                imageOrder=image.image_order,
                imageUrl=_absolute(url, base_url),
                imageUrlExpiresAt=expires_at,
                items=[_review_item(item, products) for item in image.extraction_run.items],
            )
        )
    return ImportReviewResponse(
        menuImportId=menu_import.id,
        barId=menu_import.bar_id,
        mode=menu_import.mode,
        status="ready_for_review",
        reviewVersion=menu_import.review_version,
        images=images,
        proposedChanges=[change for _, change in proposed],
    )


def get_menu_import_status(
    session: Session, menu_import_id: str, storage: ImageStorage, base_url: str
) -> MenuImportStatusResponse:
    menu_import = _load_import(session, menu_import_id)
    status = menu_import.status
    if status in (ImportStatus.UPLOADED, ImportStatus.PROCESSING):
        return ImportProcessingResponse(
            menuImportId=menu_import.id, status=status.value, progress=_progress(menu_import), pollAfterMs=POLL_AFTER_MS
        )
    if status == ImportStatus.FAILED:
        progress = _progress(menu_import)
        failure = (
            ImportFailure(code="IMAGE_EXTRACTION_FAILED", message="일부 메뉴 이미지를 처리하지 못했습니다.")
            if progress.failedImages
            else ImportFailure(code="PROCESSING_FAILED", message="메뉴를 처리하지 못했습니다.")
        )
        return ImportFailedResponse(menuImportId=menu_import.id, status="failed", progress=progress, failure=failure)
    if status == ImportStatus.APPLIED:
        board_id = session.scalar(select(MenuBoard.id).where(MenuBoard.last_import_id == menu_import.id))
        return ImportAppliedResponse(
            menuImportId=menu_import.id,
            barId=menu_import.bar_id,
            status="applied",
            reviewVersion=menu_import.review_version,
            appliedAt=menu_import.review_confirmed_at,
            menuBoardId=board_id,
        )
    return _review(session, menu_import, storage, base_url)
