"""Background processing of a menu import after the upload request has returned.

For each image in order: extract → store items and options (committed per image so
polling shows progress). Then match every product item, store candidates, build the draft
diff, and move the import to ready_for_review. The first failed image fails the import and
the remaining images are not extracted, since the import cannot be reviewed anyway.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.adapters.extraction import ExtractedItemData, ExtractionError, MenuExtractor
from app.adapters.storage import ImageStorage
from app.matching import ExtractedProduct, resolve_product
from app.matching.db_catalog import DbCatalog
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
) -> None:
    """Called after the import rows are committed, so the job never sees uncommitted rows."""
    menu_import.status = ImportStatus.PROCESSING
    session.commit()
    background_tasks.add_task(process_menu_import, session_factory, storage, extractor, menu_import.id)


def process_menu_import(
    session_factory: SessionFactory, storage: ImageStorage, extractor: MenuExtractor, import_id: UUID
) -> None:
    with session_factory() as session:
        menu_import = session.get(MenuImport, import_id)
        if menu_import is None or menu_import.status != ImportStatus.PROCESSING:
            return
        try:
            if _extract_all(session, storage, extractor, menu_import):
                _resolve_and_draft(session, menu_import)
                menu_import.status = ImportStatus.READY_FOR_REVIEW
            else:
                menu_import.status = ImportStatus.FAILED
                menu_import.completed_at = _now()
            session.commit()
        except Exception:
            # A bug must not leave the import in processing forever.
            logger.exception("Menu import %s failed during processing", import_id)
            session.rollback()
            menu_import = session.get(MenuImport, import_id)
            if menu_import is not None:
                menu_import.status = ImportStatus.FAILED
                menu_import.completed_at = _now()
                session.commit()


def _extract_all(session: Session, storage: ImageStorage, extractor: MenuExtractor, menu_import: MenuImport) -> bool:
    """Extract queued images in order. Returns False at the first failed image."""
    for image in menu_import.images:
        run = image.extraction_run
        if run.status != PipelineStatus.QUEUED:
            continue
        # Read before the commit: after it, attribute access would open a new transaction and
        # hold it for the whole extraction call, which can take minutes with a real model.
        storage_key, filename = image.storage_key, image.original_filename
        run.status = PipelineStatus.RUNNING
        run.started_at = _now()
        session.commit()
        try:
            data = storage.read(storage_key)
            detected = detect_image_type(data)
            result = extractor.extract(data, detected[1] if detected else "application/octet-stream", filename)
        except (ExtractionError, OSError) as error:
            run.status = PipelineStatus.FAILED
            run.raw_output = {"error": type(error).__name__, "message": str(error)}
            if isinstance(error, ExtractionError) and error.raw_output is not None:
                run.raw_output["output"] = error.raw_output
            run.completed_at = _now()
            session.commit()
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


def _resolve_and_draft(session: Session, menu_import: MenuImport) -> None:
    catalog = DbCatalog(session)
    for item in product_items(session, menu_import):
        result = resolve_product(
            ExtractedProduct(
                product_name=item.extracted_product_name,
                brand_name=item.extracted_brand_name,
                age_years=item.extracted_age_years,
                edition_name=item.extracted_edition_name,
                abv=item.extracted_abv,
            ),
            catalog,
        )
        item.initial_resolution_status = ResolutionStatus(result.status)
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
