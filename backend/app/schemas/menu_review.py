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
from app.models.menu import MenuItemKind
from app.schemas.common import UtcDateTime

# The same limits as a manual edit (spec 3.14.2).
MAX_PRICE_KRW = 99_999_999
MAX_POUR_ML = 32767
MAX_REVIEW_OPTIONS = 10

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


class ReviewOption(_Strict):
    """One option of a line's final option list (spec 8.1): the values to publish, not corrections."""

    extractedOptionId: UUID | None = Field(
        default=None, description="The extracted option it comes from; null for one the reviewer added"
    )
    optionLabel: str | None = Field(default=None, min_length=1, max_length=100, description="null for none")
    pourMl: int | None = Field(default=None, ge=1, le=MAX_POUR_ML, description="null for none; stored as sent")
    priceKrw: int = Field(ge=1, le=MAX_PRICE_KRW)


class ExistingBrand(_Strict):
    type: Literal["existing"]
    brandId: UUID


class NewBrand(_Strict):
    type: Literal["new"]
    canonicalName: str = Field(min_length=1, max_length=120)
    aliases: list[BrandAliasInput] = Field(default_factory=list, description="The canonical name is added as an alias too")


BrandDecision = Annotated[ExistingBrand | NewBrand, Field(discriminator="type")]


class NewProduct(_Strict):
    # The shared catalog holds whiskies only (spec 8.1); a non-whisky menu is published without a product.
    category: Literal["whisky"] = Field(default="whisky", description="Only whisky")
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
    options: list[ReviewOption] = Field(
        min_length=1,
        max_length=MAX_REVIEW_OPTIONS,
        description="The line's final options in display order. Extracted options left out are not published",
    )


class SelectExistingProduct(_ProductDecision):
    action: Literal["select_existing_product"]
    productId: UUID
    aliasesToAdd: list[ProductAliasInput] = Field(
        default_factory=list,
        description="Only for a confirmed real spelling, not for OCR errors. Operators only (OPERATOR_ONLY)",
    )


class CreateProduct(_ProductDecision):
    action: Literal["create_product"]
    brand: BrandDecision
    product: NewProduct
    aliases: list[ProductAliasInput] = Field(default_factory=list)


class PublishWithoutProduct(_ProductDecision):
    """Publish the line on this bar's menu only, without a catalog product (spec 8.10)."""

    action: Literal["publish_without_product"]
    kind: MenuItemKind = Field(description="whisky waits for an operator to link it; other is a non-whisky menu")


class ConfirmNonProduct(_Strict):
    action: Literal["confirm_non_product"]
    extractedItemId: UUID
    finalLineType: NonProductLineType


class Reject(_Strict):
    action: Literal["reject"]
    extractedItemId: UUID
    finalLineType: LineType = Field(description="Any line type; stored as the corrected type when it differs")


ItemDecision = Annotated[
    SelectExistingProduct | CreateProduct | PublishWithoutProduct | ConfirmNonProduct | Reject,
    Field(discriminator="action"),
]
# Decisions that publish the line as a menu item.
ProductDecision = SelectExistingProduct | CreateProduct | PublishWithoutProduct


class ChangeDecision(_Strict):
    changeId: UUID
    decision: Literal["apply", "ignore"]


class ReviewAndApplyRequest(_Strict):
    reviewVersion: int = Field(ge=1, description="`reviewVersion` of the review data the decisions were made on")
    itemDecisions: list[ItemDecision] = Field(description="Exactly one decision for every extracted item")
    changeDecisions: list[ChangeDecision] = Field(description="Exactly one decision for every proposed change")


register_union_tags(
    "select_existing_product",
    "create_product",
    "publish_without_product",
    "confirm_non_product",
    "reject",
    "existing",
    "new",
)


# ---- Response ----


class ReviewResult(BaseModel):
    added: int = Field(description="Items added to the board")
    updated: int = Field(description="Board items whose options or link changed")
    removed: int = Field(description="Items removed from the board")
    ignored: int = Field(description="Proposed changes the reviewer ignored")
    createdBrands: int
    createdProducts: int
    unlinkedWhisky: int = Field(
        description="Whisky items without a product this review added or changed (spec 8.8); they appear in "
        "search once an operator links them"
    )


class ReviewAppliedResponse(BaseModel):
    menuImportId: UUID
    status: Literal["applied"]
    reviewVersion: int
    appliedAt: UtcDateTime
    menuBoardId: UUID
    result: ReviewResult
