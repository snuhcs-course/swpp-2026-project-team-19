from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.bar import BarPhotoResponse
from app.schemas.bar_hours import OperatingException, WeeklyHours
from app.schemas.common import Latitude, Longitude, UtcDateTime


class DiscountResponse(BaseModel):
    """A time-limited discount that has not ended. The app decides whether it is running from the
    device clock: the discounted price applies while `startsAt <= now < endsAt`."""

    discountedPriceKrw: int = Field(description="Discounted price in KRW; lower than `priceKrw`")
    startsAt: UtcDateTime = Field(description="When the discount starts; may be in the future")
    endsAt: UtcDateTime = Field(description="When the list price applies again")


class MenuOptionResponse(BaseModel):
    menuEntryOptionId: UUID
    optionLabel: str | None = Field(description='Label from the menu such as "잔" or "병"; null when none')
    pourMl: int | None = Field(description="Pour size in ml; null when the menu does not state it")
    priceKrw: int = Field(description="List price, also while a discount is running")
    discount: DiscountResponse | None = Field(description="null when there is no discount or it has ended")
    sortOrder: int = Field(description="Options are returned in this order")


class MenuItemResponse(BaseModel):
    menuBoardEntryId: UUID
    barMenuItemId: UUID = Field(description="Stable id of the item; manual edits address items by it")
    productId: UUID = Field(description="Canonical catalog product")
    productName: str = Field(description="Canonical product name (products.display_name)")
    brandId: UUID
    brandName: str = Field(description="The brand's canonical name")
    category: str = Field(description='Product category, e.g. "whisky"')
    displayName: str = Field(description="Name as written on the bar's menu, not the canonical product name")
    sortOrder: int = Field(description="Items are returned in this order")
    soldOut: bool = Field(
        description="Sold out (spec 3.14.8). Only operators and the bar's owner get sold-out items, in place; "
        "everyone else gets them left out, so for them this is always false"
    )
    options: list[MenuOptionResponse] = Field(description="Price and pour-size choices")


class BarMenuResponse(BaseModel):
    barId: UUID
    name: str
    address: str
    latitude: Latitude
    longitude: Longitude
    phone: str | None
    description: str | None = Field(
        description="One-line introduction; may contain line breaks. Show it as plain text, not HTML. null when none"
    )
    tags: list[str] = Field(description="Up to 5 tags; show them in this order. Empty when none")
    weeklyHours: list[WeeklyHours] = Field(
        description="Regular hours by `dayOfWeek`; a weekday left out has no information. Empty when none"
    )
    operatingException: OperatingException | None = Field(
        description="The temporary closure, also one not started yet or one that ended yesterday (for the status "
        "early that morning); null when none. The open status is computed by the app (spec 3.15.5)"
    )
    photos: list[BarPhotoResponse] = Field(
        description="Bar photos in display order; the first is the cover. Empty when none: show the default image"
    )
    menuBoardId: UUID | None = Field(description="null when the bar has no published menu")
    menuVersion: int | None = Field(
        description="Raised by every review publish and manual edit; send it with a manual edit. null without a menu"
    )
    publishedAt: UtcDateTime | None = Field(
        description="When a review publish or a manual edit last changed the menu; null without one"
    )
    items: list[MenuItemResponse] = Field(description="Empty when the bar has no published menu")
