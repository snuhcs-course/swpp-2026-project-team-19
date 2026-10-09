# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #12). Reviewed by Haeul Yang.
"""POST /api/menu-imports/{id}/review-and-apply: confirm the review and publish the menu in
one SERIALIZABLE transaction (API spec 8, flow doc 17).

Steps, all rolled back together on any error:

1. lock the import; an `applied` import returns its stored result (a retried request)
2. check the status and reviewVersion
3. rebuild the draft; if the board changed since it was made, store the new draft with a new
   reviewVersion and answer REVIEW_OUTDATED (the only write that is kept on an error)
4. validate the decisions (menu_review_validation)
5. create brands, products and aliases (menu_review_catalog)
6. record the decisions on extracted_items and extracted_options
7. publish the board (menu_publish) and record the applied changes in menu_import_changes
8. mark the import applied

A serialization failure reruns everything from step 1, up to three attempts in total.
"""

import logging
import random
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import (
    Brand,
    ExtractedItem,
    ExtractionRun,
    ImportStatus,
    MatchMethod,
    MenuBoard,
    MenuChangeDecision,
    MenuChangeType,
    MenuImage,
    MenuImport,
    MenuImportChange,
    Product,
    ReviewStatus,
)
from app.schemas.menu_review import (
    ConfirmNonProduct,
    Reject,
    ReviewAndApplyRequest,
    ReviewAppliedResponse,
    ReviewResult,
    SelectExistingProduct,
)
from app.services.menu_draft import build_draft, replace_draft
from app.services.menu_import_review import menu_import_not_found
from app.services.menu_publish import AppliedChange, review_plan, write_board
from app.services.menu_review_catalog import CatalogResult, create_catalog_entries
from app.services.menu_review_validation import ReviewedItem, ValidatedReview, pending_changes, validate_review

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractContextManager[Session]]

MAX_ATTEMPTS = 3
# serialization_failure, deadlock_detected
RETRYABLE_SQLSTATES = {"40001", "40P01"}

# Replaced in tests so retries do not wait.
sleep = time.sleep


def _review_url(menu_import_id: UUID) -> str:
    return f"/api/menu-imports/{menu_import_id}"


def _outdated(menu_import: MenuImport, submitted: int) -> ApiError:
    return ApiError(
        409,
        "REVIEW_OUTDATED",
        "검수 데이터가 변경되었습니다. 최신 내용을 다시 확인해 주세요.",
        details={
            "menuImportId": str(menu_import.id),
            "submittedReviewVersion": submitted,
            "currentReviewVersion": menu_import.review_version,
            "reviewUrl": _review_url(menu_import.id),
        },
    )


def _change_key(change_type: MenuChangeType, extracted_item_id: UUID | None, bar_menu_item_id: UUID | None):
    """add/update belong to a menu line, remove to a board entry."""
    if change_type == MenuChangeType.REMOVE:
        return ("board", bar_menu_item_id)
    return ("line", extracted_item_id)


# ---- recording ----


def _record_item(entry: ReviewedItem, catalog: CatalogResult) -> None:
    item, decision = entry.item, entry.decision
    final_type = decision.finalLineType
    item.corrected_line_type = None if final_type == item.extracted_line_type else final_type
    item.reviewed_at = func.now()
    if isinstance(decision, (ConfirmNonProduct, Reject)):
        item.selected_product_id = item.selected_match_method = item.match_confidence = None
        item.corrected_product_name = None
        if isinstance(decision, Reject):
            item.review_status = ReviewStatus.REJECTED
        else:
            item.review_status = ReviewStatus.CONFIRMED if item.corrected_line_type is None else ReviewStatus.CORRECTED
        return

    product_id = catalog.product_ids[item.id]
    candidates = {c.product_id: c for c in item.candidates}
    top = item.candidates[0] if item.candidates else None
    kept_top = isinstance(decision, SelectExistingProduct) and top is not None and top.product_id == product_id
    item.selected_product_id = product_id
    # The rank-1 method only when the proposal was kept; any other choice is manual, but a
    # chosen candidate keeps the score the system gave it.
    item.selected_match_method = top.method if kept_top else MatchMethod.MANUAL
    item.match_confidence = candidates[product_id].score if product_id in candidates else None
    name = decision.correctedProductName
    item.corrected_product_name = name if name is not None and name != item.extracted_product_name else None

    options_corrected = False
    for final in entry.options:
        option = final.option
        option.corrected_option_label = final.label if final.label != option.extracted_option_label else None
        option.corrected_pour_ml = final.pour_ml if final.pour_ml != option.extracted_pour_ml else None
        option.corrected_price_krw = final.price_krw if final.price_krw != option.extracted_price_krw else None
        options_corrected |= any(
            v is not None for v in (option.corrected_option_label, option.corrected_pour_ml, option.corrected_price_krw)
        )
    unchanged = kept_top and item.corrected_line_type is None and item.corrected_product_name is None
    item.review_status = ReviewStatus.CONFIRMED if unchanged and not options_corrected else ReviewStatus.CORRECTED


