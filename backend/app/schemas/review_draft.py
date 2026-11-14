"""The review draft (API spec 5.9): saving it, and how the review data returns it (5.4)."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UtcDateTime

# The size limit of a draft's content written as JSON (spec 5.9).
MAX_DRAFT_BYTES = 262_144


class ReviewDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draftVersion: int = Field(ge=0, description="The draft version last read; 0 when no draft was saved")
    reviewVersion: int = Field(ge=1, description="The reviewVersion of the review data the draft was entered on")
    content: dict[str, Any] = Field(
        description=(
            "The unfinished input: `itemDecisions` and `changeDecisions` in the submission's shape (spec 8.1) "
            "with any field but `extractedItemId` left out, and `clientState` for the client alone. Not "
            "checked beyond being an object of at most 256 KB as JSON; other top-level fields are kept."
        )
    )


class ReviewDraftSavedResponse(BaseModel):
    menuImportId: UUID
    draftVersion: int = Field(description="Send it with the next save")
    savedAt: UtcDateTime


class ReviewDraft(BaseModel):
    """The saved draft in the review data (spec 5.4)."""

    draftVersion: int
    reviewVersion: int = Field(description="The review data was rebuilt since when it differs from the response's")
    savedAt: UtcDateTime
    content: dict[str, Any]
