"""I5 row pairing check: hybrid prompts v1, v2 and v3 on chosen I3 photos, same day. Calls Gemini.

    python ai/eval/i5_row_pairing.py --out ai/runs/<date>_i5_row_pairing --photos 014_tale_07 --check
    python ai/eval/i5_row_pairing.py --out ai/runs/<date>_i5_row_pairing --photos 014_tale_07 --runs 1 2 3
    python ai/eval/i5_row_pairing.py --out ai/runs/<date>_i5_row_pairing/regression --photos regression         --prompts v2 v3 --runs 1 --max-calls 34

`--photos regression` is the 15 regression photos (ai/regression/fixtures) and the two photos the
old rule was written for (EXTRA_PHOTOS), which are not regression fixtures: their SHA-256 is
taken from the local file, so only the OCR cache check ties them to a known image.

Prompt v3 is prompt v2 with the "이름과 가격의 행 대응" rule rewritten (the y gap between a name
and its price may change steadily from top to bottom; the n-th name / n-th price count is a
check). It is not wired into the server: this script points hybrid_v2 at hybrid_prompt_v3.md for
the v3 calls only.

One Gemini call per photo, prompt and run through the server code, as ai/regression/
run_extraction.py does (`run_photo`: photo and OCR cache checks, record format, 2 attempts). The
prompts are interleaved (v1, v2, v3 of run 1, then run 2, ...) so the time of day is the same
for the three. Records go to <out>/<prompt>/<stem>_r<run>.json; an existing record is kept.

The I3 photos are a frozen evaluation set. These runs show whether a known error is reproduced
and fixed on the photo it was reported on; they are not a score of the fix.

GEMINI_API_KEY is read from the repo .env and is never printed or written.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "regression"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

import hashlib  # noqa: E402

import p46_extract  # noqa: E402
import regression  # noqa: E402
import run_extraction as rx  # noqa: E402
from app.extraction import ExtractionSettings, ModelCallError  # noqa: E402
from app.extraction import hybrid_v2  # noqa: E402

PROMPTS = ("v1", "v2", "v3")
V2_PROMPT = (hybrid_v2.PROMPT_VERSION, hybrid_v2.PROMPT_PATH)
V3_PROMPT = ("hybrid-v3", hybrid_v2.PROMPT_PATH.with_name("hybrid_prompt_v3.md"))
MIN_INTERVAL_S = 4.5
# The photos the "y gap stays the same" rule came from (P12 prompt v3, ai/runs/ai_usage_log.md).
EXTRA_PHOTOS = (("007_위스키복춘_02", "eval_photos", "007_bokchun_02.jpg"),
                ("012_Beck_04", "eval_photos_test", "012_beck_04.jpeg"))


def known_photos(data_dir: Path) -> dict[str, dict]:
    """File stem -> run_extraction fixture, for the I3 photos, the regression photos and EXTRA_PHOTOS."""
    photos = p46_extract.load_photos() + regression.load_fixtures()
    for photo_id, photo_dir, file in EXTRA_PHOTOS:
        path = data_dir / photo_dir / file
        if path.is_file():
            photos.append({"photo_id": photo_id, "photo": {
                "file": file, "photo_dir": photo_dir, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}})
    return {Path(fx["photo"]["file"]).stem: fx for fx in photos}


def regression_stems() -> list[str]:
    return ([Path(fx["photo"]["file"]).stem for fx in regression.load_fixtures()]
            + [Path(file).stem for _, _, file in EXTRA_PHOTOS])


def use_prompt(prompt: str) -> str:
    """Point hybrid_v2 at the prompt file of `prompt`; returns the run_extraction extractor key."""
    hybrid_v2.PROMPT_VERSION, hybrid_v2.PROMPT_PATH = V3_PROMPT if prompt == "v3" else V2_PROMPT
    hybrid_v2.load_prompt.cache_clear()
    return "v1" if prompt == "v1" else "v2"


def main(argv=None, *, sleep=time.sleep) -> int:
    from extract import data_dir as default_data_dir
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--photos", nargs="+", required=True, help="file stems, e.g. 014_tale_07, or `regression`")
    ap.add_argument("--prompts", nargs="+", default=list(PROMPTS), choices=PROMPTS)
    ap.add_argument("--runs", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--data-dir", type=Path)
    ap.add_argument("--check", action="store_true", help="list the calls that would be made; no API call")
    ap.add_argument("--max-calls", type=int, default=9)
    args = ap.parse_args(argv)

    data_dir = args.data_dir or default_data_dir()
    stems = regression_stems() if args.photos == ["regression"] else args.photos
    known = known_photos(data_dir)
    unknown = [stem for stem in stems if stem not in known]
    if unknown:
        raise SystemExit(f"not a known photo (or the file is missing): {', '.join(unknown)}")
    photos = [known[stem] for stem in stems]
    problems = p46_extract.check_inputs(photos, data_dir)
    if problems:
        raise SystemExit("\n".join(problems))
    todo = [(run, fx, prompt, args.out / prompt / f"{Path(fx['photo']['file']).stem}_r{run}.json")
            for run in args.runs for fx in photos for prompt in args.prompts]
    todo = [job for job in todo if not job[3].exists()]
    print(f"calls to make: {len(todo)} (max {args.max_calls}), {rx.MODEL}, thinking {rx.THINKING_LEVEL}")
    if args.check:
        return 0
    key = rx.api_key()
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set in the repo .env")
    settings = ExtractionSettings(api_key=key, model=rx.MODEL, thinking_level=rx.THINKING_LEVEL,
                                  max_attempts=rx.MAX_ATTEMPTS)
    for calls, (run, fx, prompt, target) in enumerate(todo):
        if calls >= args.max_calls:
            print(f"stopped at --max-calls {args.max_calls}")
            return 1
        if calls:
            sleep(MIN_INTERVAL_S)
        try:
            record = rx.run_photo(fx, data_dir, use_prompt(prompt), settings)
        except ModelCallError as error:
            print(f"{target.name} {prompt} no answer ({str(error).replace(key, '***')[:200]}); stopped")
            return 1
        record["run"] = run
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"))
        rows = "rejected" if record["output"] is None else len(record["output"]["items"])
        print(f"{target.stem} {prompt} {record['prompt_version']} {record['prompt_sha256'][:12]} rows {rows}  "
              f"{record['latency_ms'] / 1000:.1f}s  thought {record['thought_tokens']}  attempts {record['attempts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
