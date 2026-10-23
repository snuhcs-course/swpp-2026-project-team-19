from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UtcDateTime


class CurrentUserResponse(BaseModel):
    userId: UUID = Field(description="The BottleMap user id (users.id), not the Supabase subject")
    email: str | None = Field(description="From the token; null when it has none or another user has it")
    displayName: str | None = Field(description="At most 20 characters; null when unknown")
    userType: Literal["customer", "operator"]
    updatedAt: UtcDateTime = Field(description="When the user's stored values last changed")
