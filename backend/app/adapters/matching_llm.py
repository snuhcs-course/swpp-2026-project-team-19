"""The LLM behind the matching LLM layer (`app.matching.llm_layer`), and its settings.

The layer is off unless MATCHING_LLM_ENABLED=true. The model and thinking level are the
frozen M3 values (ai/match_llm/llm.py), not settings, so the offline evaluation numbers
describe what the server runs. `GeminiMatchingLLM` (app.adapters.gemini_matching_llm) is
the real implementation; tests use fakes and never call the API.
"""

import os
from dataclasses import dataclass
from typing import Any, Protocol

MODEL = "gemini-3.1-flash-lite"
THINKING_LEVEL = "low"
DEFAULT_MAX_CALLS = 30


class MatchingLLMError(Exception):
    """The call failed: an API error, a timeout, or retries ran out."""


class MatchingLLM(Protocol):
    def generate_json(self, prompt: str, payload: dict[str, Any], response_schema: dict[str, Any]) -> str:
        """Send the system prompt and the payload (as JSON text); return the model's text as is.

        The text is meant to follow `response_schema`; the caller validates it. Raises on
        failure (MatchingLLMError for API errors); the caller treats any exception as no answer.
        """
        ...


@dataclass(frozen=True)
class MatchingLLMSettings:
    enabled: bool = False
    # Model requests per menu import (M3a and M3b together); retries inside one request are not counted.
    max_calls: int = DEFAULT_MAX_CALLS
    # M3b (pick one product of the brands named) was not adopted in the I2 evaluation, so it stays off.
    m3b_enabled: bool = False


def load_matching_llm_settings() -> MatchingLLMSettings:
    """Read the MATCHING_LLM_* variables; raise RuntimeError for an invalid call cap."""
    raw = os.getenv("MATCHING_LLM_MAX_CALLS")
    max_calls = DEFAULT_MAX_CALLS
    if raw:
        try:
            max_calls = int(raw)
        except ValueError:
            max_calls = 0
        if max_calls <= 0:
            raise RuntimeError(f"MATCHING_LLM_MAX_CALLS must be a positive int, got {raw!r}")
    return MatchingLLMSettings(
        enabled=_flag("MATCHING_LLM_ENABLED"),
        max_calls=max_calls,
        m3b_enabled=_flag("MATCHING_LLM_M3B_ENABLED"),
    )


def _flag(name: str) -> bool:
    return os.getenv(name, "false").lower() == "true"
