"""GeminiToolLLM with a fake client: request shape, function calls, thought signatures. No API call."""

import base64
from types import SimpleNamespace

from google.genai import types

from app.adapters.gemini_tool_llm import GeminiToolLLM, _contents
from app.matching.tool_layer import TOOLS


class FakeModels:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def generate_content(self, **request):
        self.requests.append(request)
        return self.response


def response(*parts, usage=(10, 2, 5)):
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=list(parts)))] if parts else [],
        usage_metadata=SimpleNamespace(prompt_token_count=usage[0], candidates_token_count=usage[1],
                                       thoughts_token_count=usage[2]))


def test_step_sends_forced_tool_calls_and_returns_calls_with_signatures():
    part = types.Part(function_call=types.FunctionCall(name="search_catalog", args={"query": "Caol Ila 12"}),
                      thought_signature=b"sig")
    text = types.Part.from_text(text="thinking out loud")
    models = FakeModels(response(text, part))
    llm = GeminiToolLLM("key", "gemini-3.1-flash-lite", client=SimpleNamespace(models=models))
    out = llm.step("system", [{"role": "user", "text": "{}"}], TOOLS)
    assert out["calls"] == [{"name": "search_catalog", "args": {"query": "Caol Ila 12"},
                             "sig": base64.b64encode(b"sig").decode()}]
    assert out["usage"] == {"input_tokens": 10, "output_tokens": 2, "thought_tokens": 5}
    request = models.requests[0]
    config = request["config"]
    assert request["model"] == "gemini-3.1-flash-lite" and config.system_instruction == "system"
    assert config.tool_config.function_calling_config.mode == types.FunctionCallingConfigMode.ANY
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert [f.name for f in config.tools[0].function_declarations] == [t["name"] for t in TOOLS]
    assert config.automatic_function_calling.disable


def test_no_candidate_means_no_calls():
    llm = GeminiToolLLM("key", "m", client=SimpleNamespace(models=FakeModels(response())))
    assert llm.step("s", [{"role": "user", "text": "x"}], TOOLS)["calls"] == []


def test_history_is_rebuilt_with_signatures_and_tool_results():
    sig = base64.b64encode(b"abc").decode()
    contents = _contents([
        {"role": "user", "text": "lines"},
        {"role": "model", "calls": [{"name": "search_catalog", "args": {"query": "x"}, "sig": sig},
                                    {"name": "get_product", "args": {"product_id": "p1"}, "sig": None}]},
        {"role": "tool", "responses": [{"name": "search_catalog", "response": {"results": []}}]},
    ])
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[1].parts[0].thought_signature == b"abc" and contents[1].parts[1].thought_signature is None
    assert contents[2].parts[0].function_response.name == "search_catalog"


def test_client_is_made_from_the_key():
    llm = GeminiToolLLM("not-a-real-key", "m")
    assert llm.model == "m" and llm._client is not None
