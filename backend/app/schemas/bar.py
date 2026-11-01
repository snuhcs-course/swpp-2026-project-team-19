from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

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


class BarUpdateInput(BaseModel):
    """PATCH /api/bars/{barId} (spec 3.7): only the fields sent change. The field rules are those of
    `BarInput` (3.5); which fields must come together is checked by the service."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=150)
    address: str | None = Field(
        default=None, min_length=1, max_length=500, description="Send `latitude` and `longitude` with it"
    )
    latitude: float | None = Field(default=None, ge=-90, le=90, description="Sent together with `longitude`")
    longitude: float | None = Field(default=None, ge=-180, le=180, description="Sent together with `latitude`")
    phone: str | None = Field(default=None, max_length=30, description="null or blank removes the phone")
    status: Literal["active", "inactive"] | None = Field(default=None, description="Operators only")

    @field_validator("name", "address", "latitude", "longitude", "status")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # Runs only for a value that was sent: a field left out keeps its default without validation.
        if value is None:
            raise PydanticCustomError("null_not_allowed", "이 항목은 비울 수 없습니다.")
        return value

    @field_validator("phone")
    @classmethod
    def _blank_phone(cls, value: str | None) -> str | None:
        return value or None
