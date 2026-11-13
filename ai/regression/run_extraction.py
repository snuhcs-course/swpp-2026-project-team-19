"""Run the server's hybrid extraction on the regression photos (I4-P12). Calls Gemini.

    python ai/regression/run_extraction.py --prompt v2 --out ai/runs/<date>_p12/hybrid_v2
    python ai/regression/run_extraction.py --prompt v1 --out ai/runs/<date>_p12/hybrid_v1    # same day, to compare
    python ai/regression/regression.py --extraction ai/runs/<date>_p12/hybrid_v2

One Gemini call per photo (15 for the whole set) through the server code: extract_menu_hybrid
(prompt v1) or extract_menu_hybrid_v2 (prompt v2), model and thinking level as deployed. CLOVA is
not called: the OCR answer comes from <data_dir>/ocr_cache/<stem>__table-off.json, and a photo
without a cache stops the command. Photos are read from <data_dir> (BOTTLEMAP_DATA_DIR, default
../bottlemap-p14/data) and must have the SHA-256 listed in the fixture.

Each photo gives <out>/<stem>_r<run>.json in the format regression.py --extraction and
ai/eval/score.py read: `raw_text` (the model's answer), `prompt_version`, `ocr_lines`, tokens and
latency, and for prompt v2 `other_items`. An existing record is kept, so a stopped command can
be run again. An answer the server rejects is recorded with "output": null. A call that gets no
answer (quota, network) stops the command; nothing is written for that photo.

GEMINI_API_KEY is read from the repo .env and is never printed or written.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "regression"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

import regression  # noqa: E402
from app.extraction import ExtractionSettings, InvalidModelOutputError, ModelCallError  # noqa: E402
from app.extraction.clova import ClovaSettings  # noqa: E402
from app.extraction.hybrid import extract_menu_hybrid  # noqa: E402
from app.extraction.hybrid_v2 import extract_menu_hybrid_v2  # noqa: E402

MODEL = "gemini-3.5-flash-lite"   # backend/deploy/env.production.example
THINKING_LEVEL = "medium"
MAX_ATTEMPTS = 2                  # the server retries 6 times; a test run should not spend the daily quota on retries
EXTRACTORS = {"v1": extract_menu_hybrid, "v2": extract_menu_hybrid_v2}
MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
REPLAY_CLOVA = ClovaSettings(invoke_url="replay://ocr-cache/general", secret="")


class ReplayOcr:
    """httpx stand-in for the server's CLOVA call: answers with the cached OCR response."""

    def __init__(self, cache: dict):
        self.cache, self.sent_sha256 = cache, None

    def post(self, url, json=None, headers=None):
        import base64
        self.sent_sha256 = hashlib.sha256(base64.b64decode(json["images"][0]["data"])).hexdigest()
        payload = copy.deepcopy(self.cache["response"])
        return type("Response", (), {"status_code": 200, "json": lambda self: payload})()


def api_key() -> str:
    from dotenv import dotenv_values
    return (dotenv_values(REPO_ROOT / ".env").get("GEMINI_API_KEY") or "").strip()


def run_photo(fixture: dict, data_dir: Path, prompt: str, settings: ExtractionSettings) -> dict:
    """One photo through the server extraction. Raises SystemExit for a missing or wrong input and
    ModelCallError when the model gives no answer."""
    photo = fixture["photo"]
    path = data_dir / photo["photo_dir"] / photo["file"]
    cache_path = data_dir / "ocr_cache" / f"{Path(photo['file']).stem}__table-off.json"
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != photo["sha256"]:
        raise SystemExit(f"{fixture['photo_id']}: {path} is missing or is not the listed photo")
    if not cache_path.is_file():
        raise SystemExit(f"{fixture['photo_id']}: no OCR cache at {cache_path}")
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    ocr = ReplayOcr(cache)
    record = {"condition": "hybrid", "model": settings.model, "thinking_level": settings.thinking_level,
              "source_image": photo["file"], "photo_id": fixture["photo_id"]}
    try:
        result = EXTRACTORS[prompt](path.read_bytes(), MIME_TYPES[path.suffix.lower()], REPLAY_CLOVA,
                                    settings=settings, ocr_client=ocr)
    except InvalidModelOutputError as error:
        meta, raw_text, rows = error.meta, error.raw_text, None
        record["parse_error"] = str(error)[:500]
    else:
        meta = result["meta"]
        raw_text = json.dumps(meta["rawOutput"], ensure_ascii=False)
        rows = regression.flatten(result["items"])
    record.update({
        "prompt_version": meta["promptVersion"], "prompt_sha256": meta["promptSha256"],
        "started_at": meta["startedAt"], "latency_ms": meta["latencyMs"], "attempts": meta["attempts"],
        "status": meta["status"], "input_tokens": meta["inputTokens"], "output_tokens": meta["outputTokens"],
        "thought_tokens": meta["thoughtTokens"], "total_tokens": meta["totalTokens"],
        # whisky lines only, one row per price option: what score.py scores
        "output": None if rows is None else {"items": rows},
        "other_items": meta.get("otherItems"), "other_items_dropped": meta.get("otherItemsDropped"),
        "raw_text": raw_text, "ocr_lines": meta["ocr"]["lines"],
        # False when this machine re-encodes the photo to other bytes than the cache was made from;
        # the OCR boxes are relative to the image size, so the lines still apply
        "ocr_cache_same_bytes": ocr.sent_sha256 == cache.get("meta", {}).get("sent_sha256"),
    })
    return record


def main(argv=None) -> int:
    from extract import data_dir as default_data_dir
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--prompt", choices=sorted(EXTRACTORS), required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--data-dir", type=Path)
    ap.add_argument("--photos", nargs="*", help="photo ids (default: all 15)")
    ap.add_argument("--max-calls", type=int, default=20, help="photos to send to Gemini in this command")
    args = ap.parse_args(argv)

    fixtures = [fx for fx in regression.load_fixtures() if not args.photos or fx["photo_id"] in args.photos]
    key = api_key()
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set in the repo .env")
    settings = ExtractionSettings(api_key=key, model=MODEL, thinking_level=THINKING_LEVEL, max_attempts=MAX_ATTEMPTS)
    data_dir = args.data_dir or default_data_dir()
    args.out.mkdir(parents=True, exist_ok=True)
    calls = 0
    for fx in fixtures:
        target = args.out / f"{Path(fx['photo']['file']).stem}_r{args.run}.json"
        if target.exists():
            print(f"{fx['photo_id']:18} kept {target.name}")
            continue
        if calls >= args.max_calls:
            print(f"stopped at --max-calls {args.max_calls}; run the command again to continue")
            return 1
        calls += 1
        try:
            record = run_photo(fx, data_dir, args.prompt, settings)
        except ModelCallError as error:
            print(f"{fx['photo_id']:18} no answer ({str(error).replace(key, '***')[:200]}); stopped")
            return 1
        record["run"] = args.run
        target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        whisky = "rejected" if record["output"] is None else len(record["output"]["items"])
        print(f"{fx['photo_id']:18} whisky rows {whisky}  other {len(record['other_items'] or [])}  "
              f"{record['latency_ms'] / 1000:.1f}s  out tokens {record['output_tokens']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