def _record_changes(
    session: Session, menu_import: MenuImport, review: ValidatedReview, applied: list[AppliedChange]
) -> None:
    """Leave the changes actually applied (apply) and the ones the reviewer ignored (ignore).

    A draft row keeps its id and takes the final type when the reviewer's decisions changed it
    (e.g. an add became an update). An applied draft row that ended up changing nothing is
    deleted, and a change the draft did not have is inserted.
    """
    applied_by_key = {_change_key(c.change_type, c.extracted_item_id, c.bar_menu_item_id): c for c in applied}
    for row in review.changes:
        row.decision = review.change_decisions[row.id]
        row.reviewed_at = func.now()
        if row.decision == MenuChangeDecision.IGNORE:
            continue
        final = applied_by_key.pop(_change_key(row.change_type, row.extracted_item_id, row.bar_menu_item_id), None)
        if final is None:
            session.delete(row)
            continue
        row.change_type = final.change_type
        row.extracted_item_id = final.extracted_item_id
        row.bar_menu_item_id = final.bar_menu_item_id
    for change in applied_by_key.values():
        session.add(
            MenuImportChange(
                menu_import_id=menu_import.id,
                change_type=change.change_type,
                extracted_item_id=change.extracted_item_id,
                bar_menu_item_id=change.bar_menu_item_id,
                decision=MenuChangeDecision.APPLY,
                reviewed_at=func.now(),
            )
        )


def applied_response(session: Session, menu_import: MenuImport) -> ReviewAppliedResponse:
    """The result of an applied import, computed from what was stored, so a repeated request
    gets the same answer as the first one."""
    decisions = session.execute(
        select(MenuImportChange.change_type, MenuImportChange.decision).where(
            MenuImportChange.menu_import_id == menu_import.id
        )
    ).all()
    applied = [change_type for change_type, decision in decisions if decision == MenuChangeDecision.APPLY]
    import_items = (
        select(ExtractedItem.id)
        .join(ExtractionRun, ExtractionRun.id == ExtractedItem.extraction_run_id)
        .join(MenuImage, MenuImage.id == ExtractionRun.menu_image_id)
        .where(MenuImage.menu_import_id == menu_import.id)
    )
    created = session.execute(
        select(Product.created_at, Brand.id, Brand.created_at)
        .join(Brand, Brand.id == Product.brand_id)
        .where(Product.created_from_extracted_item_id.in_(import_items))
    ).all()
    # now() is fixed within a transaction, so a brand created by this review has the same
    # created_at as the products created with it.
    created_brands = {brand_id for product_at, brand_id, brand_at in created if brand_at == product_at}
    board_id = session.scalar(select(MenuBoard.id).where(MenuBoard.last_import_id == menu_import.id))
    return ReviewAppliedResponse(
        menuImportId=menu_import.id,
        status="applied",
        reviewVersion=menu_import.review_version,
        appliedAt=menu_import.review_confirmed_at,
        menuBoardId=board_id,
        result=ReviewResult(
            added=applied.count(MenuChangeType.ADD),
            updated=applied.count(MenuChangeType.UPDATE),
            removed=applied.count(MenuChangeType.REMOVE),
            ignored=sum(1 for _, decision in decisions if decision == MenuChangeDecision.IGNORE),
            createdBrands=len(created_brands),
            createdProducts=len(created),
        ),
    )


# ---- the transaction ----


def _draft_keys(changes) -> set[tuple]:
    return {(c.change_type, c.extracted_item_id, c.bar_menu_item_id) for c in changes}


def _apply_once(session: Session, menu_import_id: str, request: ReviewAndApplyRequest) -> ReviewAppliedResponse:
    try:
        import_id = UUID(menu_import_id)
    except ValueError:
        raise menu_import_not_found(menu_import_id) from None
    menu_import = session.scalar(select(MenuImport).where(MenuImport.id == import_id).with_for_update())
    if menu_import is None:
        raise menu_import_not_found(menu_import_id)
    if menu_import.status == ImportStatus.APPLIED:
        return applied_response(session, menu_import)
    if menu_import.status != ImportStatus.READY_FOR_REVIEW:
        raise ApiError(
            409,
            "INVALID_IMPORT_STATE",
            "지금 상태에서는 검수 결과를 제출할 수 없습니다.",
            details={"menuImportId": str(menu_import.id), "status": menu_import.status.value},
        )
    if request.reviewVersion != menu_import.review_version:
        raise _outdated(menu_import, request.reviewVersion)

    # The board may have changed since the draft was made; the reviewer then saw a stale diff.
    if _draft_keys(build_draft(session, menu_import)) != _draft_keys(pending_changes(session, menu_import)):
        replace_draft(session, menu_import)
        session.commit()
        raise _outdated(menu_import, request.reviewVersion)

    review = validate_review(session, menu_import, request)
    catalog = create_catalog_entries(session, menu_import, review)
    for entry in review.items:
        _record_item(entry, catalog)
    board, plan = review_plan(session, menu_import.bar_id, menu_import.mode, review, catalog)
    write_board(session, board, menu_import.bar_id, menu_import.id, plan.entries)
    _record_changes(session, menu_import, review, plan.changes)
    menu_import.status = ImportStatus.APPLIED
    menu_import.review_confirmed_at = func.now()
    menu_import.completed_at = func.now()
    session.flush()
    session.refresh(menu_import)
    return applied_response(session, menu_import)


def _is_retryable(error: DBAPIError) -> bool:
    return getattr(error.orig, "sqlstate", None) in RETRYABLE_SQLSTATES


def review_and_apply(
    session_factory: SessionFactory, menu_import_id: str, request: ReviewAndApplyRequest
) -> ReviewAppliedResponse:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        with session_factory() as session:
            try:
                response = _apply_once(session, menu_import_id, request)
                session.commit()
                return response
            except DBAPIError as error:
                session.rollback()
                if not _is_retryable(error):
                    raise
                logger.info("review-and-apply %s: write conflict, attempt %d", menu_import_id, attempt)
            except BaseException:
                session.rollback()
                raise
        if attempt < MAX_ATTEMPTS:
            sleep(random.uniform(0.05, 0.2) * attempt)
    raise ApiError(
        503,
        "TEMPORARY_WRITE_CONFLICT",
        "다른 요청과 동시에 처리되어 반영하지 못했습니다. 잠시 후 다시 제출해 주세요.",
        details={"menuImportId": menu_import_id},
    )
