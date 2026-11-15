"""The UAT input run (I4-P30, scripts/run_uat_inputs.py): the six inputs, what a record holds,
every failure reason, and that a second run keeps the good results.

Gemini is a scripted fake and CLOVA a fake call_ocr, so nothing here calls an API. The real
bars' photos are not in the repository; the tests run them only as missing or changed files.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import extraction
from app.adapters.hybrid_extraction import HybridMenuExtractor
from app.adapters.pdf_guards import PdfGuards
from app.extraction import clova, gemini, hybrid, pdf
from scripts import run_uat_inputs as uat

REPO = Path(__file__).resolve().parents[2]
PDFS = Path(__file__).resolve().parent / "fixtures" / "pdf"
SETTINGS = extraction.ExtractionSettings(api_key="secret-test-key", model="gemini-3.5-flash-lite",
                                         thinking_level="medium", max_attempts=2)
CLOVA = clova.ClovaSettings(invoke_url="https://ocr.example.test/custom/v1/1/abc/general", secret="clova-secret")
INPUTS = {entry["id"]: entry for entry in uat.load_manifest()}


def design_page() -> pdf.PdfPage:
    [page] = pdf.read_pdf((PDFS / "text_menu_design.pdf").read_bytes())
    return page


def answer(rows: list[tuple[str, int | None, str]]) -> str:
    """A model answer for the design menu's lines: (name, price, unit) with the line ids of the name."""
    lines = {row["text"]: row["id"] for row in clova.ocr_lines_table(
        clova.build_lines(pdf.clova_response(design_page())), (1, 1))}
    return json.dumps({"items": [
        {"raw_name": name, "price_krw": price, "pour_ml": 30 if unit == "glass" else None, "unit": unit,
         "source_lines": {"name": [lines[name]], "price": []}} for name, price, unit in rows]})


DESIGN = answer([
    ("글렌피딕 12년", 15000, "glass"), ("글렌피딕 12년", 190000, "bottle"),
    ("발베니 12년 더블우드", 22000, "glass"), ("발베니 12년 더블우드", 280000, "bottle"),
    ("탈리스커 10년", 16000, "glass"),
    ("라가불린 16년", 26000, "glass"), ("라가불린 16년", 340000, "bottle"),
    ("메이커스 마크", 11000, "glass"), ("메이커스 마크", 130000, "bottle"),
    ("와일드터키 101", 12000, "glass"),
])
ONE = answer([("글렌피딕 12년", 15000, "glass")])


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    monkeypatch.setattr(clova, "sleep", lambda s: None)
    monkeypatch.setattr(gemini, "sleep", lambda s: None)


@pytest.fixture
def model(monkeypatch):
    """A scripted Gemini (text to answer or an exception to raise per call, then ONE) and a CLOVA
    that answers every picture with the design menu's lines."""

    class Model:
        def __init__(self):
            self.script, self.calls, self.ocr_calls = [], 0, 0

        def create(self, **request):
            self.calls += 1
            step = self.script.pop(0) if self.script else ONE
            if isinstance(step, Exception):
                raise step
            usage = SimpleNamespace(total_input_tokens=1, total_output_tokens=1, total_thought_tokens=1, total_tokens=3)
            return SimpleNamespace(output_text=step, status="completed", usage=usage)

    fake = Model()
    real_call_ocr = hybrid.call_ocr

    def call_ocr(settings, image, mime_type, client=None):
        if client is not None:  # a text page: its lines come from the PDF, through the real code
            return real_call_ocr(settings, image, mime_type, client)
        fake.ocr_calls += 1
        page = design_page()
        return {"response": pdf.clova_response(page), "sentSize": [page.width, page.height], "latencyMs": 700,
                "attempts": 1}

    monkeypatch.setattr(gemini, "make_client", lambda settings: SimpleNamespace(interactions=fake))
    monkeypatch.setattr(hybrid, "call_ocr", call_ocr)
    return fake


def make_hybrid() -> HybridMenuExtractor:
    return HybridMenuExtractor(SETTINGS, CLOVA, prompt="v1")


def run(inputs, out, data_dir, **kwargs):
    log: list[str] = []
    records = uat.run_all(inputs, out, data_dir, make_hybrid, PdfGuards(), log=log.append, **kwargs)
    return records, log


# ---- the six inputs ----


