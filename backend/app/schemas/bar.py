# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #13). Reviewed by Haeul Yang.
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ActiveMenuImport(BaseModel):
    menuImportId: UUID
    status: Literal["uploaded", "processing", "ready_for_review"]


class BarListItem(BaseModel):
    barId: UUID
    name: str
    address: str
    latitude: float
    longitude: float
    phone: str | None
    status: Literal["active", "inactive"]
    activeMenuImport: ActiveMenuImport | None = Field(
        description="The bar's unfinished import, to continue it without another request; null when none"
    )


class BarListResponse(BaseModel):
    items: list[BarListItem] = Field(description="Sorted by name")
    nextCursor: str | None = Field(description="Pass as `cursor` for the next page; null on the last page")
