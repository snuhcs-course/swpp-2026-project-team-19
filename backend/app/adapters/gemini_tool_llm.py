"""Gemini with function calling for the tool matching layer (`app.matching.tool_layer`).

One `step` sends the system prompt, the conversation so far and the tool declarations and
returns the model's function calls. Function calls are forced (mode ANY), so the model
always answers with a tool call and ends with `submit_answers`. Gemini 3 function calls
carry a thought signature that must be sent back with them; `step` returns it (base64)
and the history it is given puts it back on the part.
"""

import base64
from typing import Any

from google import genai
from google.genai import types

REQUEST_TIMEOUT_MS = 60_000


class GeminiToolLLM:
    def __init__(self, api_key: str, model: str, thinking_level: str = "low", client: Any = None) -> None:
        self.model = model
        self.thinking_level = thinking_level
        self._client = client or genai.Client(api_key=api_key,
                                              http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))

    def step(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(name=t["name"], description=t["description"],
                                          parameters_json_schema=t["parameters"]) for t in tools])],
            tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="ANY")),
            thinking_config=types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel, self.thinking_level.upper())),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = self._client.models.generate_content(model=self.model, contents=_contents(history), config=config)
        calls = []
        parts = (response.candidates[0].content.parts or []) if response.candidates else []
        for part in parts:
            if part.function_call is not None:
                sig = part.thought_signature
                calls.append({"name": part.function_call.name, "args": dict(part.function_call.args or {}),
                              "sig": base64.b64encode(sig).decode() if sig else None})
        usage = response.usage_metadata
        return {"calls": calls,
                "usage": {"input_tokens": getattr(usage, "prompt_token_count", None),
                          "output_tokens": getattr(usage, "candidates_token_count", None),
                          "thought_tokens": getattr(usage, "thoughts_token_count", None)}}


def _contents(history: list[dict]) -> list[types.Content]:
    out = []
    for m in history:
        if m["role"] == "user":
            out.append(types.Content(role="user", parts=[types.Part.from_text(text=m["text"])]))
        elif m["role"] == "model":
            out.append(types.Content(role="model", parts=[
                types.Part(function_call=types.FunctionCall(name=c["name"], args=c["args"]),
                           thought_signature=base64.b64decode(c["sig"]) if c.get("sig") else None)
                for c in m["calls"]]))
        else:  # tool results
            out.append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=r["name"], response=r["response"]) for r in m["responses"]]))
    return out