def test_the_manifest_lists_three_photos_and_three_pdfs_with_their_uat_use():
    assert [entry["kind"] for entry in INPUTS.values()] == ["photo"] * 3 + ["pdf"] * 3
    assert len(INPUTS) == 6 and all(entry["uat"] for entry in INPUTS.values())


@pytest.mark.parametrize("entry", [entry for entry in INPUTS.values() if entry["source"] == "repo"],
                         ids=lambda entry: entry["id"])
def test_an_input_in_the_repository_is_the_listed_file_and_has_expected_lines(entry):
    assert hashlib.sha256((REPO / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
    rows = uat.expected_rows(entry)
    assert rows and all(set(row) == {"name", "price_krw"} for row in rows)


@pytest.mark.parametrize("entry", [entry for entry in INPUTS.values() if entry["source"] == "data"],
                         ids=lambda entry: entry["id"])
def test_a_real_bar_photo_is_not_in_the_repository_and_takes_its_expected_lines_from_its_fixture(entry):
    assert not (REPO / entry["path"]).exists()
    fixture = json.loads((REPO / entry["expect_fixture"]).read_text(encoding="utf-8"))
    assert fixture["photo"]["sha256"] == entry["sha256"] and entry["path"].endswith(fixture["photo"]["file"])
    rows = uat.expected_rows(entry)
    whisky = [row for row in fixture["expected_items"] if row["gold"] != "non_whisky"]
    assert len(rows) == len(whisky) > 0 and rows[0] == {"name": whisky[0]["raw_name"],
                                                         "price_krw": whisky[0]["price_krw"]}


def test_the_manifest_is_checked(tmp_path):
    def manifest(inputs):
        path = tmp_path / "inputs.json"
        path.write_text(json.dumps({"inputs": inputs}), encoding="utf-8")
        return path

    entry = {"id": "a", "kind": "photo", "source": "repo"}
    with pytest.raises(ValueError, match="ids must be unique"):
        uat.load_manifest(manifest([entry, entry]))
    with pytest.raises(ValueError, match="a needs kind photo|pdf"):
        uat.load_manifest(manifest([{**entry, "kind": "video"}]))
    with pytest.raises(ValueError, match="source repo|data"):
        uat.load_manifest(manifest([{**entry, "source": "web"}]))
    assert uat.expected_rows(entry) == []


# ---- expected lines ----


def test_expected_lines_are_found_by_name_and_price():
    items = [{"name": "글렌피딕 12 년", "prices": [{"priceKrw": 15000}, {"priceKrw": 190000}]},
             {"name": "라가불린 16년", "prices": []}, {"name": "탈리스커 10년", "prices": [{"priceKrw": 99}]}]
    expected = [{"name": "글렌피딕 12년", "price_krw": 15000}, {"name": "글렌피딕 12년", "price_krw": 190000},
                {"name": "라가불린 16년", "price_krw": None}, {"name": "탈리스커 10년", "price_krw": 16000},
                {"name": "맥캘란 18년", "price_krw": 45000}]

    assert uat.found_expected(expected, items) == {"expected": 5, "found": 3, "missing": expected[3:]}
    assert uat.found_expected([], items) == {"expected": 0, "found": 0, "missing": []}


# ---- a run ----


def test_a_text_pdf_gives_its_names_prices_latency_and_expected_lines(tmp_path, model):
    model.script = [DESIGN]

    [record], log = run([INPUTS["pdf-text-design"]], tmp_path, tmp_path)

    assert record["failure"] is None and model.calls == 1 and model.ocr_calls == 0
    assert record["items"][0] == {"page": 1, "name": "글렌피딕 12년", "lineType": "product", "prices": [
        {"priceKrw": 15000, "pourMl": 30, "label": "잔"}, {"priceKrw": 190000, "pourMl": None, "label": "병"}]}
    assert record["expected"] == {"expected": 10, "found": 10, "missing": []}
    assert record["pages"] == [{"page": 1, "kind": "text", "textLayer": "used", "items": 6, "failure": None,
                                "attempts": 1, "modelMs": record["modelMs"], "ocrMs": None}]
    assert record["modelMs"] is not None and record["wallMs"] >= 0 and record["attempts"] == 1
    assert (record["model"], record["sha256"]) == ("gemini-3.5-flash-lite", INPUTS["pdf-text-design"]["sha256"])
    assert log == [f"pdf-text-design: 6 items in {record['wallMs']} ms"]
    assert json.loads((tmp_path / "pdf-text-design.json").read_text(encoding="utf-8")) == record


def test_a_photo_and_a_scanned_pdf_go_through_ocr_and_report_its_latency(tmp_path, model):
    records, _ = run([INPUTS["photo-review-menu"], INPUTS["pdf-scanned"]], tmp_path, tmp_path)

    photo, scanned = records
    assert photo["failure"] is None and photo["ocrMs"] == 700 and "pages" not in photo and photo["ocrFallback"] is None
    assert photo["items"] == [{"name": "글렌피딕 12년", "lineType": "product",
                               "prices": [{"priceKrw": 15000, "pourMl": 30, "label": "잔"}]}]
    assert photo["expected"]["expected"] == 8 and photo["expected"]["found"] == 1
    assert [page["kind"] for page in scanned["pages"]] == ["scanned", "scanned"] and scanned["ocrMs"] == 1400
    assert scanned["attempts"] == 2 and [item["page"] for item in scanned["items"]] == [1, 2]
    assert model.calls == 3 and model.ocr_calls == 3


def test_a_photo_read_without_ocr_says_so(tmp_path, model, monkeypatch):
    def down(*args, **kwargs):
        raise clova.ClovaOCRError("CLOVA OCR failed after 3 attempt(s): HTTP 500")

    monkeypatch.setattr(hybrid, "call_ocr", down)
    model.script = [json.dumps({"items": [{"raw_name": "글렌피딕 12년", "price_krw": 15000, "pour_ml": 30,
                                           "unit": "glass"}]})]

    [record], _ = run([INPUTS["photo-review-menu"]], tmp_path, tmp_path)

    assert record["failure"] is None and record["ocrFallback"] == "CLOVA OCR failed after 3 attempt(s): HTTP 500"
    assert "OCR failed and the model read the photo alone" in uat.markdown([record])


# ---- failure reasons ----


def test_a_real_bar_photo_that_is_not_there_is_a_failure_and_nothing_is_sent(tmp_path, model):
    [record], log = run([INPUTS["photo-seorosang"]], tmp_path / "out", tmp_path / "data")

    assert record["failure"]["code"] == "input_missing" and "nothing was sent" in record["failure"]["message"]
    assert (record["items"], model.calls, model.ocr_calls) == ([], 0, 0)
    assert record["expected"]["found"] == 0 and record["expected"]["expected"] > 0
    assert log[0].startswith("photo-seorosang: FAILED input_missing")


def test_a_file_that_is_not_the_listed_one_is_a_failure_and_nothing_is_sent(tmp_path, model):
    entry = INPUTS["photo-bokchun"]
    (tmp_path / "eval_photos").mkdir()
    (tmp_path / entry["path"]).write_bytes(b"another photo")

    [record], _ = run([entry], tmp_path / "out", tmp_path)

    assert record["failure"]["code"] == "input_changed" and (model.calls, model.ocr_calls) == (0, 0)


@pytest.mark.parametrize("script, code, message", [
    ([httpx.ReadTimeout("read timed out")] * 2, "model_timeout", "gave up after 2 attempts"),
    (["{oops"], "invalid_output", "not valid hybrid v1 output"),
])
def test_a_failed_model_call_is_the_photo_failure_reason(tmp_path, model, script, code, message):
    model.script = list(script)

    [record], _ = run([INPUTS["photo-review-menu"]], tmp_path, tmp_path)

    assert record["failure"]["code"] == code and message in record["failure"]["message"]
    assert record["items"] == [] and record["attempts"] == len(script)


def test_a_failed_page_is_the_pdf_failure_reason_and_the_other_page_is_still_reported(tmp_path, model):
    model.script = ["{oops"]

    [record], _ = run([INPUTS["pdf-text-office"]], tmp_path, tmp_path)

    assert record["failure"] == {"code": "pages_failed",
                                 "message": "1 of 2 pages failed (page 1: invalid_output)"}
    assert [(page["page"], page["items"], bool(page["failure"])) for page in record["pages"]] == [(1, 0, True),
                                                                                                 (2, 1, False)]
    assert [item["page"] for item in record["items"]] == [2]


def test_a_stopped_pdf_says_why(tmp_path, model):
    model.script = ["{oops"] * 2

    record = uat.run_pdf((PDFS / "text_menu_office.pdf").read_bytes(), uat.PdfMenuExtractor(make_hybrid()),
                         PdfGuards(failed_pages=1))

    assert record["failure"]["message"] == ("2 of 2 pages failed (page 1: invalid_output, page 2: not_attempted); "
                                            "stopped: too_many_failed_pages")
    assert (record["attempts"], record["modelMs"], record["ocrMs"]) == (1, record["pages"][0]["modelMs"], None)


def test_a_pdf_that_cannot_be_read_is_a_failure_with_its_code(tmp_path, model):
    data = (PDFS / "encrypted.pdf").read_bytes()
    entry = {"id": "pdf-locked", "kind": "pdf", "uat": "x", "source": "repo",
             "path": "backend/tests/fixtures/pdf/encrypted.pdf", "sha256": hashlib.sha256(data).hexdigest()}

    [record], _ = run([entry], tmp_path, tmp_path)

    assert record["failure"] == {"code": "pdf_encrypted", "message": "the PDF is protected with a password"}
    assert (record["pages"], record["attempts"], model.calls) == ([], 0, 0)


# ---- running again ----


def test_a_second_run_keeps_good_results_and_runs_failed_ones_again(tmp_path, model):
    inputs = [INPUTS["pdf-text-design"], INPUTS["pdf-text-office"]]
    model.script = [ONE, "{oops"]
    first, _ = run(inputs, tmp_path, tmp_path)
    assert [record["failure"] is None for record in first] == [True, False] and model.calls == 3

    second, log = run(inputs, tmp_path, tmp_path)

    assert log[0] == "pdf-text-design: kept (1 items)" and second[0] == first[0]
    assert second[1]["failure"] is None and model.calls == 3 + 2  # only the failed PDF's two pages

    third, log = run(inputs, tmp_path, tmp_path)
    assert log == ["pdf-text-design: kept (1 items)", "pdf-text-office: kept (2 items)"] and model.calls == 5

    run(inputs, tmp_path, tmp_path, force=True)
    assert model.calls == 5 + 3


def test_a_kept_result_of_another_file_is_run_again_and_settings_are_read_only_when_needed(tmp_path, model):
    entry = INPUTS["pdf-text-design"]
    run([entry], tmp_path, tmp_path)
    assert model.calls == 1

    def no_settings():
        raise AssertionError("the settings were read")

    assert len(uat.run_all([entry], tmp_path, tmp_path, no_settings, PdfGuards(), log=lambda line: None)) == 1
    record = json.loads((tmp_path / "pdf-text-design.json").read_text(encoding="utf-8"))
    (tmp_path / "pdf-text-design.json").write_text(json.dumps({**record, "sha256": "0" * 64}), encoding="utf-8")
    run([entry], tmp_path, tmp_path)
    assert model.calls == 2


@pytest.mark.parametrize("left_behind", [
    '{"id": "pdf-text-design", "items": [{"name": "글렌',   # a run stopped while writing
    "",
    "[1, 2]",                                               # not a record
    '{"id": "pdf-text-design", "failure": null}',           # a record without its items
])
def test_a_record_a_stopped_run_left_unusable_is_run_again(tmp_path, model, left_behind):
    entry = INPUTS["pdf-text-design"]
    (tmp_path / "pdf-text-design.json").write_text(left_behind, encoding="utf-8")

    [record], log = run([entry], tmp_path, tmp_path)

    assert record["failure"] is None and model.calls == 1 and "kept" not in log[0]
    assert json.loads((tmp_path / "pdf-text-design.json").read_text(encoding="utf-8")) == record
    assert sorted(path.name for path in tmp_path.iterdir()) == ["pdf-text-design.json"]  # no part file left


def test_a_record_is_written_whole_or_not_at_all(tmp_path, monkeypatch):
    target = tmp_path / "x.json"
    uat.write_record(target, {"items": [], "failure": None})
    monkeypatch.setattr(uat.os, "replace", lambda source, destination: (_ for _ in ()).throw(OSError("stopped")))

    with pytest.raises(OSError):
        uat.write_record(target, {"items": [1], "failure": None})

    assert uat.read_record(target) == {"items": [], "failure": None}  # the earlier record is intact
    assert uat.read_record(tmp_path / "none.json") is None


# ---- the report and the command ----


def test_the_report_has_the_table_the_items_and_the_missing_lines(tmp_path, model):
    model.script = [DESIGN, "{oops"]
    records, _ = run([INPUTS["pdf-text-design"], INPUTS["pdf-text-office"], INPUTS["photo-seorosang"]], tmp_path,
                     tmp_path)

    uat.write_report(records, tmp_path)

    text = (tmp_path / "uat_inputs.md").read_text(encoding="utf-8")
    assert "3 inputs, 1 without a failure." in text
    assert "| pdf-text-design | pdf | 6 | 10/10 |" in text and "| 1 | - |" in text
    assert "pages_failed: 1 of 2 pages failed (page 1: invalid_output) |" in text
    assert "| photo-seorosang | photo | 0 | 0/" in text and "input_missing" in text
    assert "| 글렌피딕 12년 | 15,000 (30ml), 190,000 (병) |" in text
    assert "- Page 1 (text, text layer used): 0 items" in text and "failed invalid_output" in text
    assert "Expected lines not found: 아드벡 10년 17,000;" in text
    summary = json.loads((tmp_path / "uat_inputs.json").read_text(encoding="utf-8"))["summary"]
    assert summary["inputs"] == 3 and summary["failed"] == ["pdf-text-office", "photo-seorosang"]
    assert summary["items"] == 7 and summary["expectedFound"] == 10


def test_prices_and_times_are_written_for_reading():
    assert uat._price({"priceKrw": None, "pourMl": None, "label": None}) == "no price"
    assert uat._price({"priceKrw": 9000, "pourMl": None, "label": None}) == "9,000"
    assert (uat._ms(None), uat._ms(1234)) == ("-", "1.2 s")
    item = {"name": "라가불린 16년", "prices": []}
    record = {"id": "x", "kind": "photo", "uat": "u", "file": "f", "items": [item], "failure": None, "wallMs": 5,
              "expected": {"expected": 1, "found": 0, "missing": [{"name": "라가불린 16년", "price_krw": None}]}}
    text = uat.markdown([record])
    assert "| 라가불린 16년 | no price |" in text
    assert "Expected lines not found: 라가불린 16년 (no price)" in text
    assert "| x | photo | 1 | 0/1 | - | - | 0.0 s | - | - |" in text


def test_the_command_runs_the_chosen_inputs_and_exits_1_when_one_failed(tmp_path, model, capsys):
    out = tmp_path / "out"
    assert uat.main(["--out", str(out), "--only", "pdf-text-design", "--only", "pdf-scanned"],
                    hybrid_factory=make_hybrid) == 0
    assert sorted(path.name for path in out.iterdir()) == [
        "pdf-scanned.json", "pdf-text-design.json", "uat_inputs.json", "uat_inputs.md"]
    assert "2 of 2 inputs without a failure" in capsys.readouterr().out

    assert uat.main(["--out", str(out), "--data-dir", str(tmp_path / "none")], hybrid_factory=make_hybrid) == 1
    assert "4 of 6 inputs without a failure" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        uat.main(["--out", str(out), "--only", "nope"], hybrid_factory=make_hybrid)
    assert "unknown input id: nope" in capsys.readouterr().err


def test_missing_settings_stop_the_command_before_anything_is_sent(tmp_path, monkeypatch, capsys):
    for name in ("GEMINI_API_KEY", "EXTRACTION_MODEL", "EXTRACTION_THINKING_LEVEL"):
        monkeypatch.delenv(name, raising=False)

    assert uat.main(["--out", str(tmp_path), "--only", "pdf-text-design"]) == 2
    assert "settings: Missing required extraction environment variables: GEMINI_API_KEY" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_the_server_extractor_is_built_from_the_environment_with_fewer_attempts(monkeypatch):
    for name, value in (("GEMINI_API_KEY", "k"), ("EXTRACTION_MODEL", "gemini-3.5-flash-lite"),
                        ("EXTRACTION_THINKING_LEVEL", "medium"), ("CLOVA_OCR_INVOKE_URL", CLOVA.invoke_url),
                        ("CLOVA_OCR_SECRET", "s"), ("EXTRACTION_HYBRID_PROMPT", "v2")):
        monkeypatch.setenv(name, value)

    built = uat.server_hybrid()

    assert (built.settings.max_attempts, built.prompt, built.clova.secret) == (2, "v2", "s")
    assert uat.server_hybrid(4).settings.max_attempts == 4
