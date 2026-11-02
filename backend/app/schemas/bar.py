from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.schemas.bar_hours import OperatingException, WeeklyHours, WeeklyHoursInput, single_line
from app.schemas.common import Latitude, Longitude, UtcDateTime

MAX_TAGS = 5
Tag = Annotated[str, Field(min_length=1, max_length=24), AfterValidator(single_line)]


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
    menuVersion: int = Field(description="As `menuVersion` of the bar menu; send it with the sales info confirmation")
    publishedAt: UtcDateTime = Field(description="When a review publish or a manual edit last changed the menu")
    confirmedAt: UtcDateTime | None = Field(
        description="When an owner or operator last confirmed the menu is still accurate; null when never. "
        "The owner home's last update is the later of this and `publishedAt`"
    )


class BarOwnerSummary(BaseModel):
    userId: UUID
    email: str | None
    displayName: str | None
    ownerSince: UtcDateTime = Field(description="When the owner application was approved")


class BarDetail(BarListItem):
    """A bar with its management state (API spec 3.6); also the items of GET /api/me/bars (3.11.9)."""

    description: str | None = Field(description="One-line introduction, may contain line breaks; null when none")
    defaultPourMl: int | None = Field(
        description="The bar's default glass size in ml, to pre-fill glass options in the menu edit and review "
        "screens; never applied by the server. null when unset"
    )
    tags: list[str] = Field(description="Up to 5 tags in the order the bar set them; empty when none")
    weeklyHours: list[WeeklyHours] = Field(
        description="Regular hours by `dayOfWeek`; a weekday left out has no information. Empty when none"
    )
    operatingException: OperatingException | None = Field(
        description="The temporary closure, also one not started yet or one that ended yesterday; null when none"
    )
    currentMenu: CurrentMenu | None = Field(description="The published menu; null when none has been published")
    owner: BarOwnerSummary | None = Field(description="The current owner; null when none")
    createdAt: UtcDateTime
    updatedAt: UtcDateTime


class MyBarsResponse(BaseModel):
    items: list[BarDetail] = Field(description="Bars the caller currently owns, sorted by name")


class BarUpdateInput(BaseModel):
    """PATCH /api/bars/{barId} (spec 3.7): only the fields sent change. The field rules are those of
    `BarInput` (3.5) and 3.7; which fields must come together, duplicate tags and the rules of the
    weekly hours that compare fields (3.15.1) are checked by the service."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=150)
    address: str | None = Field(
        default=None, min_length=1, max_length=500, description="Send `latitude` and `longitude` with it"
    )
    latitude: float | None = Field(default=None, ge=-90, le=90, description="Sent together with `longitude`")
    longitude: float | None = Field(default=None, ge=-180, le=180, description="Sent together with `latitude`")
    phone: str | None = Field(default=None, max_length=30, description="null or blank removes the phone")
    description: str | None = Field(
        default=None, max_length=100, description="Line breaks allowed; null or blank removes it"
    )
    defaultPourMl: int | None = Field(default=None, ge=1, le=999, description="null removes it")
    tags: list[Tag] | None = Field(
        default=None,
        max_length=MAX_TAGS,
        description="Replaces all tags, in display order. Each 1-24 characters, one line, unique ignoring case; "
        "`[]` removes them",
    )
    weeklyHours: list[WeeklyHoursInput] | None = Field(
        default=None, description="Replaces all regular hours (spec 3.15.1); `[]` removes them"
    )
    status: Literal["active", "inactive"] | None = Field(default=None, description="Operators only")

    @field_validator("name", "address", "latitude", "longitude", "tags", "weeklyHours", "status")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # Runs only for a value that was sent: a field left out keeps its default without validation.
        if value is None:
            raise PydanticCustomError("null_not_allowed", "이 항목은 비울 수 없습니다.")
        return value

    @field_validator("phone", "description")
    @classmethod
    def _blank_to_null(cls, value: str | None) -> str | None:
        return value or None
