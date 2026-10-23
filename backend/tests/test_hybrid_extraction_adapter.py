"""Hybrid extraction (CLOVA OCR + Gemini) and EXTRACTION_MODE. CLOVA goes through an httpx
MockTransport or a fake call_ocr, Gemini through a fake client; no test calls a real API."""

import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from app import extraction
from app.adapters.extraction import ExtractionError, ExtractionResult
from app.adapters.gemini_extraction import GeminiMenuExtractor
from app.adapters.hybrid_extraction import HybridMenuExtractor
from app.api import deps
from app.extraction import clova, gemini, hybrid
from app.models import ExtractionApproach

SETTINGS = extraction.ExtractionSettings(api_key="secret-test-key", model="gemini-3.5-flash-lite", thinking_level="medium")
CLOVA = clova.ClovaSettings(invoke_url="https://ocr.example.test/custom/v1/1/abc/general", secret="clova-secret")
REPO_ROOT = Path(__file__).resolve().parents[2]


def jpeg(size=(1000, 2000)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, format="JPEG")
    return out.getvalue()


def field(text, x0, y0, x1, y1, line_break):
    return {"inferText": text, "lineBreak": line_break,
            "boundingPoly": {"vertices": [{"x": x0, "y": y0}, {"x": x1, "y": y0}, {"x": x1, "y": y1}, {"x": x0, "y": y1}]}}


# Made-up menu, image 1000 x 2000: a title, one name with glass and bottle prices far to the right.
OCR_RESPONSE = {"version": "V2", "images": [{"inferResult": "SUCCESS", "fields": [
    field("WHISKY", 100, 20, 260, 60, True),
    field("페른홀로우", 100, 200, 300, 240, False),
    field("12년", 310, 200, 380, 240, False),
    field("15,000", 600, 200, 700, 240, False),   # gap > 2.5 x height: own line
    field("150,000", 760, 200, 880, 240, True),
]}]}
HYBRID_OUTPUT = {"items": [
    {"raw_name": "페른홀로우 12년", "price_krw": 15000, "pour_ml": None, "unit": "glass",
     "source_lines": {"name": ["L002"], "price": ["L003"]}},
    {"raw_name": "페른홀로우 12년", "price_krw": 150000, "pour_ml": None, "unit": "bottle",
     "source_lines": {"name": ["L002"], "price": ["L003", "L099"]}},  # L099 is made up: dropped
    {"raw_name": "사진에서만 읽은 줄", "price_krw": None, "pour_ml": None, "unit": None,
     "source_lines": {"name": [], "price": []}},
]}


class FakeInteractions:
    def __init__(self, text, status="completed"):
        self.text, self.status, self.requests = text, status, []

    def create(self, **request):
        self.requests.append(request)
        usage = SimpleNamespace(total_input_tokens=5000, total_output_tokens=300, total_thought_tokens=700,
                                total_tokens=6000)
        return SimpleNamespace(output_text=self.text, status=self.status, usage=usage)


@pytest.fixture
def fake_gemini(monkeypatch):
    fake = SimpleNamespace(interactions=FakeInteractions(json.dumps(HYBRID_OUTPUT)))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)
    return fake.interactions


@pytest.fixture
def fake_ocr(monkeypatch):
    """Replace the CLOVA call; set `.error` to make it fail and read `.calls`."""

    class Fake:
        error = None
        calls: list = []

        def __call__(self, settings, image, mime_type, client=None):
            self.calls.append((settings, mime_type))
            if self.error is not None:
                raise self.error
            return {"response": OCR_RESPONSE, "sentSize": [1000, 2000], "latencyMs": 900, "attempts": 1}

    fake = Fake()
    fake.calls = []
    monkeypatch.setattr(hybrid, "call_ocr", fake)
    return fake


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    monkeypatch.setattr(clova, "sleep", lambda s: None)
    monkeypatch.setattr(gemini, "sleep", lambda s: None)


# ---- CLOVA settings and call ----


