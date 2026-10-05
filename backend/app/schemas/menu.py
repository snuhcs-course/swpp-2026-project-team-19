from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UtcDateTime


class MenuOptionResponse(BaseModel):
    menuEntryOptionId: UUID
    optionLabel: str | None = Field(description='Label from the menu such as "잔" or "병"; null when none')
    pourMl: int | None = Field(description="Pour size in ml; null when the menu does not state it")
    priceKrw: int
    sortOrder: int = Field(description="Options are returned in this order")


class MenuItemResponse(BaseModel):
    menuBoardEntryId: UUID
    barMenuItemId: UUID
    productId: UUID = Field(description="Canonical catalog product")
    displayName: str = Field(description="Name as written on the bar's menu, not the canonical product name")
    sortOrder: int = Field(description="Items are returned in this order")
    options: list[MenuOptionResponse] = Field(description="Price and pour-size choices")


class BarMenuResponse(BaseModel):
    barId: UUID
    name: str
    address: str
    latitude: float
    longitude: float
    phone: str | None
    menuBoardId: UUID | None = Field(description="null when the bar has no published menu")
    publishedAt: UtcDateTime | None = Field(description="When the current menu was published; null without one")
    items: list[MenuItemResponse] = Field(description="Empty when the bar has no published menu")
