from uuid import UUID

from pydantic import BaseModel, Field

from app.models import ImportStatus


class MenuImportAcceptedResponse(BaseModel):
    menuImportId: UUID
    status: ImportStatus = Field(description="Current status; a retried request returns the existing import's status")
    imageCount: int
    statusUrl: str = Field(description="Poll this with GET for progress and, when ready, the review data")
    pollAfterMs: int = Field(description="Suggested polling interval")
