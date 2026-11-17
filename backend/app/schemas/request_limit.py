from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RequestLimitKind = Literal["business_verification", "business_certificate_ocr"]


class RequestLimitResetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userId: UUID | None = Field(
        default=None, description="`users.id` whose counts to clear; every user, with or without a row, if null"
    )
    kind: RequestLimitKind | None = Field(
        default=None,
        description="`business_verification` (NTS checks) or `business_certificate_ocr`; both if null",
    )


class RequestLimitResetResponse(BaseModel):
    clearedCount: int = Field(
        description="How many counts (one per user and kind used today) were cleared; 0 when there were none",
        examples=[1],
    )
