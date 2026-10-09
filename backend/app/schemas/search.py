# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9). Reviewed by Haeul Yang.
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UtcDateTime


class MatchedProductResponse(BaseModel):
    productId: UUID
    displayName: str = Field(description="Canonical product name")
    brandName: str
    ageYears: int | None
    editionName: str | None
    resultCount: int = Field(
        description="Result rows for this product before `limit` is applied; 0 when no bar sells it now"
    )


class SearchOptionResponse(BaseModel):
    optionLabel: str | None = Field(description='Label from the menu such as "잔" or "병"; null when none')
    pourMl: int | None = Field(description="Pour size in ml; null when the menu does not state it")
    priceKrw: int
    sortOrder: int = Field(description="Options are returned in this order")


class SearchResultItem(BaseModel):
    barId: UUID
    barName: str
    address: str
    latitude: float
    longitude: float
    distanceMeters: int | None = Field(
        description="Straight-line distance from lat/lng in whole meters; null when no location was sent"
    )
    productId: UUID
    productDisplayName: str = Field(description="Canonical product name (products.display_name)")
    menuDisplayName: str = Field(description="Name as written on this bar's menu")
    options: list[SearchOptionResponse] = Field(description="All price and pour-size choices for this item")
    menuUpdatedAt: UtcDateTime = Field(description="When this bar's current menu was published")


class SearchBarsResponse(BaseModel):
    query: str = Field(description="The query after trimming")
    matchType: Literal["alias_exact", "brand", "partial", "none"] = Field(
        description="The resolution step that produced the products"
    )
    matchedProducts: list[MatchedProductResponse] = Field(
        description="Every product the query resolved to, including ones no bar sells now. "
        "Empty means the name was not recognized."
    )
    items: list[SearchResultItem] = Field(
        description="One row per bar x product. Empty with non-empty matchedProducts means the product "
        "was recognized but no active bar currently sells it."
    )
    truncated: bool = Field(description="True when more rows matched than `limit`")
