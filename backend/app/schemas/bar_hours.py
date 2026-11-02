"""Opening hours and temporary closures (API spec 3.15): the regular weekly hours sent with
PATCH /api/bars/{barId} (3.7), the operating exception request (3.15.2), and both in the bar responses.

Times and dates are Seoul local values sent as `"HH:MM"` and `"YYYY-MM-DD"` text, never converted to UTC.
The shapes, lengths and formats are checked here. The rules that compare fields (`MISSING`,
`TIME_ON_CLOSED_DAY`, `SAME_OPEN_CLOSE`, `DUPLICATE_DAY`, `END_BEFORE_START`) and the ones that need
today's date are checked by app.services.bar_hours and app.services.operating_exception.
"""

import re
import unicodedata
from datetime import date, time
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, StrictBool, WithJsonSchema
from pydantic import field_validator
from pydantic_core import PydanticCustomError

from app.core.errors import register_union_tags

TIME_PATTERN = "^([01][0-9]|2[0-3]):[0-5][05]$"
DATE_PATTERN = "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
_TIME_TEXT = re.compile(TIME_PATTERN)
_DATE_TEXT = re.compile(DATE_PATTERN)


def single_line(value: str) -> str:
    """Rejects line breaks and control characters (`INVALID_CHARACTER`)."""
    if any(unicodedata.category(char) in {"Cc", "Zl", "Zp"} for char in value):
        raise PydanticCustomError("invalid_character", "줄바꿈이나 제어 문자는 쓸 수 없습니다.")
    return value


def _time_text(value: object) -> object:
    # Only "HH:MM" text in 5-minute steps: Pydantic would otherwise accept seconds, "9:00" or a number.
    if not isinstance(value, str) or not _TIME_TEXT.fullmatch(value):
        raise PydanticCustomError("invalid_time", "시각은 00:00부터 23:55까지 5분 단위의 HH:MM으로 보내 주세요.")
    return value


def _date_text(value: object) -> object:
    # Only `YYYY-MM-DD` text, as for the owner application's openingDate; a day that does not exist
    # still fails Pydantic's own date check.
    if not isinstance(value, str) or not _DATE_TEXT.fullmatch(value):
        raise PydanticCustomError("date_from_datetime_parsing", "Input should be a valid date in YYYY-MM-DD format")
    return value


def _time_string(value: time) -> str:
    return value.strftime("%H:%M")


_TIME_SCHEMA = WithJsonSchema({"type": "string", "pattern": TIME_PATTERN, "examples": ["18:00"]})
_DATE_SCHEMA = WithJsonSchema({"type": "string", "format": "date", "examples": ["2026-11-06"]})

TimeInput = Annotated[time, BeforeValidator(_time_text), _TIME_SCHEMA]
DateInput = Annotated[date, BeforeValidator(_date_text), _DATE_SCHEMA]
LocalTime = Annotated[time, PlainSerializer(_time_string, return_type=str), _TIME_SCHEMA]
LocalDate = Annotated[date, _DATE_SCHEMA]

OperatingExceptionKind = Literal["closed_today", "custom_hours", "vacation"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WeeklyHoursInput(_Strict):
    dayOfWeek: int = Field(ge=1, le=7, description="ISO 8601: 1 = Monday .. 7 = Sunday; once per array")
    closed: StrictBool = Field(description="true for a regular day off")
    openTime: TimeInput | None = Field(
        default=None, description="Seoul local `HH:MM`, 5-minute steps; required unless `closed`, absent or null if it is"
    )
    closeTime: TimeInput | None = Field(
        default=None, description="As `openTime`; earlier than `openTime` means the next day; never equal to it"
    )


class WeeklyHours(BaseModel):
    dayOfWeek: int = Field(description="ISO 8601: 1 = Monday .. 7 = Sunday")
    closed: bool = Field(description="A regular day off; its times are null")
    openTime: LocalTime | None = Field(description="Seoul local `HH:MM`; null on a day off")
    closeTime: LocalTime | None = Field(
        description="Seoul local `HH:MM`; earlier than `openTime` means the next day (`00:00` is midnight). "
        "null on a day off"
    )


class OperatingException(BaseModel):
    """A temporary closure (spec 3.15.4). It is sent through the day after `endDate`, so whether it is in
    effect now is for the app to decide from the device clock (3.15.5)."""

    kind: OperatingExceptionKind
    startDate: LocalDate = Field(description="Seoul local date; the day it was applied unless `vacation`")
    endDate: LocalDate = Field(description="Seoul local date; equal to `startDate` unless `vacation`")
    openTime: LocalTime | None = Field(description="`custom_hours` only; null otherwise")
    closeTime: LocalTime | None = Field(
        description="`custom_hours` only; earlier than `openTime` means it ends the next day. null otherwise"
    )
    note: str | None = Field(description="Message for customers; null when none")


class _OperatingExceptionInput(_Strict):
    note: str | None = Field(
        default=None, max_length=100, description="Message for customers, one line; blank is stored as null"
    )

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return single_line(value) if value else None


class ClosedTodayInput(_OperatingExceptionInput):
    kind: Literal["closed_today"]
    date: DateInput = Field(description="Today in Seoul when the user applies it")


class CustomHoursInput(_OperatingExceptionInput):
    kind: Literal["custom_hours"]
    date: DateInput = Field(description="Today in Seoul when the user applies it")
    openTime: TimeInput = Field(description="Seoul local `HH:MM`, 5-minute steps")
    closeTime: TimeInput = Field(description="As `openTime`; earlier than it means the next day; never equal to it")


class VacationInput(_OperatingExceptionInput):
    kind: Literal["vacation"]
    startDate: DateInput = Field(description="Today or later")
    endDate: DateInput = Field(description="`startDate` or later")


# The route declares the discriminator on Body(), as for the owner application.
OperatingExceptionInput = ClosedTodayInput | CustomHoursInput | VacationInput
register_union_tags("closed_today", "custom_hours", "vacation")
