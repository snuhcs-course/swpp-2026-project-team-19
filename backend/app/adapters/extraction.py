"""Menu extraction: one image in, the recognized menu blocks out (API spec 4.3 response format).

`MockMenuExtractor` stands in until the AI pipeline (P14) is ready; a real extractor
implements `MenuExtractor` and returns its model output through `parse_extraction_response`.
"""

import json
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any, Protocol

from app.models import ExtractionApproach, LineType

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Column limits of extracted_items and extracted_options.
_TEXT_LIMITS = {"productName": 200, "brandText": 120, "editionName": 150}
_OPTION_LABEL_LIMIT = 100
_SMALLINT_MAX = 32767


class ExtractionError(Exception):
    """The image could not be extracted or the response is not in the expected format.

    `raw_output` is what the model returned, if anything (e.g. its text and call metadata);
    it is stored on the failed run (API spec 4.3).
    """

    def __init__(self, message: str, *, raw_output: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.raw_output = raw_output


@dataclass(frozen=True)
class ExtractedOptionData:
    option_label: str | None
    pour_ml: int | None
    price_krw: int | None


@dataclass(frozen=True)
class ExtractedItemData:
    item_order: int
    raw_text: str
    line_type: LineType
    product_name: str | None = None
    brand_text: str | None = None
    age_years: int | None = None
    edition_name: str | None = None
    abv: Decimal | None = None
    confidence: Decimal | None = None
    options: tuple[ExtractedOptionData, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExtractionResult:
    items: list[ExtractedItemData]
    # Stored as extraction_runs.raw_output.
    raw_output: dict[str, Any]


class MenuExtractor(Protocol):
    # Recorded on extraction_runs so each result can be traced to what produced it.
    approach: ExtractionApproach
    provider: str
    model_name: str
    pipeline_version: str

    def extract(self, image: bytes, content_type: str, filename: str | None) -> ExtractionResult:
        """Raises ExtractionError when the image cannot be extracted."""
        ...


def _int(value: Any, where: str, *, minimum: int, maximum: int = _SMALLINT_MAX, nullable: bool = True) -> int | None:
    if value is None and nullable:
        return None
    # bool is an int subclass; a JSON true is never a valid count or price.
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ExtractionError(f"{where} must be an integer between {minimum} and {maximum}, got {value!r}")
    return value


def _decimal(value: Any, where: str, *, maximum: float, places: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= maximum:
        raise ExtractionError(f"{where} must be a number between 0 and {maximum}, got {value!r}")
    return Decimal(str(value)).quantize(Decimal(places))


def _text(value: Any, where: str, limit: int | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ExtractionError(f"{where} must be a non-empty string or null, got {value!r}")
    if limit is not None and len(value) > limit:
        raise ExtractionError(f"{where} is longer than {limit} characters")
    return value


def parse_extraction_response(payload: Any) -> list[ExtractedItemData]:
    """Check the format of an extraction response and convert it.

    This validates shape, enums, lengths and ranges only; whether a line really is a
    product is left to the operator's review.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ExtractionError("Response must be an object with an 'items' array")

    items: list[ExtractedItemData] = []
    seen_orders: set[int] = set()
    for index, raw in enumerate(payload["items"]):
        where = f"items[{index}]"
        if not isinstance(raw, dict):
            raise ExtractionError(f"{where} must be an object")
        item_order = _int(raw.get("itemOrder"), f"{where}.itemOrder", minimum=1, nullable=False)
        if item_order in seen_orders:
            raise ExtractionError(f"{where}.itemOrder {item_order} is repeated")
        seen_orders.add(item_order)
        raw_text = _text(raw.get("rawText"), f"{where}.rawText", None)
        if raw_text is None:
            raise ExtractionError(f"{where}.rawText is required")
        try:
            line_type = LineType(raw.get("lineType"))
        except ValueError:
            raise ExtractionError(f"{where}.lineType is not one of {[t.value for t in LineType]}") from None

        raw_options = raw.get("options") or []
        if not isinstance(raw_options, list):
            raise ExtractionError(f"{where}.options must be an array")
        options = []
        for option_index, option in enumerate(raw_options):
            option_where = f"{where}.options[{option_index}]"
            if not isinstance(option, dict):
                raise ExtractionError(f"{option_where} must be an object")
            options.append(
                ExtractedOptionData(
                    option_label=_text(option.get("optionLabel"), f"{option_where}.optionLabel", _OPTION_LABEL_LIMIT),
                    pour_ml=_int(option.get("pourMl"), f"{option_where}.pourMl", minimum=1),
                    price_krw=_int(option.get("priceKrw"), f"{option_where}.priceKrw", minimum=0, maximum=2**31 - 1),
                )
            )

        items.append(
            ExtractedItemData(
                item_order=item_order,
                raw_text=raw_text,
                line_type=line_type,
                product_name=_text(raw.get("productName"), f"{where}.productName", _TEXT_LIMITS["productName"]),
                brand_text=_text(raw.get("brandText"), f"{where}.brandText", _TEXT_LIMITS["brandText"]),
                age_years=_int(raw.get("ageYears"), f"{where}.ageYears", minimum=0, maximum=200),
                edition_name=_text(raw.get("editionName"), f"{where}.editionName", _TEXT_LIMITS["editionName"]),
                abv=_decimal(raw.get("abv"), f"{where}.abv", maximum=100, places="0.01"),
                confidence=_decimal(raw.get("confidence"), f"{where}.confidence", maximum=1, places="0.0001"),
                options=tuple(options),
            )
        )
    return items


@cache
def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / f"mock_menu_{name}.json").read_text(encoding="utf-8"))


class MockMenuExtractor:
    """Returns a fixed result whatever the image, chosen by the uploaded file name.

    - name contains "fail": raises ExtractionError (to exercise the failed state)
    - name contains "sample": a short menu with an exact match, an age conflict,
      an unknown product, a section header and a description
    - otherwise: a real labeled menu photo (8 whiskies and 2 cognacs) plus a header
      and a description line
    """

    approach = ExtractionApproach.VISION_LLM
    provider = "mock"
    model_name = "mock"
    pipeline_version = "bottlemap-menu-mock-v1"

    def extract(self, image: bytes, content_type: str, filename: str | None) -> ExtractionResult:
        name = (filename or "").lower()
        if "fail" in name:
            raise ExtractionError("Mock extraction failure requested by the file name")
        payload = load_fixture("sample" if "sample" in name else "label")
        return ExtractionResult(items=parse_extraction_response(payload), raw_output=payload)
