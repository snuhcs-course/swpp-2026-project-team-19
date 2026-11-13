"""Background processing of a menu import after the upload request has returned.

For each image in order: extract → store items and options (committed per image so
polling shows progress). Then match every product item, store candidates, build the draft
diff, and move the import to ready_for_review. The first failed image fails the import and
the remaining images are not extracted, since the import cannot be reviewed anyway.

Matching runs the rule stages S1–S3 and, when the LLM matching layer is configured
(MATCHING_LLM_ENABLED, see `app.api.deps.get_matching_llm_layer`), the M3 layer on the lines
they did not confirm, or with MATCHING_LLM_MODE=tools the tool-calling layer (E10,
`app.matching.tool_layer`). The layer only adds candidates: its lines are ambiguous, and any
failure in it leaves the rule results as they were. Last, when EMBEDDING_ENABLED=true, the
embedding step (`app.matching.embedding`) works on those results: lines still unmatched get up to
five similar products as ambiguous candidates, and ambiguous lines without a confirmRecommended
candidate are reordered. It never confirms, and a failure in it keeps the earlier results too.

Processing runs inside the API process, so a restart stops it. At start-up the unfinished
imports (`uploaded`, `processing`) are resumed: an image's items are committed together with
its run's `succeeded`, so a `running` run left behind stored nothing and is queued again, and
matching writes nothing until its final commit. An import is resumed at most MAX_RECOVERIES
times, so an image that crashes the process cannot make it restart forever.

An import can be canceled while it is processed (app.services.menu_import_cancel). Before each
commit the job locks the import row, which the cancel locks too, and stops without writing if it
is no longer `processing`; a canceled import is not resumed either.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.extraction import ExtractedItemData, ExtractionError, MenuExtractor
from app.adapters.storage import ImageStorage
from app.matching import ExtractedProduct, ResolutionResult
from app.matching.db_catalog import CatalogSnapshot, DbCatalog
from app.matching.embedding import EmbeddingStep, get_embedding_step, summarize
from app.matching.llm_layer import CONFIRMED, M3Engine
from app.matching.linking_guards import apply_linking_guards
from app.matching.product_draft import draft_from_name
from app.matching.review_state import stored_status
from app.matching.staged import resolve_product_staged
from app.matching.tool_config import CappedToolLLM, MatchingLayerConfig, ToolLayerConfig
from app.matching.tool_layer import ToolEngine
from app.models import (
    ExtractedItem,
    ExtractedOption,
    ExtractionRun,
    ImportStatus,
    MatchMethod,
    MenuImport,
    PipelineStatus,
    ResolutionCandidate,
    ResolutionStatus,
)
from app.services.menu_draft import product_items, replace_draft
from app.services.menu_import_upload import detect_image_type

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractContextManager[Session]]

MAX_RECOVERIES = 3
_RESUMABLE = (ImportStatus.UPLOADED, ImportStatus.PROCESSING)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def start_processing(
    session: Session,
    background_tasks: BackgroundTasks,
    menu_import: MenuImport,
    *,
    session_factory: SessionFactory,
    storage: ImageStorage,
    extractor: MenuExtractor,
    llm_layer: MatchingLayerConfig | None = None,
) -> None:
    """Called after the import rows are committed, so the job never sees uncommitted rows.

    The import can be canceled once it is committed, so the row is locked and processing starts
    only while it is still `uploaded`.
    """
    session.refresh(menu_import, with_for_update=True)
    if menu_import.status != ImportStatus.UPLOADED:
        session.commit()
        return
    menu_import.status = ImportStatus.PROCESSING
    session.commit()
    background_tasks.add_task(
        process_menu_import, session_factory, storage, extractor, menu_import.id, llm_layer=llm_layer
    )


def process_menu_import(
    session_factory: SessionFactory,
    storage: ImageStorage,
    extractor: MenuExtractor,
    import_id: UUID,
    *,
    llm_layer: MatchingLayerConfig | None = None,
) -> None:
    with session_factory() as session:
        menu_import = session.get(MenuImport, import_id)
        if menu_import is None or menu_import.status != ImportStatus.PROCESSING:
            return
        try:
            if not _extract_all(session, storage, extractor, menu_import):
                return
            _resolve_and_draft(session, menu_import, llm_layer)
            if not _still_processing(session, import_id):
                session.rollback()
                return
            menu_import.status = ImportStatus.READY_FOR_REVIEW
            session.commit()
        except Exception:
            # A bug must not leave the import in processing forever.
            logger.exception("Menu import %s failed during processing", import_id)
            session.rollback()
            menu_import = session.get(MenuImport, import_id, with_for_update=True)
            if menu_import is not None and menu_import.status == ImportStatus.PROCESSING:
                menu_import.status = ImportStatus.FAILED
                menu_import.completed_at = _now()
            session.commit()


def _still_processing(session: Session, import_id: UUID) -> bool:
    """Lock the import row until the next commit and tell whether it is still `processing`.

    Called before each commit of the job: a cancel locks the same row, so it either commits first
    and the job stops here, or waits until the job's commit and sees what it wrote.
    """
    stmt = select(MenuImport.status).where(MenuImport.id == import_id).with_for_update()
    return session.scalar(stmt) == ImportStatus.PROCESSING


def find_unfinished_imports(session_factory: SessionFactory) -> list[UUID]:
    """Imports a restart left `uploaded` or `processing`, oldest first.

    Call it before the server takes requests: the API runs as one process, so at that point nothing
    in it is processing, and an upload made after it cannot be mistaken for an interrupted one.
    """
    with session_factory() as session:
        return list(
            session.scalars(
                select(MenuImport.id).where(MenuImport.status.in_(_RESUMABLE)).order_by(MenuImport.created_at)
            )
        )


def recover_imports(
    import_ids: list[UUID],
    session_factory: SessionFactory,
    storage: ImageStorage,
    extractor: MenuExtractor,
    *,
    llm_layer: MatchingLayerConfig | None = None,
) -> None:
    """Resume the given interrupted imports one by one; one that cannot be resumed does not stop the rest."""
    for import_id in import_ids:
        try:
            if _prepare_resume(session_factory, import_id):
                process_menu_import(session_factory, storage, extractor, import_id, llm_layer=llm_layer)
        except Exception:
            logger.exception("Menu import %s could not be recovered", import_id)


def _prepare_resume(session_factory: SessionFactory, import_id: UUID) -> bool:
    """Queue the interrupted run again and count the recovery, or fail the import past the limit.
    Returns whether to process it now."""
    with session_factory() as session:
        menu_import = session.get(MenuImport, import_id, with_for_update=True)
        if menu_import is None or menu_import.status not in _RESUMABLE:
            # No longer unfinished since it was found.
            return False
        interrupted = [
            image.extraction_run
            for image in menu_import.images
            if image.extraction_run is not None and image.extraction_run.status == PipelineStatus.RUNNING
        ]
        if menu_import.recovery_count >= MAX_RECOVERIES:
            now = _now()
            # A run interrupted again points at the image; without one the import fails as a whole.
            for run in interrupted:
                run.status = PipelineStatus.FAILED
                run.raw_output = {"error": "Interrupted", "message": "The server restarted during extraction"}
                run.completed_at = now
            menu_import.status = ImportStatus.FAILED
            menu_import.completed_at = now
            session.commit()
            logger.warning("Menu import %s failed after %d recoveries", import_id, MAX_RECOVERIES)
            return False
        menu_import.recovery_count += 1
        for run in interrupted:
            run.status = PipelineStatus.QUEUED
            run.started_at = None
        menu_import.status = ImportStatus.PROCESSING
        session.commit()
        logger.info(
            "Resuming menu import %s (recovery %d of %d)", import_id, menu_import.recovery_count, MAX_RECOVERIES
        )
        return True


def _extract_all(session: Session, storage: ImageStorage, extractor: MenuExtractor, menu_import: MenuImport) -> bool:
    """Extract queued images in order. Returns False when processing ended here: at the first failed
    image, which fails the import, or when the import was canceled, which leaves it as it is."""
    import_id = menu_import.id
    for image in menu_import.images:
        run = image.extraction_run
        if run.status != PipelineStatus.QUEUED:
            continue
        # Read before the commit: after it, attribute access would open a new transaction and
        # hold it for the whole extraction call, which can take minutes with a real model.
        storage_key, filename = image.storage_key, image.original_filename
        if not _still_processing(session, import_id):
            session.rollback()
            return False
        run.status = PipelineStatus.RUNNING
        run.started_at = _now()
        session.commit()
        try:
            data = storage.read(storage_key)
            detected = detect_image_type(data)
            result = extractor.extract(data, detected[1] if detected else "application/octet-stream", filename)
        except (ExtractionError, OSError) as error:
            # The cancel has already ended the run; the error is not stored.
            if not _still_processing(session, import_id):
                session.rollback()
                return False
            run.status = PipelineStatus.FAILED
            run.raw_output = {"error": type(error).__name__, "message": str(error)}
            if isinstance(error, ExtractionError) and error.raw_output is not None:
                run.raw_output["output"] = error.raw_output
            run.completed_at = _now()
            menu_import.status = ImportStatus.FAILED
            menu_import.completed_at = run.completed_at
            session.commit()
            return False
        if not _still_processing(session, import_id):
            session.rollback()
            return False
        for item in result.items:
            _store_item(session, run, item)
        run.status = PipelineStatus.SUCCEEDED
        run.raw_output = result.raw_output
        run.completed_at = _now()
        session.commit()
    return True


def _store_item(session: Session, run: ExtractionRun, data: ExtractedItemData) -> None:
    item = ExtractedItem(
        extraction_run_id=run.id,
        item_order=data.item_order,
        raw_text=data.raw_text,
        extracted_line_type=data.line_type,
        extracted_product_name=data.product_name,
        extracted_brand_name=data.brand_text,
        extracted_age_years=data.age_years,
        extracted_edition_name=data.edition_name,
        extracted_abv=data.abv,
        extraction_confidence=data.confidence,
    )
    session.add(item)
    session.flush()
    for order, option in enumerate(data.options, start=1):
        session.add(
            ExtractedOption(
                extracted_item_id=item.id,
                option_order=order,
                extracted_option_label=option.option_label,
                extracted_price_krw=option.price_krw,
                extracted_pour_ml=option.pour_ml,
            )
        )


# Rule stages evaluated in I2 (P22, P47): name variants, brand + age/edition, default product,
# edit distance. The LLM layer (M3, app.matching.llm_layer) runs after them only when configured.
MATCHING_STAGES = frozenset({"S1", "S2", "S2b", "S3"})


def _resolve_and_draft(session: Session, menu_import: MenuImport, llm_layer: MatchingLayerConfig | None = None) -> None:
    catalog = DbCatalog(session)
    items = product_items(session, menu_import)
    results = {
        item.id: resolve_product_staged(
            ExtractedProduct(
                product_name=item.extracted_product_name,
                brand_name=item.extracted_brand_name,
                age_years=item.extracted_age_years,
                edition_name=item.extracted_edition_name,
                abv=item.extracted_abv,
            ),
            catalog,
            MATCHING_STAGES,
        )
        for item in items
    }
    if llm_layer is not None and any(result.status not in CONFIRMED for result in results.values()):
        results = _apply_llm_layer(session, menu_import.id, items, results, llm_layer)
        # The layer ended the read transaction, which expired the loaded rows; load them again.
        items = product_items(session, menu_import)
    embedding = get_embedding_step()
    if embedding is not None:
        results = _apply_embedding(session, menu_import.id, items, results, embedding)
    for item in items:
        # Last step: a confirmed match to an unchecked product becomes a recommendation (I4-P18).
        result = apply_linking_guards(item.extracted_product_name, results[item.id], catalog)
        # exact_match only for a line that needs no review (I4-P24, app.matching.review_state).
        # "multi" (one line naming two products) has no stored status: the line stays ambiguous
        # with both products as candidates (evidence "multiProduct"), and the reviewer decides.
        item.initial_resolution_status = ResolutionStatus(stored_status(result))
        if item.initial_resolution_status is not ResolutionStatus.EXACT_MATCH:
            _fill_product_parts(item, catalog)
        for candidate in result.candidates:
            session.add(
                ResolutionCandidate(
                    extracted_item_id=item.id,
                    product_id=candidate.product_id,
                    candidate_rank=candidate.rank,
                    score=Decimal(str(candidate.score)),
                    method=MatchMethod(candidate.method),
                    evidence=candidate.evidence,
                )
            )
    session.flush()
    replace_draft(session, menu_import)


def _fill_product_parts(item: ExtractedItem, catalog: DbCatalog) -> None:
    """Brand, age and edition read from the name of a line that has no confirmed product (I4-P18),
    so the new-product form (`newProductDraft`) opens filled in. Extraction leaves these fields
    empty; a line that already has one of them is left as it is."""
    if (item.extracted_brand_name, item.extracted_age_years, item.extracted_edition_name) != (None, None, None):
        return
    draft = draft_from_name(item.extracted_product_name, catalog)
    if draft is None:
        return
    edition = draft.edition_english or draft.edition_text
    item.extracted_brand_name = draft.brand_text[:120] if draft.brand_text else None
    item.extracted_age_years = draft.age_years
    item.extracted_edition_name = edition[:150] if edition else None


def _apply_llm_layer(
    session: Session,
    import_id: UUID,
    items: list[ExtractedItem],
    results: dict[UUID, ResolutionResult],
    llm_layer: MatchingLayerConfig,
) -> dict[UUID, ResolutionResult]:
    """Run M3 (or the tool layer) on the lines S1–S3 did not confirm; on any failure return `results` unchanged.

    Lines are the product names of one image (one extraction run) in menu order, each name
    once; M3a is called for every image first, then lines are resolved in menu order (with
    M3b if enabled), until the call cap is reached. Nothing is written here.
    """
    try:
        lines: dict[str, list[str]] = {}
        targets: dict[str, set[str]] = {}
        unconfirmed: list[tuple[UUID, str, str]] = []  # item id, image (run) id, name
        for item in items:
            name = item.extracted_product_name
            if name is None:
                continue
            image = str(item.extraction_run_id)
            image_lines = lines.setdefault(image, [])
            if name not in image_lines:
                image_lines.append(name)
            if results[item.id].status not in CONFIRMED:
                targets.setdefault(image, set()).add(name)
                unconfirmed.append((item.id, image, name))
        catalog = CatalogSnapshot(session)
        # Nothing is written yet; end the read transaction so it is not held during the model calls.
        session.commit()

        if isinstance(llm_layer, ToolLayerConfig):
            resolved, stats = _run_tool_layer(llm_layer, lines, targets, unconfirmed, catalog, results)
        else:
            engine = M3Engine(llm_layer.llm, lines, catalog.meta, max_calls=llm_layer.max_calls)
            for image in lines:
                engine.translate(image, targets.get(image, set()))
            resolved = dict(results)
            for item_id, image, name in unconfirmed:
                resolved[item_id] = engine.resolve(image, name, catalog, results[item_id], use_m3b=llm_layer.use_m3b)
            stats = dict(engine.stats)
    except Exception:
        logger.exception("Menu import %s: the LLM matching layer failed; keeping the rule results", import_id)
        session.rollback()
        return results
    changed = sum(resolved[item_id] is not results[item_id] for item_id, _, _ in unconfirmed)
    logger.info(
        "Menu import %s: LLM matching layer gave candidates to %d of %d unconfirmed lines (requests: %s)",
        import_id, changed, len(unconfirmed), stats or "none",
    )
    return resolved


def _apply_embedding(
    session: Session,
    import_id: UUID,
    items: list[ExtractedItem],
    results: dict[UUID, ResolutionResult],
    embedding: EmbeddingStep,
) -> dict[UUID, ResolutionResult]:
    """Run the embedding step on the results of the earlier steps (rules, then the LLM layer if it ran);
    on any failure return `results` unchanged. Only reads: nothing is written before this point."""
    try:
        resolved = embedding.apply(session, {item.id: item.extracted_product_name for item in items}, results)
    except Exception:
        logger.exception("Menu import %s: the embedding step failed; keeping the earlier results", import_id)
        # Only reads happened in this transaction; the rows reload on their next access.
        session.rollback()
        return results
    logger.info(
        "Menu import %s: embedding step (%s, floor %s): %s",
        import_id, embedding.provider.model_id, embedding.min_similarity, summarize(results, resolved),
    )
    return resolved


def _run_tool_layer(
    config: ToolLayerConfig,
    lines: dict[str, list[str]],
    targets: dict[str, set[str]],
    unconfirmed: list[tuple[UUID, str, str]],
    catalog: CatalogSnapshot,
    results: dict[UUID, ResolutionResult],
) -> tuple[dict[UUID, ResolutionResult], dict]:
    """MATCHING_LLM_MODE=tools: one conversation per image in menu order, then the lines in menu order.

    Each conversation turn is a request toward the import's cap (`CappedToolLLM`); a photo whose
    conversation fails, runs out of turns, hits the cap or runs past its wall-clock limits
    (`tool_config.TURN_TIMEOUT_S`, `PHOTO_TIMEOUT_S`) keeps its rule results.
    """
    llm = CappedToolLLM(config.llm, config.max_calls, make_llm=config.make_llm)
    engine = ToolEngine(llm, lines, catalog.meta)
    for image in lines:
        llm.start_photo()
        engine.translate(image, targets.get(image, set()), catalog)
    resolved = dict(results)
    for item_id, image, name in unconfirmed:
        resolved[item_id] = engine.resolve(image, name, catalog, results[item_id])
    return resolved, {"mode": "tools", "requests": llm.calls, **dict(llm.stats), "photos": dict(engine.stats)}
