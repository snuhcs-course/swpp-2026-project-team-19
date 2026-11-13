"""run_extraction.py with a made-up photo, a made-up OCR cache and a fake Gemini client."""

import hashlib
import io
import json
from types import SimpleNamespace

import pytest
import regression as reg
import run_extraction as runner
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
ANSWERS = {"v1": {"items": [WHISKY]},
           "v2": {"items": [{**WHISKY, "category": "whisky"},
                            {**WHISKY, "raw_name": "모히토", "price_krw": 12000, "category": "cocktail"}]}}


class Interactions:
    def __init__(self, text, error=None):
        self.text, self.error, self.calls = text, error, 0

    def create(self, **request):
        self.calls += 1
        if self.error:
            raise self.error
        usage = SimpleNamespace(total_input_tokens=5000, total_output_tokens=300, total_thought_tokens=0, total_tokens=5300)
        return SimpleNamespace(output_text=self.text, status="completed", usage=usage)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """A data dir with two photos and their OCR caches; returns (fixtures, data_dir, set_answer)."""
    fixtures = []
    for n in (1, 2):
        out = io.BytesIO()
        Image.new("RGB", (1000, 2000), (250, 250, 250 - n)).save(out, format="JPEG")
        photo = tmp_path / "eval_photos" / f"00{n}_bar_01.jpg"
        photo.parent.mkdir(exist_ok=True)
        photo.write_bytes(out.getvalue())
        cache = tmp_path / "ocr_cache" / f"00{n}_bar_01__table-off.json"
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps({"meta": {"sent_sha256": "x"}, "response": OCR}), encoding="utf-8")
        fixtures.append({"photo_id": f"00{n}_바_01", "photo": {
            "file": photo.name, "photo_dir": "eval_photos", "sha256": hashlib.sha256(out.getvalue()).hexdigest()}})
    monkeypatch.setattr(reg, "load_fixtures", lambda: fixtures)
    monkeypatch.setattr(runner, "api_key", lambda: "secret-test-key")
    monkeypatch.setattr(gemini, "sleep", lambda s: None)
    state = SimpleNamespace(client=None)

    def answer(text, error=None):
        state.client = Interactions(text, error)
        monkeypatch.setattr(gemini, "make_client", lambda settings: SimpleNamespace(interactions=state.client))
        return state.client

    return fixtures, tmp_path, answer


def args(tmp_path, prompt, *more):
    return ["--prompt", prompt, "--out", str(tmp_path / "out"), "--data-dir", str(tmp_path), *more]


def test_v2_run_writes_records_that_regression_can_replay(setup, capsys):
    fixtures, tmp_path, answer = setup
    client = answer(json.dumps(ANSWERS["v2"]))
    assert runner.main(args(tmp_path, "v2")) == 0
    record = json.loads((tmp_path / "out" / "001_bar_01_r1.json").read_text(encoding="utf-8"))
    assert record["prompt_version"] == "hybrid-v2" and record["model"] == runner.MODEL and record["run"] == 1
    assert record["output"] == {"items": [{"raw_name": "페른홀로우 12년", "price_krw": 15000, "pour_ml": None, "unit": "glass"}]}
    assert [o["rawText"] for o in record["other_items"]] == ["모히토"] and record["ocr_cache_same_bytes"] is False
    assert [row["id"] for row in record["ocr_lines"]] == ["L001", "L002"]
    assert "secret-test-key" not in json.dumps(record)
    output = reg.server_output(record)
    assert len(output["items"]) == 1 and output["otherItems"][0]["box"] is not None
    # a second command keeps the records and calls nothing
    assert client.calls == 2 and runner.main(args(tmp_path, "v2")) == 0 and client.calls == 2
    assert "kept 001_bar_01_r1.json" in capsys.readouterr().out


def test_v1_run_and_photo_filter(setup):
    fixtures, tmp_path, answer = setup
    answer(json.dumps(ANSWERS["v1"]))
    assert runner.main(args(tmp_path, "v1", "--photos", "002_바_01", "--run", "2")) == 0
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["002_bar_01_r2.json"]
    record = json.loads((tmp_path / "out" / "002_bar_01_r2.json").read_text(encoding="utf-8"))
    assert record["prompt_version"] == "hybrid-v1" and record["other_items"] is None


def test_rejected_answer_is_recorded_and_no_answer_stops(setup, capsys):
    fixtures, tmp_path, answer = setup
    answer("{oops")
    assert runner.main(args(tmp_path, "v2", "--photos", "001_바_01")) == 0
    record = json.loads((tmp_path / "out" / "001_bar_01_r1.json").read_text(encoding="utf-8"))
    assert record["output"] is None and record["raw_text"] == "{oops" and "parse_error" in record
    assert reg.record_output(record) is None
    answer("", error=RuntimeError("bad key secret-test-key"))
    assert runner.main(args(tmp_path, "v2")) == 1
    out = capsys.readouterr().out
    assert "no answer" in out and "secret-test-key" not in out
    assert not (tmp_path / "out" / "002_bar_01_r1.json").exists()


def test_call_cap_and_input_checks(setup, monkeypatch, capsys):
    fixtures, tmp_path, answer = setup
    client = answer(json.dumps(ANSWERS["v2"]))
    assert runner.main(args(tmp_path, "v2", "--max-calls", "1")) == 1 and client.calls == 1
    assert "--max-calls" in capsys.readouterr().out
    (tmp_path / "ocr_cache" / "002_bar_01__table-off.json").unlink()
    with pytest.raises(SystemExit, match="no OCR cache"):
        runner.main(args(tmp_path, "v2"))
    (tmp_path / "eval_photos" / "002_bar_01.jpg").write_bytes(b"other")
    with pytest.raises(SystemExit, match="not the listed photo"):
        runner.main(args(tmp_path, "v2"))
    monkeypatch.setattr(runner, "api_key", lambda: "")
    with pytest.raises(SystemExit, match="GEMINI_API_KEY"):
        runner.main(args(tmp_path, "v2"))


def test_api_key_comes_from_the_repo_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    assert runner.api_key() == ""
    (tmp_path / ".env").write_text("GEMINI_API_KEY= abc \n", encoding="utf-8")
    assert runner.api_key() == "abc"
