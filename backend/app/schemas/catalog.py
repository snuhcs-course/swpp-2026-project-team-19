# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #12). Reviewed by Haeul Yang.
from uuid import UUID

from pydantic import BaseModel, Field


class CatalogBrandItem(BaseModel):
    brandId: UUID
    canonicalName: str
    matchedAlias: str = Field(description="The brand alias that matched the query, as written")


class CatalogBrandsResponse(BaseModel):
    items: list[CatalogBrandItem] = Field(
        description="Exact alias matches first, then closest partial matches. Several brands can share an "
        "alias; all of them are returned and none is chosen automatically."
    )


class CatalogProductItem(BaseModel):
    productId: UUID
    displayName: str = Field(description="Canonical product name")
    brandId: UUID
    brandName: str
    category: str
    ageYears: int | None
    editionName: str | None
    abv: float | None
    isActive: bool = Field(description="Inactive products are listed so the reviewer does not create a duplicate")
    matchedAlias: str = Field(description="The product alias that matched the query, as written")


class CatalogProductsResponse(BaseModel):
    items: list[CatalogProductItem] = Field(description="Exact alias matches first, then closest partial matches")
