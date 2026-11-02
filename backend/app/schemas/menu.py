from uuid import UUID

from pydantic import BaseModel, Field

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
    options: list[MenuOptionResponse] = Field(description="Price and pour-size choices")


class BarMenuResponse(BaseModel):
    barId: UUID
    name: str
    address: str
    latitude: Latitude
    longitude: Longitude
    phone: str | None
    menuBoardId: UUID | None = Field(description="null when the bar has no published menu")
    menuVersion: int | None = Field(
        description="Raised by every review publish and manual edit; send it with a manual edit. null without a menu"
    )
    publishedAt: UtcDateTime | None = Field(
        description="When a review publish or a manual edit last changed the menu; null without one"
    )
    items: list[MenuItemResponse] = Field(description="Empty when the bar has no published menu")
