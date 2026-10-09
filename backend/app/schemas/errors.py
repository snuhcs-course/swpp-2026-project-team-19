# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9). Reviewed by Haeul Yang.
"""OpenAPI models for the common error format produced by app.core.errors."""

from typing import Any

from pydantic import BaseModel, Field


class FieldErrorResponse(BaseModel):
    path: str = Field(description='Request field, e.g. "query" or "itemDecisions[0].optionDecisions[1].correctedPriceKrw"')
    code: str = Field(description='Machine-readable reason, e.g. "MISSING", "STRING_TOO_LONG", "BLANK"')
    message: str


class ErrorBody(BaseModel):
    code: str = Field(description="Branch on this, not on message, e.g. BAR_NOT_FOUND or VALIDATION_FAILED")
    message: str = Field(description="Default text that can be shown to users")
    details: dict[str, Any] | None = Field(description="Code-specific context such as the requested id")
    fieldErrors: list[FieldErrorResponse] = Field(description="Filled for VALIDATION_FAILED")


class ErrorResponse(BaseModel):
    error: ErrorBody


def error_responses(*entries: tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    """`responses=` for a route: (status, description listing the error codes) pairs.

    A 422 entry is always included, replacing FastAPI's default validation error
    schema, which does not match what the API returns.
    """
    responses: dict[int | str, dict[str, Any]] = {
        422: {"model": ErrorResponse, "description": "`VALIDATION_FAILED`: see `fieldErrors`."}
    }
    for status, description in entries:
        responses[status] = {"model": ErrorResponse, "description": description}
    return responses
