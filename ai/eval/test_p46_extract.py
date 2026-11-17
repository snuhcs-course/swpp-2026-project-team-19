"""p46_extract.py with made-up photos, made-up OCR caches and a fake Gemini client."""

import hashlib
import io
import json
from types import SimpleNamespace

import p46_extract as p46
import pytest
from app.extraction import gemini
from PIL import Image

OCR = {"version": "V2", "images": [{"inferResult": "SUCCESS", "fields": [
    {"inferText": "페른홀로우 12년", "lineBreak": False, "boundingPoly": {"vertices": [
        {"x": 100, "y": 200}, {"x": 380, "y": 200}, {"x": 380, "y": 240}, {"x": 100, "y": 240}]}},
    {"inferText": "15,000", "lineBreak": True, "boundingPoly": {"vertices": [
        {"x": 700, "y": 200}, {"x": 800, "y": 200}, {"x": 800, "y": 240}, {"x": 700, "y": 240}]}},
]}]}
WHISKY = {"raw_name": "페른홀로우 12년", "price_krw": 15000, "pour_ml": None, "unit": "glass",
          "source_lines": {"name": ["L001"], "price": ["L002"]}}
ANSWER = json.dumps({"items": [{**WHISKY, "category": "whisky"},
                               {**WHISKY, "raw_name": "모히토", "price_krw": 12000, "category": "cocktail"}]})


class Interactions:
    def __init__(self, fail_after=None):
        self.calls, self.fail_after = 0, fail_after

    def create(self, **request):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("400 bad request")
        usage = SimpleNamespace(total_input_tokens=5000, total_output_tokens=300, total_thought_tokens=0, total_tokens=5300)
        return SimpleNamespace(output_text=ANSWER, status="completed", usage=usage)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """A data dir with two photos, their OCR caches and a photo hash file; returns (argv, client)."""
    listed = []
    for n in (1, 2):
        out = io.BytesIO()
        Image.new("RGB", (1000, 2000), (250, 250, 250 - n)).save(out, format="JPEG")
        photo = tmp_path / p46.PHOTO_DIR / f"00{n}_bar_01.jpg"
        photo.parent.mkdir(exist_ok=True)
        photo.write_bytes(out.getvalue())
        cache = tmp_path / "ocr_cache" / f"00{n}_bar_01__table-off.json"
        cache.parent.mkdir(exist_ok=True)
        sent = p46.ocr_image(*p46.prepare_image(out.getvalue(), "image/jpeg"))[0]
        cache.write_text(json.dumps({"meta": {"sent_sha256": hashlib.sha256(sent).hexdigest()}, "response": OCR}),
                         encoding="utf-8")
        listed.append({"file": photo.name, "photo_id": f"00{n}_바_01", "sha256": hashlib.sha256(out.getvalue()).hexdigest()})
    hashes = tmp_path / "hashes.json"
    hashes.write_text(json.dumps({"photos": listed}, ensure_ascii=False), encoding="utf-8")
    client = Interactions()
    monkeypatch.setattr(p46.rx, "api_key", lambda: "secret-test-key")
    monkeypatch.setattr(gemini, "sleep", lambda s: None)
    monkeypatch.setattr(gemini, "make_client", lambda settings: SimpleNamespace(interactions=client))
    lines = tmp_path / "mixed_lines.json"
    lines.write_text(json.dumps({"reviewed": "tester 2026-11-17", "photos": {}}), encoding="utf-8")
    argv = ["--out", str(tmp_path / "out"), "--data-dir", str(tmp_path), "--hashes", str(hashes), "--no-hashes-sha-check",
            "--mixed-lines", str(lines)]
    return argv, client, tmp_path


def run(argv, *more):
    return p46.main([*argv, *more], sleep=lambda s: None)


def test_the_photo_list_is_the_pinned_i3_list(tmp_path):
    assert len(p46.load_photos()) == 33
    other = tmp_path / "hashes.json"
    other.write_text('{"photos": []}', encoding="utf-8")
    with pytest.raises(SystemExit, match="not the frozen photo list"):
        p46.load_photos(other)


