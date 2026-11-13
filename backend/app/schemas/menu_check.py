"""Operator menu item checks (API spec 3.18): the list response and the resolve request."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import register_union_tags
from app.models.menu import MenuItemKind
from app.models.menu_check import CheckReason, CheckResolution, CheckStatus
from app.schemas.common import UtcDateTime
from app.schemas.menu_import import SourceBox
from app.schemas.menu_review import BrandDecision, NewProduct, ProductAliasInput

# ---- response ----


class CheckSource(BaseModel):
    """The review line that raised a reason (spec 3.18.2)."""

    menuImportId: UUID
    extractedItemId: UUID
    rawText: str
    sourceBox: SourceBox | None = Field(description="Where the line is on the photo, as in the review data (5.4)")
    imageUrl: str = Field(description="The menu photo of the line; a signed URL, as in the review data (5.4)")
    imageUrlExpiresAt: UtcDateTime | None = Field(description="Null when the URL does not expire (local storage)")
    extractedProductName: str | None
    extractedBrandName: str | None
    extractedAgeYears: int | None
    extractedEditionName: str | None


class CheckReasonResponse(BaseModel):
    reason: CheckReason
    addedAt: UtcDateTime
    source: CheckSource | None = Field(description="Null for a reason raised by a manual add or edit")


class DiscardedOption(BaseModel):
    optionLabel: str | None
    pourMl: int | None
    priceKrw: int
    displayName: str = Field(description="Menu name of the line the option was on")
    extractedItemId: UUID | None = Field(description="The review line it came from; null from a manual edit")


class CheckBar(BaseModel):
    barId: UUID
    name: str
    status: Literal["active", "inactive"]


class CheckProduct(BaseModel):
    productId: UUID
    displayName: str
    brandId: UUID
    brandName: str
    category: str
    ageYears: int | None
    editionName: str | None


class CheckItemOption(BaseModel):
    optionLabel: str | None
    pourMl: int | None
    priceKrw: int


class CheckItem(BaseModel):
    barMenuItemId: UUID
    kind: MenuItemKind
    displayName: str = Field(description="Name on the board; the last one shown when the item left it")
    onBoard: bool
    soldOut: bool
    product: CheckProduct | None = Field(description="The product it is linked to now; null when unlinked")
    options: list[CheckItemOption] = Field(description="Options on the board now; empty when not on the board")


class MenuItemCheckResponse(BaseModel):
    checkId: UUID
    status: CheckStatus
    reasons: list[CheckReasonResponse] = Field(description="In the order they were added; at least one")
    createdAt: UtcDateTime
    resolvedAt: UtcDateTime | None
    resolution: CheckResolution | None
    resolvedProductId: UUID | None
    discardedOptions: list[DiscardedOption] = Field(description="Prices the server dropped while merging lines")
    bar: CheckBar
    item: CheckItem


class MenuItemCheckPage(BaseModel):
    items: list[MenuItemCheckResponse]
    nextCursor: str | None = Field(description="Pass as `cursor` for the next page; null on the last page")


# ---- request ----


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LinkExisting(_Strict):
    resolution: Literal["link_existing"]
    productId: UUID
    aliasesToAdd: list[ProductAliasInput] = Field(
        default_factory=list, description="Spellings of the menu to add to the product, e.g. the board's name"
    )


class CreateAndLink(_Strict):
    resolution: Literal["create_and_link"]
    brand: BrandDecision
    product: NewProduct
    aliases: list[ProductAliasInput] = Field(default_factory=list)


class Keep(_Strict):
    resolution: Literal["keep"]


class MarkAsOther(_Strict):
    resolution: Literal["mark_as_other"]


ResolveRequest = Annotated[LinkExisting | CreateAndLink | Keep | MarkAsOther, Field(discriminator="resolution")]

register_union_tags("link_existing", "create_and_link", "keep", "mark_as_other")
