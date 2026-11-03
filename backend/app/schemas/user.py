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

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    displayName: str = Field(
        max_length=MAX_DISPLAY_NAME_LENGTH,
        description="1-20 characters (code points) after trimming, one line. It cannot be removed",
    )

    @field_validator("displayName")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        # Spec 3.3 asks for BLANK, not the STRING_TOO_SHORT that min_length would give.
        if not value:
            raise PydanticCustomError("blank", "표시 이름을 입력해 주세요.")
        return single_line(value)
