"""Request body of POST /api/menu-imports/{menuImportId}/review-and-apply (API spec, section 8).

Each item decision is one of four shapes picked by `action`, and a new product's brand is
one of two shapes picked by `brand.type`. Fields another shape uses are rejected
(`EXTRA_FORBIDDEN`), e.g. options on a `confirm_non_product` decision.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import register_union_tags
from app.models import LineType
from app.schemas.common import UtcDateTime

MAX_PRICE_KRW = 2**31 - 1
MAX_POUR_ML = 32767

NonProductLineType = Literal["section_header", "description", "unknown"]


class _Strict(BaseModel):
    # Names are stored as sent, so surrounding spaces are dropped; a blank name then fails min_length.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProductAliasInput(_Strict):
    aliasText: str = Field(min_length=1, max_length=200, description="As written; normalized by the backend")
    languageCode: str | None = Field(default=None, max_length=10, description='e.g. "ko", "en"')
    isSearchable: bool = Field(default=True, description="Whether customer search uses this alias")


class BrandAliasInput(_Strict):
    aliasText: str = Field(min_length=1, max_length=120, description="As written; normalized by the backend")
    languageCode: str | None = Field(default=None, max_length=10)


class OptionDecision(_Strict):
    """Corrections to one extracted option. A null or missing field keeps the extracted value."""

    extractedOptionId: UUID
    correctedOptionLabel: str | None = Field(default=None, min_length=1, max_length=100)
    correctedPriceKrw: int | None = Field(default=None, gt=0, le=MAX_PRICE_KRW)
    correctedPourMl: int | None = Field(default=None, ge=1, le=MAX_POUR_ML)


class ExistingBrand(_Strict):
    type: Literal["existing"]
    brandId: UUID


class NewBrand(_Strict):
    type: Literal["new"]
    canonicalName: str = Field(min_length=1, max_length=120)
    aliases: list[BrandAliasInput] = Field(default_factory=list, description="The canonical name is added as an alias too")


BrandDecision = Annotated[ExistingBrand | NewBrand, Field(discriminator="type")]


class NewProduct(_Strict):
    category: str = Field(default="whisky", min_length=1, max_length=30)
    displayName: str = Field(min_length=1, max_length=200, description="Canonical name; also added as an alias")
    ageYears: int | None = Field(default=None, ge=0, le=200)
    editionName: str | None = Field(default=None, min_length=1, max_length=150)
    abv: float | None = Field(default=None, gt=0, le=100)


class _ProductDecision(_Strict):
    extractedItemId: UUID
    finalLineType: Literal["product"]
    correctedProductName: str | None = Field(
        default=None, min_length=1, max_length=200, description="The line's name as it should appear on the menu"
    )
    optionDecisions: list[OptionDecision] = Field(default_factory=list, description="Only options being corrected")


class SelectExistingProduct(_ProductDecision):
    action: Literal["select_existing_product"]
    productId: UUID
    aliasesToAdd: list[ProductAliasInput] = Field(
        default_factory=list, description="Only for a confirmed real spelling, not for OCR errors"
    )


class CreateProduct(_ProductDecision):
    action: Literal["create_product"]
    brand: BrandDecision
    product: NewProduct
    aliases: list[ProductAliasInput] = Field(default_factory=list)


class ConfirmNonProduct(_Strict):
    action: Literal["confirm_non_product"]
    extractedItemId: UUID
    finalLineType: NonProductLineType


class Reject(_Strict):
    action: Literal["reject"]
    extractedItemId: UUID
    finalLineType: LineType = Field(description="Any line type; stored as the corrected type when it differs")


ItemDecision = Annotated[
    SelectExistingProduct | CreateProduct | ConfirmNonProduct | Reject, Field(discriminator="action")
]
ProductDecision = SelectExistingProduct | CreateProduct


class ChangeDecision(_Strict):
    changeId: UUID
    decision: Literal["apply", "ignore"]


class ReviewAndApplyRequest(_Strict):
    reviewVersion: int = Field(ge=1, description="`reviewVersion` of the review data the decisions were made on")
    itemDecisions: list[ItemDecision] = Field(description="Exactly one decision for every extracted item")
    changeDecisions: list[ChangeDecision] = Field(description="Exactly one decision for every proposed change")


register_union_tags("select_existing_product", "create_product", "confirm_non_product", "reject", "existing", "new")


# ---- Response ----


class ReviewResult(BaseModel):
    added: int = Field(description="Products added to the board")
    updated: int = Field(description="Board products whose options changed")
    removed: int = Field(description="Products removed from the board")
    ignored: int = Field(description="Proposed changes the reviewer ignored")
    createdBrands: int
    createdProducts: int


class ReviewAppliedResponse(BaseModel):
    menuImportId: UUID
    status: Literal["applied"]
    reviewVersion: int
    appliedAt: UtcDateTime
    menuBoardId: UUID
    result: ReviewResult
