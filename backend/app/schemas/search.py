from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.bar import COVER_THUMBNAIL_DESCRIPTION
from app.schemas.common import Latitude, Longitude, UtcDateTime
from app.schemas.menu import DiscountResponse


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
    priceKrw: int = Field(description="List price, also while a discount is running")
    discount: DiscountResponse | None = Field(
        description="The same as on the bar menu; null when there is no discount or it has ended"
    )
    sortOrder: int = Field(description="Options are returned in this order")


class SearchResultItem(BaseModel):
    barId: UUID
    barName: str
    address: str
    latitude: Latitude
    longitude: Longitude
    coverThumbnailUrl: str | None = Field(description=COVER_THUMBNAIL_DESCRIPTION)
    distanceMeters: int | None = Field(
        description="Straight-line distance from lat/lng in whole meters; null when no location was sent"
    )
    productId: UUID
    productDisplayName: str = Field(description="Canonical product name (products.display_name)")
    menuDisplayName: str = Field(description="Name as written on this bar's menu")
    options: list[SearchOptionResponse] = Field(description="All price and pour-size choices for this item")
    menuUpdatedAt: UtcDateTime = Field(description="When this bar's current menu was published")


class SearchBarsResponse(BaseModel):
    query: str | None = Field(description="The query after trimming; null for a productId search")
    matchType: Literal["alias_exact", "brand", "partial", "product", "none"] = Field(
        description="The resolution step that produced the products; `product` for a productId search "
        "that found its product"
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


class BarNameItem(BaseModel):
    barId: UUID
    name: str
    address: str
    latitude: Latitude
    longitude: Longitude
    coverThumbnailUrl: str | None = Field(description=COVER_THUMBNAIL_DESCRIPTION)
    hasOwner: bool = Field(
        description="True when the bar has a current owner; an owner application for it would be "
        "`409 BAR_OWNER_EXISTS`"
    )


class BarNamesResponse(BaseModel):
    items: list[BarNameItem] = Field(description="Active bars whose name or address contains the query, by name")
    truncated: bool = Field(description="True when more bars matched than `limit`")


class MapBarItem(BaseModel):
    barId: UUID
    name: str
    address: str
    latitude: Latitude
    longitude: Longitude
    coverThumbnailUrl: str | None = Field(description=COVER_THUMBNAIL_DESCRIPTION)
    menuUpdatedAt: UtcDateTime | None = Field(
        description="When this bar's current menu was published, as in GET /api/search/nearby-bars; "
        "null when the bar has never had a published menu, set even when that menu has no items"
    )


class MapBarsResponse(BaseModel):
    items: list[MapBarItem] = Field(
        description="Every active bar inside the area, edges included, by barId. Never truncated."
    )


class NearbyBarItem(BaseModel):
    barId: UUID
    name: str
    address: str
    latitude: Latitude
    longitude: Longitude
    coverThumbnailUrl: str | None = Field(description=COVER_THUMBNAIL_DESCRIPTION)
    distanceMeters: int = Field(
        description="Straight-line (haversine) distance from lat/lng in whole meters; at most `radiusMeters`"
    )
    menuUpdatedAt: UtcDateTime | None = Field(
        description="When this bar's current menu was published (`publishedAt` of GET /api/bars/{barId}/menu); "
        "null when the bar has never had a published menu, set even when that menu has no items"
    )


class NearbyBarsResponse(BaseModel):
    items: list[NearbyBarItem] = Field(
        description="Every active bar within the radius, nearest first; ties by barId. Never truncated."
    )


class PopularProductItem(BaseModel):
    productId: UUID = Field(description="Search it with `GET /api/search/bars?productId=...&source=popular`")
    displayName: str = Field(description="Canonical product name, shown on the card")
    brandName: str
    ageYears: int | None
    editionName: str | None
    barCount: int = Field(
        description="Active bars selling it now, not sold out; the number of bars its productId search "
        "shows. At least 1."
    )


class PopularProductsResponse(BaseModel):
    items: list[PopularProductItem] = Field(
        description="Ranked products, at most `limit`; empty when no bar sells any product"
    )