def test_clova_settings(monkeypatch):
    monkeypatch.setenv("CLOVA_OCR_INVOKE_URL", "https://ocr.example.test/custom/v1/1/abc/")
    monkeypatch.setenv("CLOVA_OCR_SECRET", "clova-secret")
    settings = clova.load_clova_settings()
    assert settings.invoke_url == "https://ocr.example.test/custom/v1/1/abc/general"
    assert "clova-secret" not in repr(settings) and "abc" not in repr(settings)


@pytest.mark.parametrize("missing", ["CLOVA_OCR_INVOKE_URL", "CLOVA_OCR_SECRET"])
def test_clova_settings_missing(monkeypatch, missing):
    monkeypatch.setenv("CLOVA_OCR_INVOKE_URL", "https://ocr.example.test/general")
    monkeypatch.setenv("CLOVA_OCR_SECRET", "clova-secret")
    monkeypatch.delenv(missing)
    with pytest.raises(extraction.ExtractionConfigError, match=missing):
        clova.load_clova_settings()


def mock_client(*responses):
    """httpx client answering with the given responses (or raising the given exceptions) in turn."""
    seen = []

    def handler(request):
        seen.append(request)
        item = responses[min(len(seen), len(responses)) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_call_ocr_sends_one_image_with_table_detection_off():
    client, seen = mock_client(httpx.Response(200, json=OCR_RESPONSE))
    out = clova.call_ocr(CLOVA, jpeg(), "image/jpeg", client)
    body = json.loads(seen[0].content)
    assert seen[0].headers["X-OCR-SECRET"] == "clova-secret"
    assert (body["version"], body["lang"], body["enableTableDetection"]) == ("V2", "ko", False)
    assert body["images"][0]["format"] == "jpg"
    assert (out["sentSize"], out["attempts"], out["response"]) == ([1000, 2000], 1, OCR_RESPONSE)


def test_call_ocr_retries_transient_errors():
    client, seen = mock_client(httpx.ConnectError("down"), httpx.Response(503), httpx.Response(200, json=OCR_RESPONSE))
    out = clova.call_ocr(CLOVA, jpeg(), "image/jpeg", client)
    assert (len(seen), out["attempts"]) == (3, 3)


@pytest.mark.parametrize("responses, message", [
    ([httpx.Response(400, json={"code": "0011"})], "HTTP 400"),
    ([httpx.Response(500)] * 3, "after 3 attempt"),
    ([httpx.Response(200, text="not json")], "not JSON"),
    ([httpx.Response(200, json={"images": [{"inferResult": "ERROR"}]})], "inferResult"),
    ([httpx.UnsupportedProtocol("bad url")], "request failed: UnsupportedProtocol"),
])
def test_call_ocr_failures(responses, message):
    client, _ = mock_client(*responses)
    with pytest.raises(clova.ClovaOCRError, match=message):
        clova.call_ocr(CLOVA, jpeg(), "image/jpeg", client)


def test_call_ocr_opens_and_closes_its_own_client(monkeypatch):
    client, seen = mock_client(httpx.Response(200, json=OCR_RESPONSE))
    monkeypatch.setattr(clova.httpx, "Client", lambda timeout: client)
    clova.call_ocr(CLOVA, jpeg(), "image/jpeg")
    assert len(seen) == 1 and client.is_closed


def test_very_long_photo_is_downscaled_for_ocr():
    out = io.BytesIO()
    Image.new("RGB", (40, 8000), "white").save(out, format="PNG")
    data, fmt, size = clova.ocr_image(out.getvalue(), "image/png")
    assert (fmt, size) == ("jpg", (40, 7999))
    assert Image.open(io.BytesIO(data)).size == (40, 7999)


# ---- lines ----


def test_lines_split_on_wide_gaps_and_scale_to_1000():
    lines = clova.build_lines(OCR_RESPONSE)
    assert [ln.text for ln in lines] == ["WHISKY", "페른홀로우 12년", "15,000 150,000"]
    table = clova.ocr_lines_table(lines, clova.image_size(OCR_RESPONSE, (1000, 2000)))
    assert table[1] == {"id": "L002", "box": [100, 100, 380, 120], "text": "페른홀로우 12년"}
    assert clova.format_lines(table).splitlines()[2] == "L003 [600,100,880,120] 15,000 150,000"


def test_lines_without_final_line_break_and_converted_size():
    response = {"images": [{"convertedImageInfo": {"width": 500, "height": 500},
                            "fields": [field("A", 0, 0, 10, 10, False), {"inferText": "B"}]}]}
    lines = clova.build_lines(response)
    assert [ln.text for ln in lines] == ["A B"]
    assert clova.image_size(response, (1, 1)) == (500.0, 500.0)
    assert clova.build_lines({}) == []


# ---- extract_menu_hybrid ----


def test_hybrid_request_has_ocr_lines_and_the_image(fake_ocr, fake_gemini):
    result = hybrid.extract_menu_hybrid(jpeg(), "image/jpeg", CLOVA, settings=SETTINGS)

    [request] = fake_gemini.requests
    text = request["input"][0]["text"]
    assert text.startswith(hybrid.USER_HEADER) and "<ocr_lines>\nL001 [100,10,260,30] WHISKY\n" in text
    assert request["input"][1]["type"] == "image"
    assert "source_lines" in json.dumps(request["response_format"]["schema"])
    assert (request["model"], request["generation_config"]) == ("gemini-3.5-flash-lite", {"thinking_level": "medium"})
    assert request["system_instruction"] == hybrid.load_prompt()

    # glass + bottle of one line -> one item with two options (same conversion as extract_menu)
    assert [i["rawText"] for i in result["items"]] == ["페른홀로우 12년", "사진에서만 읽은 줄"]
    assert [o["priceKrw"] for o in result["items"][0]["options"]] == [15000, 150000]
    meta = result["meta"]
    assert meta["mode"] == "hybrid" and meta["rawOutput"] == HYBRID_OUTPUT
    assert meta["ocr"]["lines"][2]["box"] == [600, 100, 880, 120]
    assert meta["itemSources"] == [
        {"itemOrder": 1, "nameLines": ["L002"], "priceLines": ["L003"], "box": [100, 100, 880, 120]},
        {"itemOrder": 2, "nameLines": [], "priceLines": [], "box": None},
    ]


@pytest.mark.parametrize("text, status, message", [
    ("{oops", "completed", "not valid hybrid v1 output"),
    (json.dumps(HYBRID_OUTPUT), "failed", "interaction status is 'failed'"),
    (json.dumps({"items": [{**HYBRID_OUTPUT["items"][0], "price_krw": 0}]}), "completed", "converted items failed"),
])
def test_hybrid_invalid_output(fake_ocr, monkeypatch, text, status, message):
    fake = SimpleNamespace(interactions=FakeInteractions(text, status))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)
    with pytest.raises(extraction.InvalidModelOutputError, match=message) as caught:
        hybrid.extract_menu_hybrid(jpeg(), "image/jpeg", CLOVA, settings=SETTINGS)
    assert caught.value.meta["ocr"]["lines"]  # OCR lines are kept on the failed run


