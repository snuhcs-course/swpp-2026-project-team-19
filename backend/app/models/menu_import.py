"""AI menu import: uploaded photos, extraction runs and results, match candidates, and the draft diff.

Nothing here changes the published menu; only the final review applies an import.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class ImportStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    APPLIED = "applied"
    FAILED = "failed"


class ImportMode(str, Enum):
    FULL_REPLACE = "full_replace"
    PARTIAL_UPDATE = "partial_update"


class PipelineStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExtractionApproach(str, Enum):
    OCR_LLM = "ocr_llm"
    VISION_LLM = "vision_llm"


class LineType(str, Enum):
    PRODUCT = "product"
    SECTION_HEADER = "section_header"
    DESCRIPTION = "description"
    UNKNOWN = "unknown"


class ResolutionStatus(str, Enum):
    EXACT_MATCH = "exact_match"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class MatchMethod(str, Enum):
    ALIAS = "alias"
    EMBEDDING = "embedding"
    LLM = "llm"
    MANUAL = "manual"


class MenuChangeType(str, Enum):
    ADD = "add"
    UPDATE = "update"
    REMOVE = "remove"


class MenuChangeDecision(str, Enum):
    PENDING = "pending"
    APPLY = "apply"
    IGNORE = "ignore"


def _pg_enum(enum_class: type[Enum], name: str) -> SQLAlchemyEnum:
    """Store enum values (not member names), like the users and bars models."""
    return SQLAlchemyEnum(enum_class, name=name, values_callable=lambda enum: [member.value for member in enum])


def _now_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MenuImport(Base):
    """One operator submission of one or more menu photos for a bar."""

    __tablename__ = "menu_imports"
    __table_args__ = (
        Index("ix_menu_imports_bar_id_created_at", "bar_id", "created_at"),
        Index("ix_menu_imports_bar_id_status", "bar_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # SHA-256 hex of the canonical request; not unique, separate requests may repeat content.
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    bar_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bars.id"), nullable=False)
    mode: Mapped[ImportMode] = mapped_column(_pg_enum(ImportMode, "import_mode"), nullable=False)
    status: Mapped[ImportStatus] = mapped_column(
        _pg_enum(ImportStatus, "import_status"),
        nullable=False,
        default=ImportStatus.UPLOADED,
        server_default=text("'uploaded'"),
    )
    # Incremented whenever the review payload (candidates, draft diff) is regenerated.
    review_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    owner_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _now_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    images: Mapped[list["MenuImage"]] = relationship(
        back_populates="menu_import", order_by="MenuImage.image_order"
    )
    changes: Mapped[list["MenuImportChange"]] = relationship(back_populates="menu_import")


class MenuImage(Base):
    """An uploaded photo. Stores the object-storage key, never the bytes or a public URL."""

    __tablename__ = "menu_images"
    __table_args__ = (
        UniqueConstraint("menu_import_id", "image_order", name="uq_menu_images_menu_import_id_image_order"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    menu_import_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("menu_imports.id"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    uploaded_at: Mapped[datetime] = _now_column()

    menu_import: Mapped[MenuImport] = relationship(back_populates="images")
    extraction_run: Mapped["ExtractionRun | None"] = relationship(back_populates="menu_image")


class ExtractionRun(Base):
    """The single extraction run of one image; a retry reuses the same row."""

    __tablename__ = "extraction_runs"
    __table_args__ = (Index("ix_extraction_runs_pipeline_version_status", "pipeline_version", "status"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    menu_image_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("menu_images.id"), nullable=False, unique=True
    )
    approach: Mapped[ExtractionApproach] = mapped_column(
        _pg_enum(ExtractionApproach, "extraction_approach"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[PipelineStatus] = mapped_column(
        _pg_enum(PipelineStatus, "pipeline_status"),
        nullable=False,
        default=PipelineStatus.QUEUED,
        server_default=text("'queued'"),
    )
    raw_output: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _now_column()

    menu_image: Mapped[MenuImage] = relationship(back_populates="extraction_run")
    items: Mapped[list["ExtractedItem"]] = relationship(
        back_populates="extraction_run", order_by="ExtractedItem.item_order"
    )


class ExtractedItem(Base):
    """One recognized block of a menu image, product or not.

    extracted_line_type and initial_resolution_status keep the system's first judgment;
    review stores changes in corrected_line_type and the selected_* columns.
    """

    __tablename__ = "extracted_items"
    __table_args__ = (
        UniqueConstraint(
            "extraction_run_id", "item_order", name="uq_extracted_items_extraction_run_id_item_order"
        ),
        Index("ix_extracted_items_extraction_run_id_extracted_line_type", "extraction_run_id", "extracted_line_type"),
        Index("ix_extracted_items_review_status_extraction_confidence", "review_status", "extraction_confidence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extraction_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extraction_runs.id"), nullable=False
    )
    item_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_line_type: Mapped[LineType] = mapped_column(
        _pg_enum(LineType, "extracted_line_type"),
        nullable=False,
        default=LineType.UNKNOWN,
        server_default=text("'unknown'"),
    )
    corrected_line_type: Mapped[LineType | None] = mapped_column(
        _pg_enum(LineType, "extracted_line_type"), nullable=True
    )
    extracted_product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    extracted_brand_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extracted_age_years: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    extracted_edition_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    extracted_abv: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    # Null when matching was not run, e.g. for items first classified as non-products.
    initial_resolution_status: Mapped[ResolutionStatus | None] = mapped_column(
        _pg_enum(ResolutionStatus, "resolution_status"), nullable=True
    )
    selected_product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id"), nullable=True, index=True
    )
    selected_match_method: Mapped[MatchMethod | None] = mapped_column(
        _pg_enum(MatchMethod, "match_method"), nullable=True
    )
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    review_status: Mapped[ReviewStatus] = mapped_column(
        _pg_enum(ReviewStatus, "review_status"),
        nullable=False,
        default=ReviewStatus.PENDING,
        server_default=text("'pending'"),
    )
    corrected_product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    extraction_run: Mapped[ExtractionRun] = relationship(back_populates="items")
    options: Mapped[list["ExtractedOption"]] = relationship(
        back_populates="item", order_by="ExtractedOption.option_order"
    )
    candidates: Mapped[list["ResolutionCandidate"]] = relationship(
        back_populates="item", order_by="ResolutionCandidate.candidate_rank"
    )


class ExtractedOption(Base):
    """One extracted price and pour-size option of a product item."""

    __tablename__ = "extracted_options"
    __table_args__ = (
        UniqueConstraint(
            "extracted_item_id", "option_order", name="uq_extracted_options_extracted_item_id_option_order"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extracted_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extracted_items.id"), nullable=False
    )
    option_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    extracted_option_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extracted_price_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_pour_ml: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    corrected_option_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    corrected_price_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corrected_pour_ml: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    item: Mapped[ExtractedItem] = relationship(back_populates="options")


class ResolutionCandidate(Base):
    """A product candidate shown to the reviewer; at most one row per product and item."""

    __tablename__ = "resolution_candidates"
    __table_args__ = (
        UniqueConstraint(
            "extracted_item_id", "candidate_rank", name="uq_resolution_candidates_extracted_item_id_candidate_rank"
        ),
        UniqueConstraint(
            "extracted_item_id", "product_id", name="uq_resolution_candidates_extracted_item_id_product_id"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extracted_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extracted_items.id"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), nullable=False)
    candidate_rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    # The method that decided the final rank, not the list of every signal.
    method: Mapped[MatchMethod] = mapped_column(_pg_enum(MatchMethod, "match_method"), nullable=False)
    evidence: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = _now_column()

    item: Mapped[ExtractedItem] = relationship(back_populates="candidates")


class MenuImportChange(Base):
    """One row of the draft diff against the current menu board, with the reviewer's decision.

    Only the latest draft is kept. An add may have no bar_menu_item_id until publication;
    a remove has no extracted_item_id.
    """

    __tablename__ = "menu_import_changes"
    __table_args__ = (
        Index("ix_menu_import_changes_menu_import_id_change_type", "menu_import_id", "change_type"),
        Index("ix_menu_import_changes_menu_import_id_decision", "menu_import_id", "decision"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    menu_import_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("menu_imports.id"), nullable=False
    )
    change_type: Mapped[MenuChangeType] = mapped_column(
        _pg_enum(MenuChangeType, "menu_change_type"), nullable=False
    )
    bar_menu_item_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bar_menu_items.id"), nullable=True
    )
    extracted_item_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extracted_items.id"), nullable=True
    )
    decision: Mapped[MenuChangeDecision] = mapped_column(
        _pg_enum(MenuChangeDecision, "menu_change_decision"),
        nullable=False,
        default=MenuChangeDecision.PENDING,
        server_default=text("'pending'"),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    menu_import: Mapped[MenuImport] = relationship(back_populates="changes")
