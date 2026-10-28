"""`MatchingLLM` with Gemini: the same request as the M3 experiment (ai/match_llm/llm.py).

The client, retries and wall-clock timeout are those of menu extraction
(`app.extraction.gemini`), with fewer attempts and shorter timeouts: a failed call only
leaves a line with its rule result, so it is not worth holding the import for minutes.
The API key is read from GEMINI_API_KEY by the caller and never logged.
"""

import json
from typing import Any

from app.adapters.matching_llm import MODEL, THINKING_LEVEL, MatchingLLMError
from app.extraction import ExtractionSettings, ModelCallError, gemini

MAX_ATTEMPTS = 2
REQUEST_TIMEOUT_S = 60.0
WALL_TIMEOUT_S = 75.0


class GeminiMatchingLLM:
    def __init__(self, api_key: str, client: Any = None) -> None:
        # ExtractionSettings keeps the key out of its repr.
        self._settings = ExtractionSettings(
            api_key=api_key,
            model=MODEL,
            thinking_level=THINKING_LEVEL,
            max_attempts=MAX_ATTEMPTS,
            request_timeout_s=REQUEST_TIMEOUT_S,
            wall_timeout_s=WALL_TIMEOUT_S,
        )
        self._client = client

    def generate_json(self, prompt: str, payload: dict[str, Any], response_schema: dict[str, Any]) -> str:
        request = dict(
            model=MODEL,
            system_instruction=prompt,
            input=[{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            response_format={"type": "text", "mime_type": "application/json", "schema": response_schema},
            generation_config={"thinking_level": THINKING_LEVEL},
            store=False,
        )
        if self._client is None:
            self._client = gemini.make_client(self._settings)
        try:
            result = gemini.call_with_retries(self._settings, request, self._client)
        except ModelCallError as error:
            raise MatchingLLMError(str(error)) from error
        return getattr(result.interaction, "output_text", None) or ""
