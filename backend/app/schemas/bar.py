from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Latitude, Longitude, UtcDateTime


class ActiveMenuImport(BaseModel):
    menuImportId: UUID
    status: Literal["uploaded", "processing", "ready_for_review"]


class BarListItem(BaseModel):
    barId: UUID
    name: str
    address: str
    latitude: Latitude
    longitude: Longitude
    phone: str | None
    status: Literal["active", "inactive"]
    activeMenuImport: ActiveMenuImport | None = Field(
        description="The bar's unfinished import, to continue it without another request; null when none"
    )


class BarListResponse(BaseModel):
    items: list[BarListItem] = Field(description="Sorted by name")
    nextCursor: str | None = Field(description="Pass as `cursor` for the next page; null on the last page")


class CurrentMenu(BaseModel):
    menuBoardId: UUID
    publishedAt: UtcDateTime = Field(description="When the current menu was last published")


class BarOwnerSummary(BaseModel):
    userId: UUID
    email: str | None
    displayName: str | None
    ownerSince: UtcDateTime = Field(description="When the owner application was approved")


class BarDetail(BarListItem):
    """A bar with its management state (API spec 3.6); also the items of GET /api/me/bars (3.11.9)."""

    currentMenu: CurrentMenu | None = Field(description="The published menu; null when none has been published")
    owner: BarOwnerSummary | None = Field(description="The current owner; null when none")
    createdAt: UtcDateTime
    updatedAt: UtcDateTime


class MyBarsResponse(BaseModel):
    items: list[BarDetail] = Field(description="Bars the caller currently owns, sorted by name")
