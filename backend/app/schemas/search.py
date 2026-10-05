from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import UtcDateTime


class MatchedProductResponse(BaseModel):
    productId: UUID
    displayName: str
    brandName: str
    ageYears: int | None
    editionName: str | None
    # Result rows for this product before `limit` is applied; 0 when no bar sells it now.
    resultCount: int


class SearchOptionResponse(BaseModel):
    optionLabel: str | None
    pourMl: int | None
    priceKrw: int
    sortOrder: int


class SearchResultItem(BaseModel):
    barId: UUID
    barName: str
    address: str
    latitude: float
    longitude: float
    # Straight-line distance from the customer; null without lat/lng.
    distanceMeters: int | None
    productId: UUID
    productDisplayName: str
    menuDisplayName: str
    options: list[SearchOptionResponse]
    menuUpdatedAt: UtcDateTime


class SearchBarsResponse(BaseModel):
    query: str
    matchType: Literal["alias_exact", "brand", "partial", "none"]
    matchedProducts: list[MatchedProductResponse]
    items: list[SearchResultItem]
    truncated: bool
