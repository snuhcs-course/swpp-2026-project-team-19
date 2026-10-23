"""Exceptions raised by menu extraction. Callers can catch `ExtractionError` for all of them."""

from typing import Any


class ExtractionError(Exception):
    """Base class for every extraction failure."""


class ExtractionConfigError(ExtractionError):
    """A required environment variable is missing or invalid."""


class UnsupportedImageError(ExtractionError):
    """The image bytes or MIME type cannot be sent to the model."""


class ModelCallError(ExtractionError):
    """The model call failed: a non-transient API error, or retries ran out."""

    def __init__(self, message: str, *, attempts: int) -> None:
        super().__init__(message)
        self.attempts = attempts


class InvalidModelOutputError(ExtractionError):
    """The model answered, but the answer is not valid extraction output.

    `raw_text` is the model's text as received and `meta` the call metadata, so the
    caller can record the partial response (flow v2 4.3: status = failed).
    """

    def __init__(self, message: str, *, raw_text: str | None, meta: dict[str, Any]) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.meta = meta
