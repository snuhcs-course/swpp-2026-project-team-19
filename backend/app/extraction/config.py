"""Extraction settings from environment variables.

The model and thinking level are required so a deployment states them explicitly;
`backend/.env.example` lists the values adopted in P14 (condition A2). Retry and
timeout defaults are the P14 experiment values.
"""

import os
from dataclasses import dataclass

from app.extraction.errors import ExtractionConfigError

THINKING_LEVELS = ("minimal", "low", "medium", "high")


@dataclass(frozen=True)
class ExtractionSettings:
    api_key: str
    model: str
    thinking_level: str
    max_attempts: int = 6
    request_timeout_s: float = 300
    wall_timeout_s: float = 330

    def __repr__(self) -> str:  # keep the key out of logs and tracebacks
        return (
            f"ExtractionSettings(model={self.model!r}, thinking_level={self.thinking_level!r}, "
            f"max_attempts={self.max_attempts}, request_timeout_s={self.request_timeout_s}, "
            f"wall_timeout_s={self.wall_timeout_s})"
        )


def load_settings() -> ExtractionSettings:
    """Read settings from the environment; raise ExtractionConfigError if anything is wrong."""
    required = ("GEMINI_API_KEY", "EXTRACTION_MODEL", "EXTRACTION_THINKING_LEVEL")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ExtractionConfigError(f"Missing required extraction environment variables: {', '.join(missing)}")

    thinking_level = os.environ["EXTRACTION_THINKING_LEVEL"]
    if thinking_level not in THINKING_LEVELS:
        raise ExtractionConfigError(
            f"EXTRACTION_THINKING_LEVEL must be one of {', '.join(THINKING_LEVELS)}, got {thinking_level!r}"
        )

    return ExtractionSettings(
        api_key=os.environ["GEMINI_API_KEY"],
        model=os.environ["EXTRACTION_MODEL"],
        thinking_level=thinking_level,
        max_attempts=_positive("EXTRACTION_MAX_ATTEMPTS", ExtractionSettings.max_attempts, int),
        request_timeout_s=_positive("EXTRACTION_REQUEST_TIMEOUT_S", ExtractionSettings.request_timeout_s, float),
        wall_timeout_s=_positive("EXTRACTION_WALL_TIMEOUT_S", ExtractionSettings.wall_timeout_s, float),
    )


def _positive(name: str, default, kind: type[int] | type[float]):
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = kind(raw)
    except ValueError:
        value = 0
    if value <= 0:
        raise ExtractionConfigError(f"{name} must be a positive {kind.__name__}, got {raw!r}")
    return value
