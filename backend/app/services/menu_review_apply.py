"""POST /api/menu-imports/{id}/review-and-apply: confirm the review and publish the menu in
one SERIALIZABLE transaction (API spec 8, flow doc 17).

Steps, all rolled back together on any error:

1. lock the bar row, then the import (spec 3.14.1: every request that changes a bar's menu
   takes the bar row first, so they run one after another); under the lock, an inactive bar is
   BAR_NOT_FOUND and the caller is checked again; an `applied` import returns its stored result
   (a retried request)
2. check the status and reviewVersion
3. rebuild the draft; if the board changed since it was made, store the new draft with a new
   reviewVersion and answer REVIEW_OUTDATED (the only write that is kept on an error)
4. validate the decisions (menu_review_validation)
5. create brands, products and aliases (menu_review_catalog)
6. record the decisions on extracted_items and extracted_options
7. publish the board (menu_publish): raise its version and stamp it with the time taken after
   the lock; record the applied changes in menu_import_changes
8. mark the import applied at the same time

A serialization failure reruns everything from step 1, up to three attempts in total
(app.services.serializable).
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import Principal
from app.models import (
    Bar,
    BarStatus,
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
    CreateProduct,
    ConfirmNonProduct,
    Reject,
    ReviewAndApplyRequest,
    ReviewAppliedResponse,
    ReviewResult,
    SelectExistingProduct,
)
from app.services.bar_access import can_manage_bar, forbidden, is_operator
from app.services.bar_menu import bar_not_found
from app.services.menu_draft import build_draft, replace_draft
from app.services.menu_publish import AppliedChange, review_plan, write_board
from app.services.menu_review_catalog import CatalogResult, create_catalog_entries
from app.services.menu_review_validation import ReviewedItem, ValidatedReview, pending_changes, validate_review
from app.services.serializable import SessionFactory, run_serializable, write_conflict
from app.services.users import caller_user_id


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
        if option is None:
            options_corrected = True
            continue
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


def _apply_once(
    session: Session, import_id: UUID, request: ReviewAndApplyRequest, principal: Principal
) -> ReviewAppliedResponse:
    # The route has checked that the import exists. Lock its bar before the import, the order every
    # menu request uses, so this cannot deadlock with a manual edit or an upload.
    bar_id = session.scalar(select(MenuImport.bar_id).where(MenuImport.id == import_id))
    status = session.scalar(select(Bar.status).where(Bar.id == bar_id).with_for_update())
    # Checked under the lock (spec 3.14.1): an inactive bar takes no menu change, and an owner revoked
    # after the route's check is refused here.
    if status != BarStatus.ACTIVE:
        raise bar_not_found(str(bar_id))
    if not can_manage_bar(session, principal, bar_id):
        raise forbidden()
    # clock_timestamp(), not now(): a publish that waited for the lock must not look older than a
    # request that committed while it waited (spec 3.14.1).
    published_at = session.scalar(select(func.clock_timestamp()))
    menu_import = session.scalar(select(MenuImport).where(MenuImport.id == import_id).with_for_update())
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
    # Review-and-apply currently writes directly into global products/aliases.
    # A bar owner must not mutate the shared catalog without operator approval.
    # Explicitly reject instead of silently publishing unapproved identities.
    if not is_operator(session, principal) and any(
        isinstance(entry.decision, CreateProduct)
        or (isinstance(entry.decision, SelectExistingProduct) and entry.decision.aliasesToAdd)
        for entry in review.items
    ):
        raise ApiError(
            403,
            "CATALOG_APPROVAL_REQUIRED",
            "신규 상품과 별칭은 관리자 승인 후 카탈로그에 등록할 수 있어요. 기존 상품만 연결해 주세요.",
        )
    catalog = create_catalog_entries(
        session, menu_import, review, created_by_user_id=caller_user_id(session, principal)
    )
    for entry in review.items:
        _record_item(entry, catalog)
    board, plan = review_plan(session, menu_import.bar_id, menu_import.mode, review, catalog)
    write_board(session, board, menu_import.bar_id, menu_import.id, plan.entries, published_at=published_at)
    _record_changes(session, menu_import, review, plan.changes)
    menu_import.status = ImportStatus.APPLIED
    menu_import.review_confirmed_at = published_at
    menu_import.completed_at = published_at
    session.flush()
    session.refresh(menu_import)
    return applied_response(session, menu_import)


def review_and_apply(
    session_factory: SessionFactory, import_id: UUID, request: ReviewAndApplyRequest, principal: Principal
) -> ReviewAppliedResponse:
    return run_serializable(
        session_factory,
        lambda session: _apply_once(session, import_id, request, principal),
        label=f"review-and-apply {import_id}",
        conflict=write_conflict(
            "다른 요청과 동시에 처리되어 반영하지 못했습니다. 잠시 후 다시 제출해 주세요.",
            details={"menuImportId": str(import_id)},
        ),
    )
