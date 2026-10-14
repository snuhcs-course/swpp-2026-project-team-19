# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, P12). Reviewed by Jinwoo Park.
"""Unit tests on a synthetic CLOVA V2 response fixture. No network, except
test_live_clova_call, which runs only when CLOVA keys are in the environment / .env."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image, ImageDraw

import clova
import lines
import parse
import recall

FIXTURE = json.loads((Path(__file__).with_name("fixtures") / "clova_v2_sample.json").read_text(encoding="utf-8"))
SECRET = "test-secret-do-not-log"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTTLEMAP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLOVA_OCR_INVOKE_URL", "https://ocr.example.test/custom/v1/1/abc/general")
    monkeypatch.setenv("CLOVA_OCR_SECRET", SECRET)
    return tmp_path


def photo(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1000, 400), "white").save(path)
    return path


# ---------- lines ----------

def test_lines_follow_linebreak_and_split_wide_gaps():
    texts = [line.text for line in lines.build_lines(FIXTURE)]
    assert texts == [
        "WHISKY",
        "Glass", "Bottle",                         # 80 px gap > 2.5 x 30 px height
        "글렌그란트 18년 Glen Grant 18Y", "2.8 / 57",  # name and price columns split
        "울프번(Wolfburn)",
        "노스랜드", "19.0",
        "17,000 ₩17,000 12년",                      # out-of-order field: no negative-gap split
    ]


def test_no_split_when_gap_factor_zero():
    texts = [line.text for line in lines.build_lines(FIXTURE, gap_factor=0)]
    assert "글렌그란트 18년 Glen Grant 18Y 2.8 / 57" in texts


def test_format_lines_scales_boxes_to_1000():
    out = lines.format_lines(lines.build_lines(FIXTURE), (1000, 400))
    first = out.splitlines()[0]
    assert first == "L001 [100,50,260,150] WHISKY"


def test_image_size_prefers_converted_info_then_fallback():
    assert lines.image_size(FIXTURE, (1000, 400)) == (1000, 400)
    resp = {"images": [{**FIXTURE["images"][0], "convertedImageInfo": {"width": 50, "height": 70}}]}
    assert lines.image_size(resp, (1000, 400)) == (50, 70)


def test_format_tables():
    out = lines.format_tables(FIXTURE).splitlines()
    assert out == ["T1 r0 c0: 글렌그란트 18년", "T1 r0 c1 (span 1x2): 2.8"]
    assert lines.format_tables({"images": [{"fields": []}]}) == ""


# ---------- recall ----------

def gt(name, price=10000, unit="glass", note=None):
    return {"raw_name": name, "price_krw": price, "pour_ml": None, "unit": unit, "note": note}


def test_name_candidates_split_tokens_and_slash():
    assert recall.name_candidates("글렌그란트 18년 / Glen Grant 18Y") == [
        ["글렌그란트", "18년", "glen", "grant", "18y"], ["글렌그란트", "18년"], ["glen", "grant", "18y"]]
    assert recall.name_candidates("울프번(Wolfburn) 노스랜드") == [["울프번", "wolfburn", "노스랜드"]]


def test_substring_distance():
    assert recall.substring_distance("글랜그란트", "xx글렌그란트yy") == 1
    assert recall.substring_distance("abc", "zzabczz") == 0
    assert recall.substring_distance("abc", "zzz") == 3


def test_name_recall_exact_approx_one_line():
    text, tokens = recall.ocr_inputs(FIXTURE)
    items = [gt("글렌그란트 18년 / Glen Grant 18Y"),  # exact, one line
             gt("울프번(Wolfburn) 노스랜드"),         # exact, but title on another line
             gt("글랜그란트 18년"),                    # one-letter misread -> approx only
             gt("글렌그란트 21년"),                    # digit differs -> not found
             gt("크라이넬리시 14년")]                  # absent
    r = recall.recall_photo(items, text, [], "p")
    assert (r["name_exact"], r["name_approx"], r["name_one_line"]) == (2, 3, 1)
    assert r["missed_names"] == ["글렌그란트 21년", "크라이넬리시 14년"]


def test_short_token_needs_exact_match():
    assert recall.Text(["abd"]).name_found("abc", approx=True)        # 3 chars: 1 edit allowed
    assert not recall.Text(["abd"]).name_found("abc", approx=False)
    assert not recall.Text(["ab"]).name_found("ac", approx=True)      # 2 chars: exact only
    assert not recall.Text(["12년"]).name_found("13년", approx=True)  # digits must be exact


def test_price_values():
    assert recall.price_values("17,000") == [{17000}]
    assert recall.price_values("₩17,000") == [{17000}]
    assert recall.price_values("2.8") == [{2800, 28000}]
    assert recall.price_values("2.8/57") == [{2800, 28000}, {57000, 570000}]
    assert recall.price_values("38000원") == [{38000}]
    assert recall.price_values("12년") == []
    assert recall.price_values("700ml") == []
    assert recall.price_values("46%") == []


def test_price_recall_is_multiset():
    text, tokens = recall.ocr_inputs(FIXTURE)
    items = [gt("a", 28000), gt("a", 570000, "bottle"), gt("b", 19000),
             gt("c", 17000), gt("d", 17000), gt("e", 17000),   # only two 17,000 on the menu
             gt("f", 5000, note="흐림"), gt("g", None)]          # not price-checked
    r = recall.recall_photo(items, text, tokens, "p")
    assert (r["n_priced"], r["price_found"]) == (6, 5)


def test_e1_inputs_use_names_and_prices():
    text, tokens = recall.e1_inputs([{"raw_name": "글렌그란트 18년", "price_krw": 28000},
                                     {"raw_name": "노스랜드", "price_krw": None}])
    r = recall.recall_photo([gt("글렌그란트 18년", 28000), gt("울프번 노스랜드", 19000)], text, tokens)
    assert (r["name_exact"], r["price_found"]) == (1, 1)


# ---------- clova ----------

def test_build_request_v2_shape():
    body = clova.build_request(b"abc", "png", "x", table=True)
    assert body["version"] == "V2" and body["lang"] == "ko" and body["enableTableDetection"] is True
    assert body["images"] == [{"format": "png", "name": "x", "data": "YWJj"}]
    assert isinstance(body["timestamp"], int)


def test_credentials_appends_general(monkeypatch, data_dir):
    monkeypatch.setenv("CLOVA_OCR_INVOKE_URL", "https://ocr.example.test/custom/v1/1/abc/")
    assert clova.credentials()[0] == "https://ocr.example.test/custom/v1/1/abc/general"


def test_ocr_photo_sends_secret_header_caches_and_never_stores_secret(data_dir):
    src = photo(data_dir / "eval_photos" / "m1.png")
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        return httpx.Response(200, json=FIXTURE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    record, cached = clova.ocr_photo(src, "on", client)
    assert not cached and len(seen) == 1
    req = seen[0]
    assert req.headers["X-OCR-SECRET"] == SECRET
    assert json.loads(req.content)["enableTableDetection"] is True
    meta = record["meta"]
    assert (meta["n_fields"], meta["n_tables"], meta["infer_result"]) == (17, 1, "SUCCESS")
    assert meta["latency_ms"] >= 0
    path = clova.cache_path("m1", "on")
    assert path.exists() and SECRET not in path.read_text(encoding="utf-8")
    assert "example.test" not in path.read_text(encoding="utf-8")
    # second call comes from the cache
    record2, cached2 = clova.ocr_photo(src, "on", client)
    assert cached2 and len(seen) == 1 and record2["response"] == FIXTURE


def test_long_side_8000_is_downscaled_before_sending(data_dir):
    src = data_dir / "eval_photos" / "big.png"
    src.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8000, 2000), "white").save(src)
    sent = []

    def handler(request):
        sent.append(json.loads(request.content)["images"][0])
        return httpx.Response(200, json=FIXTURE)

    _, meta = clova.call_ocr(src, False, httpx.Client(transport=httpx.MockTransport(handler)))
    assert meta["resized"] and meta["sent_size"] == [7999, 2000]
    assert meta["sent_image"] == "big.jpg" and sent[0]["format"] == "jpg"
    small = photo(data_dir / "eval_photos" / "small.png")  # 1000 px: sent as is
    _, meta2 = clova.call_ocr(small, False, httpx.Client(transport=httpx.MockTransport(handler)))
    assert not meta2["resized"] and meta2["sent_size"] == [1000, 400] and sent[1]["format"] == "png"


def test_retry_on_500_then_success(data_dir, monkeypatch):
    monkeypatch.setattr(clova.time, "sleep", lambda s: None)
    src = photo(data_dir / "eval_photos" / "m2.png")
    codes = iter([500, 200])
    client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(next(codes), json=FIXTURE)))
    _, meta = clova.call_ocr(src, False, client)
    assert meta["attempts"] == 2


def test_table_disabled_error_code(data_dir):
    src = photo(data_dir / "eval_photos" / "m3.png")
    client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"code": "0028", "message": "Table detection disabled"})))
    with pytest.raises(clova.ClovaError) as exc:
        clova.call_ocr(src, True, client)
    assert exc.value.code == "0028"
    assert SECRET not in str(exc.value)


# ---------- parse ----------

def cache_fixture(data_dir, stem="m4"):
    src = photo(data_dir / "eval_photos" / f"{stem}.png")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=FIXTURE)))
    clova.ocr_photo(src, "off", client)
    return src


def test_ocr_user_text_from_cache(data_dir):
    cache_fixture(data_dir)
    text, meta = parse.ocr_user_text("m4")
    assert "<ocr_lines>" in text and "L001 [100,50,260,150] WHISKY" in text
    assert "<ocr_tables>" not in text
    assert meta["n_lines"] == 9 and meta["ocr_variant"] == "off"
    with pytest.raises(FileNotFoundError):
        parse.ocr_user_text("m4", tables=True)


def test_call_parse_with_fake_client():
    sent = {}

    class FakeInteractions:
        def create(self, **request):
            sent.update(request)
            return SimpleNamespace(
                output_text='{"items": [{"raw_name": "노스랜드", "price_krw": 19000, "pour_ml": null, "unit": "glass"}]}',
                status="completed",
                usage=SimpleNamespace(total_input_tokens=10, total_output_tokens=5,
                                      total_thought_tokens=3, total_tokens=18),
                model_dump=lambda **kw: {"status": "completed"})

    rec = parse.call_parse("USER", "SYSTEM", SimpleNamespace(interactions=FakeInteractions()))
    assert sent["model"] == "gemini-3.5-flash-lite"
    assert sent["generation_config"] == {"thinking_level": "medium"}
    assert sent["input"] == [{"type": "text", "text": "USER"}]  # text only, no image
    assert rec["output"]["items"][0]["price_krw"] == 19000 and rec["parse_error"] is None


def test_prompt_has_no_eval_photo_content():
    prompt = parse.prompt_path("v1").read_text(encoding="utf-8")
    for word in ("미라보", "Beck", "포레스트", "복춘", "서로상", "크라이넬리시", "Balvenie", "Macallan"):
        assert word not in prompt


# ---------- live (only with keys) ----------

def _live_keys():
    from dotenv import dotenv_values
    env = {**dotenv_values(clova.REPO_ROOT / ".env"), **os.environ}
    return env.get("CLOVA_OCR_INVOKE_URL") and env.get("CLOVA_OCR_SECRET")


@pytest.mark.skipif(not _live_keys(), reason="CLOVA keys not set")
def test_live_clova_call(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTTLEMAP_DATA_DIR", str(tmp_path))
    img = tmp_path / "live.png"
    im = Image.new("RGB", (600, 200), "white")
    ImageDraw.Draw(im).text((20, 80), "GLEN GRANT 18 28000", fill="black")
    im.save(img)
    raw, meta = clova.call_ocr(img, table=False)
    assert meta["infer_result"] == "SUCCESS"
    assert "fields" in raw["images"][0]
