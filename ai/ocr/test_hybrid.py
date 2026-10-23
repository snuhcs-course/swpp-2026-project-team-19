"""Unit tests for the hybrid extractor (no network)."""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

import clova
import hybrid
from lines import Line, Word

FIXTURE = json.loads((Path(__file__).with_name("fixtures") / "clova_v2_sample.json").read_text(encoding="utf-8"))


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTTLEMAP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLOVA_OCR_INVOKE_URL", "https://ocr.example.test/custom/v1/1/abc/general")
    monkeypatch.setenv("CLOVA_OCR_SECRET", "test-secret")
    return tmp_path


def cached_photo(data_dir, stem="m4") -> Path:
    src = data_dir / "eval_photos" / f"{stem}.png"
    src.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1000, 400), "white").save(src)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=FIXTURE)))
    clova.ocr_photo(src, "off", client)
    return src


@pytest.mark.parametrize("text", ["18.0", "17,000", "290.000", "2.8 / 57", "₩ 19,000", "3.9 / -", "57", "15000원",
                                  "42.0  16.0"])
def test_price_like_yes(text):
    assert hybrid.price_like(text)


@pytest.mark.parametrize("text", ["30ml", "12년", "2023", "8", "Talisker 10yo", "18년 캐스크 스트랭스", "", "-",
                                  "Glass 20ml / 40ml", "100% 아일라"])
def test_price_like_no(text):
    assert not hybrid.price_like(text)


def line(text, y=0):
    return Line([Word(text, 0, y, 10, y + 10)])


def test_source_check_counts_uncited_price_lines_and_flags():
    lines = [line("울프번"), line("노스랜드"), line("19.0"), line("10년 셰리"), line("24.0")]
    lines += [line(p) for p in ("11.0", "12.0", "13.0", "14.0")]
    items = [{"raw_name": "울프번 노스랜드", "source_lines": {"name": ["L001", "L002"], "price": ["L003"]}},
             {"raw_name": "울프번 10년 셰리", "source_lines": {"name": ["L001", "L004"], "price": ["L999"]}}]
    sc = hybrid.source_check(items, lines)
    assert sc["price_like_lines"] == 6
    assert sc["uncited"] == ["L005", "L006", "L007", "L008", "L009"]
    assert sc["flag_missing"] is True  # 5 >= max(4, 1.2)
    assert sc["invalid_refs"] == ["L999"]
    items[1]["source_lines"]["price"] = ["L005"]
    assert hybrid.source_check(items, lines)["uncited_price_lines"] == 4  # still >= 4
    assert hybrid.source_check(items, lines[:6])["flag_missing"] is False


def test_user_text_uses_p12_line_format(data_dir):
    cached_photo(data_dir)
    lines, size, meta = hybrid.ocr_lines("m4")
    text = hybrid.user_text(lines, size)
    assert text.startswith(hybrid.USER_HEADER)
    assert "L001 [100,50,260,150] WHISKY" in text
    with pytest.raises(FileNotFoundError):
        hybrid.ocr_lines("missing")


def fake_client(sent: dict):
    class FakeInteractions:
        def create(self, **request):
            sent.update(request)
            return SimpleNamespace(
                output_text='{"items": [{"raw_name": "노스랜드", "price_krw": 19000, "pour_ml": null, "unit": "glass", '
                            '"source_lines": {"name": ["L002"], "price": ["L003"]}}]}',
                status="completed",
                usage=SimpleNamespace(total_input_tokens=10, total_output_tokens=5,
                                      total_thought_tokens=3, total_tokens=18),
                model_dump=lambda **kw: {"status": "completed"})
    return SimpleNamespace(interactions=FakeInteractions())


def test_call_hybrid_sends_text_and_image(data_dir):
    src = cached_photo(data_dir)
    sent = {}
    rec = hybrid.call_hybrid(src, "USER", "SYSTEM", hybrid.Budget(1), fake_client(sent))
    assert sent["model"] == "gemini-3.5-flash-lite"
    assert sent["generation_config"] == {"thinking_level": "medium"}
    assert [part["type"] for part in sent["input"]] == ["text", "image"]
    assert sent["input"][0]["text"] == "USER"
    assert "source_lines" in json.dumps(sent["response_format"]["schema"])
    assert rec["output"]["items"][0]["source_lines"] == {"name": ["L002"], "price": ["L003"]}
    assert rec["parse_error"] is None


def test_budget_stops_at_limit(data_dir):
    src = cached_photo(data_dir)
    budget = hybrid.Budget(1)
    hybrid.call_hybrid(src, "USER", "SYSTEM", budget, fake_client({}))
    with pytest.raises(hybrid.CallLimitReached):
        hybrid.call_hybrid(src, "USER", "SYSTEM", budget, fake_client({}))


@pytest.mark.parametrize("version", ["v1"])
def test_prompt_has_no_eval_photo_content(version):
    from score import load_labels, normalize
    prompt = hybrid.prompt_path(version).read_text(encoding="utf-8")
    for word in ("미라보", "Beck", "포레스트", "복춘", "서로상", "크라이넬리시", "Balvenie", "Macallan"):
        assert word not in prompt
    # no val/test label name (normalized, 4+ chars) in the prompt, except the guideline
    # text examples shared with E1's prompt v2 (e.g. 글렌파클라스105 CS)
    flat = normalize(prompt)
    e1 = normalize((hybrid.REPO_ROOT / "ai" / "extract" / "prompt_v2.md").read_text(encoding="utf-8"))
    names = {normalize(i["raw_name"]) for s in ("val", "test", "val_v1_1", "test_v1_1")
             for items in load_labels(s).values() for i in items}
    leaked = sorted(n for n in names if len(n) >= 4 and n in flat and n not in e1)
    assert leaked == []
