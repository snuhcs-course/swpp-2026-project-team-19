from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import ImportMode, ImportStatus, LineType, MatchMethod, MenuChangeDecision, MenuChangeType, ResolutionStatus
from app.schemas.common import UtcDateTime


class MenuImportAcceptedResponse(BaseModel):
    menuImportId: UUID
    status: ImportStatus = Field(description="Current status; a retried request returns the existing import's status")
    imageCount: int
    statusUrl: str = Field(description="Poll this with GET for progress and, when ready, the review data")
    pollAfterMs: int = Field(description="Suggested polling interval")


# --- GET /api/menu-imports/{menuImportId}: the body depends on the status ---


class ImportProgress(BaseModel):
    totalImages: int
    completedImages: int = Field(description="Images whose extraction succeeded. For progress display only")
    failedImages: int


class ImportProcessingResponse(BaseModel):
    menuImportId: UUID
    status: Literal["uploaded", "processing"]
    progress: ImportProgress
    pollAfterMs: int = Field(description="Wait this long before polling again")


class ImportFailure(BaseModel):
    code: Literal["IMAGE_EXTRACTION_FAILED", "PROCESSING_FAILED"]
    message: str


class ImportFailedResponse(BaseModel):
    menuImportId: UUID
    status: Literal["failed"]
    progress: ImportProgress
    failure: ImportFailure = Field(description="Start a new upload; a failed import is not resumed")


class ReviewOption(BaseModel):
    extractedOptionId: UUID
    optionOrder: int
    extractedOptionLabel: str | None
    extractedPourMl: int | None
    extractedPriceKrw: int | None


class ReviewCandidate(BaseModel):
    productId: UUID
    candidateRank: int = Field(description="Candidates are sorted by this; rank 1 is proposedProductId")
    displayName: str
    brandId: UUID
    brandName: str
    category: str
    ageYears: int | None
    editionName: str | None
    abv: float | None
    matchMethod: MatchMethod
    score: float | None
    evidence: dict[str, Any] = Field(description="Explanatory signals; ignore unknown keys")


class NewProductDraft(BaseModel):
    """Prefill for creating a product from this item. Not a catalog row."""

    brandText: str | None
    category: str
    displayName: str | None
    ageYears: int | None
    editionName: str | None
    abv: float | None


class ReviewItem(BaseModel):
    extractedItemId: UUID
    itemOrder: int
    rawText: str = Field(description="The text block the item was read from")
    extractedLineType: LineType = Field(description="The AI's first classification; never changed by review")
    correctedLineType: LineType | None = Field(description="Set only when review changed the classification")
    effectiveLineType: LineType = Field(description="correctedLineType ?? extractedLineType; use for display")
    initialResolutionStatus: ResolutionStatus | None = Field(
        description="First matching result; null for items first classified as non-products"
    )
    extractedProductName: str | None
    extractedBrandName: str | None
    extractedAgeYears: int | None
    extractedEditionName: str | None
    extractedAbv: float | None
    extractionConfidence: float | None
    proposedProductId: UUID | None = Field(description="Rank-1 candidate, a suggestion only; null without candidates")
    options: list[ReviewOption]
    candidates: list[ReviewCandidate]
    newProductDraft: NewProductDraft | None = Field(description="Null for non-product items")


class ReviewImage(BaseModel):
    imageId: UUID
    imageOrder: int
    imageUrl: str
    imageUrlExpiresAt: UtcDateTime | None = Field(description="Null when the URL does not expire (local storage)")
    items: list[ReviewItem]


class ChangeBeforeOption(BaseModel):
    menuEntryOptionId: UUID
    optionLabel: str | None
    pourMl: int | None
    priceKrw: int


class ChangeAfterOption(BaseModel):
    extractedOptionId: UUID
    optionLabel: str | None
    pourMl: int | None
    priceKrw: int | None


class ChangeBefore(BaseModel):
    productId: UUID
    displayName: str = Field(description="Canonical product name")
    options: list[ChangeBeforeOption]


class ChangeAfter(BaseModel):
    productId: UUID | None = Field(description="Proposed product; null when the item matched no product")
    displayName: str | None = Field(description="Canonical product name, or the extracted name when unmatched")
    options: list[ChangeAfterOption]


class ProposedChange(BaseModel):
    changeId: UUID
    changeType: MenuChangeType
    barMenuItemId: UUID | None
    extractedItemId: UUID | None
    before: ChangeBefore | None = Field(description="Published values; null for add")
    after: ChangeAfter | None = Field(description="Proposed values; null for remove")
    summary: str = Field(description="Display text only; never used for validation")
    decision: MenuChangeDecision


class ImportReviewResponse(BaseModel):
    menuImportId: UUID
    barId: UUID
    mode: ImportMode
    status: Literal["ready_for_review"]
    reviewVersion: int = Field(description="Send this back with the review; a newer version rejects older submissions")
    images: list[ReviewImage]
    proposedChanges: list[ProposedChange] = Field(
        description="add/update in menu order, then remove in current board order"
    )


class ImportAppliedResponse(BaseModel):
    menuImportId: UUID
    barId: UUID
    status: Literal["applied"]
    reviewVersion: int
    appliedAt: UtcDateTime | None
    menuBoardId: UUID | None


MenuImportStatusResponse = ImportProcessingResponse | ImportFailedResponse | ImportReviewResponse | ImportAppliedResponse


class MenuImportListItem(BaseModel):
    menuImportId: UUID
    mode: ImportMode
    status: ImportStatus
    imageCount: int
    reviewVersion: int = Field(description="0 until the first review data is ready")
    ownerNote: str | None
    createdAt: UtcDateTime
    completedAt: UtcDateTime | None = Field(description="When it was applied or failed; null while unfinished")


class MenuImportListResponse(BaseModel):
    items: list[MenuImportListItem] = Field(description="Newest first")
    nextCursor: str | None = Field(description="Pass as `cursor` for the next page; null on the last page")
