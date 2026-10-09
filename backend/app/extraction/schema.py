# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-06, PR #10). Reviewed by Jinwoo Park.
"""Response models: what the model returns (prompt v1) and what extract_menu returns (flow v2 4.3).

The v1 models must stay identical to ai/extract/extract.py: their JSON schema is sent
to the model as the response schema, so the class and field names are part of the
request. tests/test_extraction.py pins the generated schema.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---- Prompt v1 output (sent as the response schema) ----


class MenuItem(BaseModel):
    raw_name: str
    price_krw: Optional[int]
    pour_ml: Optional[int]
    unit: Optional[Literal["glass", "bottle"]]


class MenuExtraction(BaseModel):
    items: list[MenuItem]


# ---- Flow v2 4.3 output (validated before it is returned) ----

LineType = Literal["product", "section_header", "description", "unknown"]

# Upper bounds follow the menu tables: display_name String(200), option_label String(100),
# pour_ml SmallInteger. The price cap only rejects misread values (bottles here are < 1,000,000).
MAX_TEXT = 200
MAX_PRICE_KRW = 10_000_000
MAX_POUR_ML = 32_767


class ExtractedOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optionLabel: str | None = Field(min_length=1, max_length=100)
    pourMl: int | None = Field(ge=1, le=MAX_POUR_ML)
    priceKrw: int | None = Field(ge=1, le=MAX_PRICE_KRW)

    @model_validator(mode="after")
    def _not_empty(self) -> "ExtractedOption":
        if self.optionLabel is None and self.pourMl is None and self.priceKrw is None:
            raise ValueError("an option needs at least one of optionLabel, pourMl, priceKrw")
        return self


class ExtractedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    itemOrder: int = Field(ge=1)
    rawText: str = Field(min_length=1, max_length=MAX_TEXT)
    lineType: LineType
    productName: str | None = Field(min_length=1, max_length=MAX_TEXT)
    brandText: str | None = Field(min_length=1, max_length=MAX_TEXT)
    ageYears: int | None = Field(ge=1, le=100)
    editionName: str | None = Field(min_length=1, max_length=MAX_TEXT)
    abv: float | None = Field(gt=0, le=100)
    options: list[ExtractedOption]
    confidence: float | None = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _fields_match_line_type(self) -> "ExtractedItem":
        if self.lineType == "product":
            if self.productName is None:
                raise ValueError("a product line needs productName")
            keys = [(o.optionLabel, o.pourMl) for o in self.options]
            if len(keys) != len(set(keys)):
                raise ValueError("options repeat the same optionLabel and pourMl")
        else:
            product_fields = (self.productName, self.brandText, self.ageYears, self.editionName, self.abv)
            if self.options or any(v is not None for v in product_fields):
                raise ValueError(f"a {self.lineType} line must have no options and no product fields")
        return self


class ExtractionItems(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ExtractedItem]

    @model_validator(mode="after")
    def _unique_order(self) -> "ExtractionItems":
        orders = [item.itemOrder for item in self.items]
        if len(orders) != len(set(orders)):
            raise ValueError("itemOrder values must be unique")
        return self
