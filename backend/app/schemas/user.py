from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.schemas.bar_hours import single_line
from app.schemas.common import UtcDateTime

# Counted in characters (code points), as Python and the database count them.
MAX_DISPLAY_NAME_LENGTH = 20


class CurrentUserResponse(BaseModel):
    userId: UUID = Field(description="The BottleMap user id (users.id), not the Supabase subject")
    email: str | None = Field(description="From the token; null when it has none or another user has it")
    displayName: str | None = Field(description="At most 20 characters; null when unknown")
    userType: Literal["customer", "operator"]
    updatedAt: UtcDateTime = Field(description="When the user's stored values last changed")


class CurrentUserUpdateInput(BaseModel):
    """PATCH /api/me (spec 3.3): only the display name can change; any other field is `EXTRA_FORBIDDEN`."""

    # No str_strip_whitespace: it would also drop leading and trailing line breaks and tabs before
    # they could be rejected as INVALID_CHARACTER.
    model_config = ConfigDict(extra="forbid")

    displayName: str = Field(
        max_length=MAX_DISPLAY_NAME_LENGTH,
        description="1-20 characters (code points) after trimming, one line. It cannot be removed",
    )

    @field_validator("displayName", mode="before")
    @classmethod
    def _one_line_then_trimmed(cls, value: object) -> object:
        # A non-string is left for the type check (STRING_TYPE). Line breaks and control characters are
        # rejected anywhere, the ends included; only then are the surrounding spaces trimmed.
        if not isinstance(value, str):
            return value
        trimmed = single_line(value).strip()
        if not trimmed:
            # Spec 3.3 asks for BLANK, not the STRING_TOO_SHORT that min_length would give.
            raise PydanticCustomError("blank", "표시 이름을 입력해 주세요.")
        return trimmed
