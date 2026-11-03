"""MATCHING_LLM_MODE: which LLM matching layer menu import runs when MATCHING_LLM_ENABLED=true.

    m3a    (default) M3a, `app.matching.llm_layer`: per photo the model translates the unconfirmed
           lines and code looks the catalog up. Adopted in I2; what the server ran before this setting.
    tools  E10, `app.matching.tool_layer`: per photo the model searches the catalog itself with
           function calls (up to `tool_layer.MAX_TURNS` requests). Whether it replaces M3a is
           decided by the held-out evaluation (ai/docs/i3_eval_freeze.md 4.10).

This is its own module rather than a field of `MatchingLLMSettings` because
`app.adapters.matching_llm` and the other M3a files are pinned by SHA-256 for the I3 evaluation
(i3_eval_freeze.md 4.5) and stay byte-for-byte unchanged. The tool layer runs the model and
thinking level of 4.10, which are the M3a ones.
"""

import os
from typing import Literal

from app.adapters.matching_llm import MODEL, THINKING_LEVEL

MatchingLLMMode = Literal["m3a", "tools"]
MODES: tuple[MatchingLLMMode, ...] = ("m3a", "tools")
DEFAULT_MODE: MatchingLLMMode = "m3a"
# i3_eval_freeze.md 4.10: gemini-3.1-flash-lite, thinking low. The evaluation harness switches to
# gemini-3.5-flash-lite after a quota error; the server does not (E10's server code has no fallback),
# so a quota error is a failed request like any other and the photo keeps its rule results.
TOOLS_MODEL = MODEL
TOOLS_THINKING_LEVEL = THINKING_LEVEL


def load_matching_llm_mode() -> MatchingLLMMode:
    """Read MATCHING_LLM_MODE (unset or empty: m3a); raise RuntimeError for any other value."""
    raw = os.getenv("MATCHING_LLM_MODE")
    if not raw:
        return DEFAULT_MODE
    mode = raw.strip().lower()
    if mode not in MODES:
        raise RuntimeError(f"MATCHING_LLM_MODE must be one of {', '.join(MODES)}, got {raw!r}")
    return mode  # type: ignore[return-value]
