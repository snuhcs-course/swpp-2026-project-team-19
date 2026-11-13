"""Request bodies of the manual menu edit APIs (API spec 3.14.2 to 3.14.6), the sold-out mark (3.14.8) and
the sales info confirmation (3.14.9).

The shapes, lengths and ranges are checked here. The rules that compare fields (duplicate
options, discounts, exactly one of productId and newProduct, names that normalize to nothing)
are checked by app.services.menu_edit.check_request, still before the bar is looked up.
"""

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool

from app.schemas.menu_review import BrandDecision, NewProduct, ProductAliasInput

MAX_MENU_PRICE_KRW = 99_999_999
MAX_POUR_ML = 32767
MAX_OPTIONS = 3


class _Strict(BaseModel):
    # Names are stored as sent, so surrounding spaces are dropped; a blank name then fails min_length.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DiscountInput(_Strict):
    discountedPriceKrw: int = Field(ge=1, le=MAX_MENU_PRICE_KRW, description="Lower than the option's `priceKrw`")
    startsAt: AwareDatetime = Field(description="With a time zone; may be in the past")
    endsAt: AwareDatetime = Field(description="The list price applies again from here; after `startsAt` and now")


class MenuOptionInput(_Strict):
    optionLabel: str | None = Field(
        default=None, min_length=1, max_length=100, description='e.g. "잔" or "병"; null for none'
    )
    pourMl: int | None = Field(
        default=None, ge=1, le=MAX_POUR_ML, description="Stored as sent; the bar's default pour is not filled in"
    )
    priceKrw: int = Field(ge=1, le=MAX_MENU_PRICE_KRW, description="List price")
    discount: DiscountInput | None = Field(default=None, description="Send the current one back to keep it")


Options = Annotated[
    list[MenuOptionInput],
    Field(min_length=1, max_length=MAX_OPTIONS, description="1 to 3 options in display order; replaces all options"),
]


class NewMenuProduct(_Strict):
    """A product not in the catalog, the same as a review's `create_product` (spec 8.1)."""

    brand: BrandDecision
    product: NewProduct
    aliases: list[ProductAliasInput] = Field(default_factory=list)


class LocalMenuInput(_Strict):
    category: str = Field(min_length=1, max_length=30, description="Store-only category; whisky requests operator approval")


class MenuItemAddRequest(_Strict):
    menuVersion: int | None = Field(description="`menuVersion` of the menu the edit was made on; null without one")
    productId: UUID | None = Field(default=None, description="An active catalog product; or send `newProduct`")
    newProduct: NewMenuProduct | None = None
    localItem: LocalMenuInput | None = None
    displayName: str | None = Field(
        default=None, min_length=1, max_length=200, description="Name on the menu; null for the product's name"
    )
    options: Options


class MenuItemUpdateRequest(_Strict):
    menuVersion: int = Field(description="`menuVersion` of the menu the edit was made on")
    displayName: str = Field(min_length=1, max_length=200, description="Name on the menu")
    category: str | None = Field(default=None, min_length=1, max_length=30,
        description="Category for this bar only; changing canonical item type detaches it into a local menu item")
    options: Options


class MenuResetRequest(_Strict):
    menuVersion: int | None = Field(description="`menuVersion` of the menu the edit was made on; null without one")


class SoldOutRequest(_Strict):
    soldOut: StrictBool = Field(description="true to mark the item sold out, false to put it back on sale")


class MenuConfirmRequest(_Strict):
    menuVersion: int | None = Field(description="`menuVersion` of the menu that was confirmed; null without one")
