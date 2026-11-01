"""p30_extract.py with made-up photos, a fake Gemini client and a fake CLOVA client (no API call,
never the I3 photos or labels)."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import p30_extract as p30
import pytest
from PIL import Image

import score

REPO_ROOT = Path(__file__).resolve().parents[2]
CLOVA_SAMPLE = json.loads((REPO_ROOT / "ai" / "ocr" / "fixtures" / "clova_v2_sample.json").read_text(encoding="utf-8"))
KEY = "AIzaFAKE-gemini-key-0123456789"
SECRET = "fake-clova-secret-9876"
URL = "https://ocr.example.test/custom/v1/1/abcdef/general"
ITEMS = {"items": [
    {"raw_name": "Glenfiddich 12", "price_krw": 18000, "pour_ml": None, "unit": "glass",
     "source_lines": {"name": ["L001"], "price": ["L002"]}},
    {"raw_name": "Glenfiddich 12", "price_krw": 150000, "pour_ml": None, "unit": "bottle",
     "source_lines": {"name": ["L001"], "price": ["L003"]}},
]}


class ApiError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def answer(text=None):
    return SimpleNamespace(status="completed", output_text=json.dumps(ITEMS) if text is None else text,
                           usage=SimpleNamespace(total_input_tokens=100, total_output_tokens=50,
                                                 total_thought_tokens=10, total_tokens=160))


class FakeGemini:
    """interactions.create returns `answer()` or plays `script` (results or exceptions) first."""

    def __init__(self, script=()):
        self.script = list(script)
        self.requests = []
        self.interactions = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        step = self.script.pop(0) if self.script else answer()
        if isinstance(step, Exception):
            raise step
        return step


class FakeClova:
    def __init__(self):
        self.requests = []

    def post(self, url, json=None, headers=None):
        self.requests.append((url, headers))
        return httpx.Response(200, json=CLOVA_SAMPLE)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """3 photos (one with EXIF rotation, so its OCR bytes are re-encoded); OCR caches for the first two."""
    data = tmp_path / "data"
    photo_dir = data / p30.PHOTO_DIR
    photo_dir.mkdir(parents=True)
    Image.new("RGB", (400, 300), "white").save(photo_dir / "901_a_01.png")
    Image.new("RGB", (300, 400), "gray").save(photo_dir / "901_a_02.png")
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (400, 300), "white").save(photo_dir / "902_b_01.jpeg", exif=exif)
    files = {"901_a_01.png": "901_바A_01", "901_a_02.png": "901_바A_02", "902_b_01.jpeg": "902_바B_01"}
    (photo_dir / "photo_map.json").write_text(json.dumps({"map": files}, ensure_ascii=False), encoding="utf-8")
    hashes = tmp_path / "hashes.json"
    hashes.write_text(json.dumps({"photos": [{"file": f, "photo_id": pid, "sha256": sha((photo_dir / f).read_bytes())}
                                             for f, pid in files.items()]}, ensure_ascii=False), encoding="utf-8")
    for f in ("901_a_01.png", "901_a_02.png"):
        write_cache(data, f, sha((photo_dir / f).read_bytes()))
    monkeypatch.setattr(p30, "PHOTO_HASHES_SHA256", p30.sha256_text_file(hashes))  # pin the made-up hash file
    monkeypatch.setattr(p30.server_gemini, "sleep", lambda s: waits.append(s))
    waits = []
    return SimpleNamespace(data=data, photo_dir=photo_dir, hashes=hashes, out=tmp_path / "out", files=files,
                           waits=waits, tmp=tmp_path)


def write_cache(data: Path, file: str, sent_sha256: str, latency_ms: int = 1234, **meta):
    path = data / "ocr_cache" / f"{Path(file).stem}__table-off.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"meta": {"source_image": file, "sent_sha256": sent_sha256, "table_detection": False,
                                         "latency_ms": latency_ms, "attempts": 1, "started_at": "2026-10-28T00:00:00Z",
                                         **meta},
                                "response": CLOVA_SAMPLE}), encoding="utf-8")
    return path


def write_sent_image(data: Path, name: str, image: Image.Image, quality: int = 90) -> str:
    """The image ai/ocr/clova.py sent for a rotated photo (<data>/prepared/<stem>.jpg); returns its SHA-256."""
    path = data / "prepared" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=quality)
    return sha(path.read_bytes())


def secrets(**over):
    return p30.Secrets({"GEMINI_API_KEY": KEY, "CLOVA_OCR_INVOKE_URL": URL, "CLOVA_OCR_SECRET": SECRET, **over})


def run(s, *extra, gemini=None, clova=None, keys=None):
    gemini = gemini if gemini is not None else FakeGemini()
    clova = clova if clova is not None else FakeClova()
    args = p30.parse_args(["--out", str(s.out), "--data-dir", str(s.data), "--hashes", str(s.hashes),
                           "--min-interval", "0", *extra])
    code = p30.run_command(args, keys or secrets(), p30.Clients(gemini=lambda settings: gemini, clova=clova))
    return code, gemini, clova


def records(out: Path) -> dict[str, dict]:
    return {f.name: json.loads(f.read_text(encoding="utf-8")) for f in sorted(out.glob("*_r*.json"))
            if score.RUN_FILE.match(f.name)}


def manifest(out: Path) -> dict:
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def test_three_runs_write_records_score_py_and_e2e_match_read(setup, monkeypatch):
    code, gemini, clova = run(setup)
    assert code == p30.EXIT_OK
    recs = records(setup.out)
    assert sorted(recs) == sorted(f"{Path(f).stem}_r{k}.json" for f in setup.files for k in (1, 2, 3))
    assert len(gemini.requests) == 9
    # CLOVA once for the photo without a cache, through the server's call_ocr; r2 and r3 use the cache
    assert len(clova.requests) == 1 and clova.requests[0] == (URL, {"X-OCR-SECRET": SECRET,
                                                                    "Content-Type": "application/json"})
    cache = json.loads((setup.data / "ocr_cache" / "902_b_01__table-off.json").read_text(encoding="utf-8"))
    assert cache["meta"]["table_detection"] is False and cache["response"] == CLOVA_SAMPLE
    assert cache["meta"]["resized"] is False  # rotated, not downscaled

    # the request is the server's: frozen model, thinking, prompt, OCR lines in the user text
    req = gemini.requests[0]
    assert req["model"] == "gemini-3.5-flash-lite" and req["generation_config"] == {"thinking_level": "medium"}
    assert hashlib.sha256(req["system_instruction"].encode()).hexdigest() == p30.PROMPT_SHA256
    assert req["input"][0]["text"].startswith(p30.server_hybrid.USER_HEADER) and "<ocr_lines>\nL001 [" in req["input"][0]["text"]
    assert req["store"] is False

    r = recs["901_a_01_r1.json"]
    assert r["output"] == ITEMS and r["server_result"] == "ok" and r["run"] == 1
    assert r["photo_id"] == "901_바A_01" and r["model"] == "gemini-3.5-flash-lite" and r["prompt_version"] == "hybrid-v1"
    assert r["clova"]["latency_ms"] == 1234 and r["clova"]["from_cache"] is True
    assert r["clova"]["image_check"] == "same image"
    assert r["gemini"]["latency_ms"] == r["latency_ms"] and r["gemini"]["attempts"] == 1
    assert len(r["flow_items"]) == 1 and len(r["flow_items"][0]["options"]) == 2  # server grouping
    assert recs["902_b_01_r1.json"]["clova"]["from_cache"] is False
    assert recs["902_b_01_r2.json"]["clova"]["from_cache"] is True

    # score.py reads the run dir (made-up labels for the made-up photos)
    labels = {pid: [{"raw_name": "Glenfiddich 12", "price_krw": 18000, "unit": "glass"}] for pid in setup.files.values()}
    stem_to_id = score.load_photo_map(setup.data, "i3")
    result = score.score_run_dir(setup.out, labels, stem_to_id)
    assert set(result["runs"]) == {1, 2, 3} and result["failed_calls"] == []
    assert result["summary"]["f1_strict"]["mean"] == pytest.approx(2 / 3)  # 1 of 2 output items is labelled

    # e2e_match.load_run (i3_match_eval.py --extraction <dir> --run k) reads run k only
    import e2e_match
    monkeypatch.setenv("BOTTLEMAP_DATA_DIR", str(setup.data))
    loaded = e2e_match.load_run(setup.out, 2, "i3")
    assert loaded == {pid: ITEMS["items"] for pid in setup.files.values()}

    m = manifest(setup.out)
    assert m["config"]["model"] == "gemini-3.5-flash-lite" and m["config"]["prompt_sha256"] == p30.PROMPT_SHA256
    assert m["frozen_code"] == p30.FROZEN_CODE
    assert m["photos"]["901_a_01.png"]["sha256"] == sha((setup.photo_dir / "901_a_01.png").read_bytes())
    assert set(m["ocr_caches"]) == set(setup.files)
    cmd = m["commands"][-1]
    assert cmd["gemini_calls"] == 9 and cmd["clova_calls"] == 1 and cmd["stopped"] is None
    assert "commit" in cmd["git"]
    summary = json.loads((setup.out / "summary.json").read_text(encoding="utf-8"))
    assert summary["runs"]["r1"]["records"] == 3 and summary["runs"]["r1"]["latency_ms"]["clova"]["n"] == 3


def test_rerun_skips_existing_records_and_makes_no_call(setup):
    run(setup, "--runs", "1")
    code, gemini, clova = run(setup, "--runs", "1")
    assert code == p30.EXIT_OK and gemini.requests == [] and clova.requests == []
    assert manifest(setup.out)["commands"][-1]["skipped"] == 3


def test_check_makes_no_call_and_writes_nothing(setup, capsys):
    code, gemini, clova = run(setup, "--check")
    assert code == p30.EXIT_OK and gemini.requests == [] and clova.requests == []
    assert not setup.out.exists()
    assert "CLOVA calls needed: 1" in capsys.readouterr().out


def test_photo_hash_mismatch_stops_before_any_call(setup, capsys):
    with open(setup.photo_dir / "901_a_02.png", "ab") as f:
        f.write(b"\0")
    code, gemini, clova = run(setup)
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == [] and clova.requests == []
    assert not setup.out.exists()
    assert "901_a_02.png: SHA-256" in capsys.readouterr().out


@pytest.mark.parametrize("change", ["missing_file", "map_id", "map_extra"])
def test_photo_set_mismatch_stops(setup, change):
    if change == "missing_file":
        (setup.photo_dir / "902_b_01.jpeg").unlink()
    else:
        files = dict(setup.files)
        if change == "map_id":
            files["901_a_01.png"] = "other"
        else:
            files["903_c_01.png"] = "903_C_01"
        (setup.photo_dir / "photo_map.json").write_text(json.dumps({"map": files}), encoding="utf-8")
    code, gemini, _ = run(setup)
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == []


def test_frozen_code_change_stops(setup, monkeypatch):
    monkeypatch.setitem(p30.FROZEN_CODE, "backend/app/extraction/hybrid.py", "0" * 64)
    code, gemini, _ = run(setup)
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == []


def test_ocr_cache_of_another_image_stops(setup, capsys):
    write_cache(setup.data, "901_a_01.png", "f" * 64)  # original bytes are sent: another image
    code, gemini, clova = run(setup, "--runs", "1")
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == [] and clova.requests == []
    write_cache(setup.data, "901_a_01.png", sha((setup.photo_dir / "901_a_01.png").read_bytes()),
                source_image="901_a_02.png")
    code, gemini, _ = run(setup, "--runs", "1")
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == []
    assert "OCR cache is for '901_a_02.png'" in capsys.readouterr().out


def test_reencoded_ocr_cache_without_provenance_stops(setup, capsys):
    # rotated photo, other sent bytes, and nothing on disk to show which image they were
    write_cache(setup.data, "902_b_01.jpeg", "f" * 64, sent_image="902_b_01.jpg")
    code, gemini, clova = run(setup, "--runs", "1")
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == [] and clova.requests == []
    printed = capsys.readouterr().out
    assert "not on disk to check" in printed and "delete ocr_cache/902_b_01__table-off.json" in printed


def test_reencoded_ocr_cache_of_the_same_pixels_is_kept(setup):
    upright = Image.new("RGB", (300, 400), "white")  # what the server sends after EXIF rotation
    digest = write_sent_image(setup.data, "902_b_01.jpg", upright, quality=80)  # other encoder settings
    write_cache(setup.data, "902_b_01.jpeg", digest, sent_image="902_b_01.jpg", resized=False)
    code, _, clova = run(setup, "--runs", "1")
    assert code == p30.EXIT_OK and clova.requests == []
    assert records(setup.out)["902_b_01_r1.json"]["clova"]["image_check"].startswith(
        "re-encoded bytes differ; same pixels")


@pytest.mark.parametrize("image, why", [
    (Image.new("RGB", (300, 400), "black"), "mean pixel difference"),
    (Image.new("RGB", (400, 300), "white"), "a different pixel size"),
])
def test_reencoded_ocr_cache_of_other_pixels_stops(setup, capsys, image, why):
    digest = write_sent_image(setup.data, "902_b_01.jpg", image)
    write_cache(setup.data, "902_b_01.jpeg", digest, sent_image="902_b_01.jpg", resized=False)
    code, gemini, _ = run(setup, "--runs", "1")
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == []
    assert why in capsys.readouterr().out


def test_reencoded_ocr_cache_whose_sent_image_changed_stops(setup, capsys):
    write_sent_image(setup.data, "902_b_01.jpg", Image.new("RGB", (300, 400), "white"))
    write_cache(setup.data, "902_b_01.jpeg", "f" * 64, sent_image="902_b_01.jpg", resized=False)
    code, gemini, _ = run(setup, "--runs", "1")
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == []
    assert "no longer hashes to the cache's sent_sha256" in capsys.readouterr().out


def test_reencoded_ocr_cache_made_by_this_runner_is_checked_by_source_sha256(setup):
    photo = sha((setup.photo_dir / "902_b_01.jpeg").read_bytes())
    write_cache(setup.data, "902_b_01.jpeg", "f" * 64, source_sha256=photo)
    code, _, _ = run(setup, "--runs", "1")
    assert code == p30.EXIT_OK
    assert "source_sha256" in records(setup.out)["902_b_01_r1.json"]["clova"]["image_check"]
    write_cache(setup.data, "902_b_01.jpeg", "f" * 64, source_sha256="0" * 64)
    code, gemini, _ = run(setup, "--runs", "2")
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == []


def test_runner_cache_records_the_source_photo(setup):
    run(setup, "--runs", "1")
    meta = json.loads((setup.data / "ocr_cache" / "902_b_01__table-off.json").read_text(encoding="utf-8"))["meta"]
    assert meta["source_sha256"] == sha((setup.photo_dir / "902_b_01.jpeg").read_bytes())
    assert p30.check_ocr_cache({"meta": meta, "response": CLOVA_SAMPLE},
                               p30.verify_photos(setup.photo_dir, setup.hashes)[2], setup.data)["image_check"] == "same image"


@pytest.mark.parametrize("change", ["edited", "other_file", "missing"])
def test_hash_file_other_than_the_frozen_one_stops(setup, capsys, change):
    if change == "edited":  # e.g. a photo dropped from the set: the rest would still verify
        data = json.loads(setup.hashes.read_text(encoding="utf-8"))
        data["photos"] = data["photos"][:2]
        setup.hashes.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    elif change == "other_file":
        other = setup.tmp / "other.json"
        other.write_text(setup.hashes.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        setup.hashes = other
    else:
        setup.hashes.unlink()
    code, gemini, clova = run(setup, "--check")
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == [] and clova.requests == []
    assert "photo check failed" in capsys.readouterr().out


def test_frozen_hash_file_in_the_repo_is_the_pinned_one():
    assert p30.sha256_text_file(p30.PHOTO_HASHES) == p30.PHOTO_HASHES_SHA256
    assert len(json.loads(p30.PHOTO_HASHES.read_text(encoding="utf-8"))["photos"]) == 33


def test_scoring_code_change_stops_even_check(setup, monkeypatch, capsys):
    assert p30.check_frozen_code(p30.REPO_ROOT)  # the checkout's score.py and e2e_match.py are the frozen ones
    monkeypatch.setitem(p30.FROZEN_EVAL, "ai/eval/score.py", "0" * 64)
    code, gemini, _ = run(setup, "--check")
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == []
    assert "frozen scoring files changed" in capsys.readouterr().out


def test_clova_cap_counts_the_servers_retries(setup, monkeypatch):
    monkeypatch.setattr(p30.server_clova, "sleep", lambda s: None)

    class Flaky:
        def __init__(self):
            self.requests = 0

        def post(self, url, json=None, headers=None):
            self.requests += 1
            return httpx.Response(503, json={"code": "busy"}) if self.requests == 1 else httpx.Response(200, json=CLOVA_SAMPLE)

    flaky = Flaky()
    code, gemini, _ = run(setup, "--runs", "1", "--max-clova-calls", "1", clova=flaky)
    assert code == p30.EXIT_STOPPED and flaky.requests == 1  # the retry would be a second request
    stopped = manifest(setup.out)["commands"][-1]
    assert "CLOVA call cap 1 reached during the server's retries" in stopped["stopped"] and stopped["clova_calls"] == 1
    assert not (setup.data / "ocr_cache" / "902_b_01__table-off.json").exists()
    flaky = Flaky()
    code, _, _ = run(setup, "--runs", "1", "--max-clova-calls", "2", clova=flaky)
    assert code == p30.EXIT_OK and flaky.requests == 2 and manifest(setup.out)["commands"][-1]["clova_calls"] == 2


def test_changed_ocr_cache_between_commands_stops(setup):
    run(setup, "--runs", "1")
    write_cache(setup.data, "901_a_01.png", sha((setup.photo_dir / "901_a_01.png").read_bytes()), latency_ms=999)
    code, gemini, _ = run(setup, "--runs", "2")
    assert code == p30.EXIT_STOPPED and gemini.requests == []
    assert "OCR cache changed" in manifest(setup.out)["commands"][-1]["stopped"]


def test_call_cap_stops_cleanly_and_next_command_resumes(setup):
    code, gemini, _ = run(setup, "--runs", "1", "--max-calls", "2")
    assert code == p30.EXIT_STOPPED and len(gemini.requests) == 2
    assert sorted(records(setup.out)) == ["901_a_01_r1.json", "901_a_02_r1.json"]
    assert "call cap 2" in manifest(setup.out)["commands"][-1]["stopped"]
    code, gemini, _ = run(setup, "--runs", "1", "--max-calls", "2")
    assert code == p30.EXIT_OK and len(gemini.requests) == 1 and len(records(setup.out)) == 3


def test_call_cap_counts_the_servers_retries(setup):
    fake = FakeGemini([ApiError(503, "unavailable"), ApiError(503, "unavailable")])
    code, gemini, _ = run(setup, "--runs", "1", "--max-calls", "2", gemini=fake)
    assert code == p30.EXIT_STOPPED and len(gemini.requests) == 2 and records(setup.out) == {}


def test_daily_quota_stops_at_once_without_the_servers_retries(setup):
    quota = ApiError(429, "RESOURCE_EXHAUSTED: quota GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    code, gemini, _ = run(setup, "--runs", "1", gemini=FakeGemini([answer(), quota]))
    assert code == p30.EXIT_STOPPED and len(gemini.requests) == 2 and setup.waits == []
    assert list(records(setup.out)) == ["901_a_01_r1.json"]
    assert manifest(setup.out)["commands"][-1]["stopped"].startswith("daily quota")


def test_rate_limit_is_retried_by_the_server_and_stops_if_it_stays(setup):
    rpm = ApiError(429, "RESOURCE_EXHAUSTED: GenerateRequestsPerMinutePerProjectPerModel")
    code, gemini, _ = run(setup, "--runs", "1", gemini=FakeGemini([rpm, answer()] + [rpm] * 6))
    assert code == p30.EXIT_STOPPED
    assert records(setup.out)["901_a_01_r1.json"]["attempts"] == 2
    assert setup.waits == [5, 5, 10, 20, 40, 60]  # server backoff: 1 retry, then 5 retries before giving up
    assert "quota (HTTP 429 after the server's retries)" in manifest(setup.out)["commands"][-1]["stopped"]
    assert not (setup.out / "901_a_02_r1.error.json").exists()


def test_no_answer_is_written_as_error_file_and_retried_next_time(setup):
    code, _, _ = run(setup, "--runs", "1", gemini=FakeGemini([ApiError(400, f"bad request for key {KEY}")]))
    assert code == p30.EXIT_STOPPED
    err = json.loads((setup.out / "901_a_01_r1.error.json").read_text(encoding="utf-8"))
    assert err["output"] is None and err["attempts"] == 1 and KEY not in err["error"] and "***" in err["error"]
    assert len(records(setup.out)) == 2  # the other photos still ran
    assert score.score_run_dir(setup.out, {pid: [] for pid in setup.files.values()},
                               score.load_photo_map(setup.data, "i3"))["runs"][1]["missing_photos"] == ["901_바A_01"]
    code, gemini, _ = run(setup, "--runs", "1")
    assert code == p30.EXIT_OK and len(gemini.requests) == 1
    assert not (setup.out / "901_a_01_r1.error.json").exists() and len(records(setup.out)) == 3


def test_output_the_server_rejects_is_recorded_as_empty(setup):
    code, _, _ = run(setup, "--runs", "1", gemini=FakeGemini([answer('{"items": "oops"}')]))
    assert code == p30.EXIT_OK
    r = records(setup.out)["901_a_01_r1.json"]
    assert r["output"] is None and r["server_result"].startswith("failed") and r["raw_text"] == '{"items": "oops"}'
    summary = json.loads((setup.out / "summary.json").read_text(encoding="utf-8"))
    assert summary["runs"]["r1"]["server_rejected_output"] == ["901_a_01.png"]
    assert "901_a_01_r1.json" in score.score_run_dir(setup.out, {pid: [] for pid in setup.files.values()},
                                                     score.load_photo_map(setup.data, "i3"))["failed_calls"]


def test_clova_failure_stops_without_record(setup):
    class Down:
        def post(self, url, json=None, headers=None):
            return httpx.Response(401, json={"code": "0002", "message": f"bad secret {SECRET}"})

    code, gemini, _ = run(setup, "--runs", "1", clova=Down())
    assert code == p30.EXIT_STOPPED and len(gemini.requests) == 2
    assert "CLOVA OCR failed for 902_b_01.jpeg" in manifest(setup.out)["commands"][-1]["stopped"]
    assert not (setup.data / "ocr_cache" / "902_b_01__table-off.json").exists()


def test_missing_keys_stop_before_any_call(setup):
    code, gemini, _ = run(setup, keys=secrets(GEMINI_API_KEY=""))
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == []
    code, gemini, _ = run(setup, keys=secrets(CLOVA_OCR_SECRET=""))
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == []


def test_manifest_from_another_configuration_stops(setup):
    run(setup, "--runs", "1")
    m = manifest(setup.out)
    m["config"]["model"] = "gemini-3.6-flash"
    (setup.out / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    code, gemini, _ = run(setup, "--runs", "2")
    assert code == p30.EXIT_PREFLIGHT and gemini.requests == []


def test_keys_are_never_written_or_printed(setup, capsys):
    run(setup, "--runs", "1", gemini=FakeGemini([ApiError(400, f"key={KEY} url={URL}")]))
    run(setup, "--runs", "1", "2")
    printed = capsys.readouterr().out
    written = [f.read_text(encoding="utf-8") for d in (setup.out, setup.data / "ocr_cache") for f in d.iterdir()]
    for text in written + [printed]:
        assert KEY not in text and SECRET not in text and URL not in text


def test_secrets_read_only_from_the_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-shell")
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=from-file\nCLOVA_OCR_INVOKE_URL=https://x.test/abc/\n", encoding="utf-8")
    s = p30.Secrets.from_env_file(env)
    assert s.get("GEMINI_API_KEY") == "from-file" and not s.has("CLOVA_OCR_SECRET")
    assert s.clova_settings().invoke_url == "https://x.test/abc/general"
    assert not p30.Secrets.from_env_file(tmp_path / "none").has("GEMINI_API_KEY")


def test_client_made_after_a_hard_timeout_is_counted_too():
    budget = p30.Budget(1, "Gemini")
    fake = FakeGemini()
    with p30.counted_gemini(lambda settings: fake, budget):
        client = p30.server_gemini.make_client(None)
        client.interactions.create(model="m")
        with pytest.raises(p30.CallCapReached):
            client.interactions.create(model="m")
    assert p30.server_gemini.make_client is not None and len(fake.requests) == 1


def test_percentile_and_parse_args():
    assert p30.percentile([], 0.5) is None
    assert p30.percentile([5, 1, 3, 2, 4], 0.5) == 3 and p30.percentile(list(range(1, 21)), 0.95) == 19
    with pytest.raises(SystemExit):
        p30.parse_args(["--out", "x", "--runs", "1", "1"])
