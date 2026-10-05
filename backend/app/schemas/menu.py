from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import UtcDateTime


class MenuOptionResponse(BaseModel):
    menuEntryOptionId: UUID
    optionLabel: str | None
    pourMl: int | None
    priceKrw: int
    sortOrder: int


class MenuItemResponse(BaseModel):
    menuBoardEntryId: UUID
    barMenuItemId: UUID
    productId: UUID
    # As written on the bar's menu (menu_board_entries.display_name).
    displayName: str
    sortOrder: int
    options: list[MenuOptionResponse]


class BarMenuResponse(BaseModel):
    barId: UUID
    name: str
    address: str
    latitude: float
    longitude: float
    phone: str | None
    menuBoardId: UUID | None
    publishedAt: UtcDateTime | None
    items: list[MenuItemResponse]