def test_frozen_prompt_is_the_e2e_prompt():
    ai_copy = REPO_ROOT / "ai" / "ocr" / "hybrid_prompt_v1.md"
    if not ai_copy.exists():
        pytest.skip("ai/ocr not in this checkout")
    assert hybrid.load_prompt() == ai_copy.read_text(encoding="utf-8").replace("\r\n", "\n")


# ---- adapter ----


def test_records_what_produced_the_result():
    extractor = HybridMenuExtractor(SETTINGS, CLOVA)
    assert extractor.approach == ExtractionApproach.OCR_LLM
    assert extractor.model_name == "gemini-3.5-flash-lite"
    assert extractor.pipeline_version == "bottlemap-menu-hybrid-prompthybrid-v1-thinking-medium"


def test_adapter_keeps_boxes_in_raw_output(fake_ocr, fake_gemini):
    result = HybridMenuExtractor(SETTINGS, CLOVA).extract(jpeg(), "image/jpeg", "menu.jpg")
    assert [i.raw_text for i in result.items] == ["페른홀로우 12년", "사진에서만 읽은 줄"]
    assert result.raw_output["itemSources"][0]["box"] == [100, 100, 880, 120]
    assert fake_ocr.calls == [(CLOVA, "image/jpeg")]


def test_clova_failure_falls_back_to_gemini_only_and_logs(fake_ocr, monkeypatch, caplog):
    fake_ocr.error = clova.ClovaOCRError("CLOVA OCR failed after 3 attempt(s): HTTP 503")
    called = []

    def gemini_only(self, image, content_type, filename):
        called.append(filename)
        return ExtractionResult(items=[], raw_output={"model": "gemini-3.5-flash-lite"})

    monkeypatch.setattr(GeminiMenuExtractor, "extract", gemini_only)
    with caplog.at_level(logging.WARNING, logger="app.adapters.hybrid_extraction"):
        result = HybridMenuExtractor(SETTINGS, CLOVA).extract(jpeg(), "image/jpeg", "menu.jpg")

    assert called == ["menu.jpg"]
    assert result.raw_output == {"model": "gemini-3.5-flash-lite",
                                 "hybridFallback": {"reason": "CLOVA OCR failed after 3 attempt(s): HTTP 503"}}
    assert "falling back to Gemini only" in caplog.text and "clova-secret" not in caplog.text