def test_check_calls_nothing_and_writes_nothing(setup, capsys):
    argv, client, tmp_path = setup
    assert run(argv, "--check") == 0
    assert client.calls == 0 and not (tmp_path / "out").exists()
    assert "photos and OCR caches verified: 2; prompt hybrid-v2" in capsys.readouterr().out


def test_runs_write_v2_records_and_a_rerun_keeps_them(setup):
    argv, client, tmp_path = setup
    assert run(argv, "--runs", "1", "2") == 0 and client.calls == 4
    record = json.loads((tmp_path / "out" / "002_bar_01_r2.json").read_text(encoding="utf-8"))
    assert record["prompt_version"] == "hybrid-v2" and record["run"] == 2 and record["photo_id"] == "002_바_01"
    assert record["output"] == {"items": [{"raw_name": "페른홀로우 12년", "price_krw": 15000, "pour_ml": None, "unit": "glass"}]}
    assert [o["rawText"] for o in record["other_items"]] == ["모히토"]
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["configuration"]["prompt_version"] == "hybrid-v2" and manifest["configuration"]["max_attempts"] == 6
    assert manifest["commands"][0]["calls"] == 4 and manifest["commands"][0]["stopped"] is None
    assert "secret-test-key" not in (tmp_path / "out" / "manifest.json").read_text(encoding="utf-8") + json.dumps(record)
    assert run(argv, "--runs", "1", "2", "3") == 0 and client.calls == 6  # only r3 is new
    assert len(json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))["commands"]) == 2


def test_the_call_cap_stops_cleanly_and_the_next_command_continues(setup, capsys):
    argv, client, tmp_path = setup
    assert run(argv, "--runs", "1", "--max-calls", "1") == 1
    assert client.calls == 1 and not (tmp_path / "out" / "002_bar_01_r1.json").exists()
    assert "stopped at --max-calls 1" in capsys.readouterr().out
    assert run(argv, "--runs", "1") == 0 and client.calls == 2


def test_a_call_without_an_answer_stops_and_writes_no_record(setup, capsys):
    argv, client, tmp_path = setup
    client.fail_after = 1
    assert run(argv, "--runs", "1") == 1
    assert (tmp_path / "out" / "001_bar_01_r1.json").exists() and not (tmp_path / "out" / "002_bar_01_r1.json").exists()
    printed = capsys.readouterr().out
    assert "no answer" in printed and "secret-test-key" not in printed
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["commands"][0]["stopped"] == "no answer for 002_바_01 r1"


def test_a_wrong_photo_or_cache_stops_before_any_call(setup, capsys):
    argv, client, tmp_path = setup
    (tmp_path / "ocr_cache" / "002_bar_01__table-off.json").write_text(
        json.dumps({"meta": {"sent_sha256": "0" * 64}, "response": OCR}), encoding="utf-8")
    (tmp_path / p46.PHOTO_DIR / "001_bar_01.jpg").write_bytes(b"another file")
    with pytest.raises(SystemExit, match="STOP: 2 of 2 photos"):
        run(argv)
    printed = capsys.readouterr().out
    assert "is missing or is not the listed photo" in printed and "was not made from this photo" in printed
    assert client.calls == 0


def test_another_configuration_in_the_run_dir_stops(setup, monkeypatch):
    argv, client, tmp_path = setup
    assert run(argv, "--runs", "1") == 0
    monkeypatch.setattr(p46.rx, "THINKING_LEVEL", "low")
    with pytest.raises(SystemExit, match="another configuration \\(thinking_level\\)"):
        run(argv, "--runs", "2")
    assert client.calls == 2


def test_a_run_waits_for_the_review_of_the_non_whisky_lines(setup, capsys):
    argv, client, tmp_path = setup
    (tmp_path / "mixed_lines.json").write_text(json.dumps({"reviewed": None, "photos": {}}), encoding="utf-8")
    assert run(argv, "--check") == 0 and "NOT reviewed yet" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="is not reviewed"):
        run(argv, "--runs", "1")
    assert client.calls == 0 and not (tmp_path / "out").exists()