@pytest.mark.parametrize("error, message, raw_output", [
    (extraction.InvalidModelOutputError("bad", raw_text="{", meta={"mode": "hybrid"}), "InvalidModelOutputError: bad",
     {"mode": "hybrid", "rawText": "{"}),
    (extraction.ModelCallError("gave up", attempts=6), "ModelCallError: gave up", {"attempts": 6}),
    (extraction.UnsupportedImageError("not an image"), "UnsupportedImageError: not an image", None),
])
def test_errors_after_ocr_fail_the_run(monkeypatch, error, message, raw_output):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("app.adapters.hybrid_extraction.extract_menu_hybrid", fail)
    with pytest.raises(ExtractionError) as caught:
        HybridMenuExtractor(SETTINGS, CLOVA).extract(b"x", "image/jpeg", None)
    assert str(caught.value) == message and caught.value.raw_output == raw_output


def test_items_rejected_by_the_adapter_keep_meta(monkeypatch):
    bad = {"items": [{"itemOrder": 1, "rawText": "x", "lineType": "drink", "options": []}], "meta": {"mode": "hybrid"}}
    monkeypatch.setattr("app.adapters.hybrid_extraction.extract_menu_hybrid", lambda *a, **k: bad)
    with pytest.raises(ExtractionError, match="lineType") as caught:
        HybridMenuExtractor(SETTINGS, CLOVA).extract(b"x", "image/jpeg", None)
    assert caught.value.raw_output == {"mode": "hybrid"}


# ---- deps ----


@pytest.fixture
def env(monkeypatch):
    for name in ("MENU_EXTRACTOR", "EXTRACTION_MODE", "GEMINI_API_KEY", "EXTRACTION_MODEL", "EXTRACTION_THINKING_LEVEL",
                 "CLOVA_OCR_INVOKE_URL", "CLOVA_OCR_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MENU_EXTRACTOR", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key")
    monkeypatch.setenv("EXTRACTION_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("EXTRACTION_THINKING_LEVEL", "medium")
    deps.get_menu_extractor.cache_clear()
    yield monkeypatch
    deps.get_menu_extractor.cache_clear()


def test_gemini_only_is_the_default_mode(env):
    assert type(deps.get_menu_extractor()) is GeminiMenuExtractor


def test_hybrid_mode_is_selected(env):
    env.setenv("EXTRACTION_MODE", "hybrid")
    env.setenv("CLOVA_OCR_INVOKE_URL", "https://ocr.example.test/general")
    env.setenv("CLOVA_OCR_SECRET", "clova-secret")
    assert isinstance(deps.get_menu_extractor(), HybridMenuExtractor)


def test_hybrid_mode_without_clova_settings_fails_at_start(env):
    env.setenv("EXTRACTION_MODE", "hybrid")
    with pytest.raises(RuntimeError, match="EXTRACTION_MODE=hybrid is not configured: .*CLOVA_OCR_INVOKE_URL") as caught:
        deps.get_menu_extractor()
    assert "secret-test-key" not in str(caught.value)


def test_unknown_mode_lists_the_choices(env):
    env.setenv("EXTRACTION_MODE", "ocr")
    with pytest.raises(RuntimeError, match="supported: gemini, hybrid"):
        deps.get_menu_extractor()
