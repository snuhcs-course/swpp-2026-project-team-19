"""P46 extraction: the server's hybrid extraction with prompt v2 on the 33 I3 photos (I4-P46). Calls Gemini.

    python ai/eval/p46_extract.py --out ai/runs/<date>_p46/hybrid_v2_i3 --check          # no API call
    python ai/eval/p46_extract.py --out ai/runs/<date>_p46/hybrid_v2_i3 --runs 1 2 3
    python ai/eval/score.py --set i3 ai/runs/<date>_p46/hybrid_v2_i3
    python ai/eval/i3_match_eval.py --set i3 --catalog full --extraction ai/runs/<date>_p46/hybrid_v2_i3 --run 1 ...

Prompt v1 on these photos is P30 (ai/eval/p30_extract.py, 2026-11-04); its code and prompt have
not changed since, so P46 does not run it again and compares with the P30 records.

One Gemini call per photo and run through the server code (`extract_menu_hybrid_v2`), model and
thinking level as deployed, with the server's retry policy (6 attempts), as P30 ran prompt v1.
CLOVA is not called: the OCR answer is the cache P30 made (<data_dir>/ocr_cache/
<stem>__table-off.json), so the two prompts read the same OCR lines. The photo checks, the OCR
cache check and the record are those of ai/regression/run_extraction.py (`run_photo`): a photo
that is not the listed one, or a cache that was not made from it, stops the command before any
call. The photos are the 33 of ai/eval/i3_photo_sha256.json, whose own SHA-256 is pinned.

Each photo gives <out>/<stem>_r<run>.json: "output" holds the whisky rows (what score.py and
i3_match_eval.py --extraction read) and "other_items" the non-whisky lines (what
p46_report.py reads). An existing record is kept, so a stopped command is run again to continue;
a kept record of another prompt, model, photo or run stops the command. A call without an
answer (quota, network) stops the command and writes nothing for that photo. <out>/manifest.json
records the configuration and the code commit of every command.

These photos are no longer unseen for prompt v1 (P30). Prompt v2 was written and checked on the
15 regression photos (I4-P12) and has not been run on them before this.

The non-whisky lines these photos are scored against (eval/mixed_lines_i3_v1.json) were written
without any model output. To keep it so, a run stops until that file says who reviewed it
("reviewed"): the lines are settled before prompt v2 sees the photos, not after.

GEMINI_API_KEY is read from the repo .env and is never printed or written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "regression"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "eval"))
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

import run_extraction as rx  # noqa: E402
from app.extraction import ExtractionSettings, ModelCallError  # noqa: E402
from app.extraction import hybrid_v2  # noqa: E402
from app.extraction.clova import ocr_image  # noqa: E402
from app.extraction.image import prepare_image  # noqa: E402

PROMPT = "v2"
PHOTO_DIR = "eval_photos_i3"
PHOTO_HASHES = REPO_ROOT / "ai" / "eval" / "i3_photo_sha256.json"
PHOTO_HASHES_SHA256 = "305c4f0e7e9afd45de4b28426cdea980c18618a96da8d0f99e1bdbc0a29ff602"  # as p30_extract.py pins it
MIXED_LINES = REPO_ROOT / "eval" / "mixed_lines_i3_v1.json"
RUNS = (1, 2, 3)
MIN_INTERVAL_S = 4.5  # between photos, as P30


def sha256_lf(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_photos(hashes: Path = PHOTO_HASHES, expect_sha: str | None = PHOTO_HASHES_SHA256) -> list[dict]:
    """The 33 photos as run_extraction fixtures (photo id, file, directory, SHA-256)."""
    if expect_sha and sha256_lf(hashes) != expect_sha:
        raise SystemExit(f"{hashes.name} is not the frozen photo list ({expect_sha[:12]}...)")
    return [{"photo_id": p["photo_id"], "photo": {"file": p["file"], "photo_dir": PHOTO_DIR, "sha256": p["sha256"]}}
            for p in json.loads(hashes.read_text(encoding="utf-8"))["photos"]]


def check_inputs(photos: list[dict], data_dir: Path) -> list[str]:
    """Problems that would stop a run: a missing or different photo, a missing OCR cache, or a
    cache that was not made from the image the server would send. No API call."""
    problems = []
    for fx in photos:
        photo = fx["photo"]
        path = data_dir / photo["photo_dir"] / photo["file"]
        cache_path = data_dir / "ocr_cache" / f"{Path(photo['file']).stem}__table-off.json"
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != photo["sha256"]:
            problems.append(f"{fx['photo_id']}: {path} is missing or is not the listed photo")
            continue
        if not cache_path.is_file():
            problems.append(f"{fx['photo_id']}: no OCR cache at {cache_path}")
            continue
        expected = json.loads(cache_path.read_text(encoding="utf-8")).get("meta", {}).get("sent_sha256")
        sent = hashlib.sha256(
            ocr_image(*prepare_image(path.read_bytes(), rx.MIME_TYPES[path.suffix.lower()]))[0]).hexdigest()
        if not expected or sent != expected:
            problems.append(f"{fx['photo_id']}: the OCR cache {cache_path.name} was not made from this photo")
    return problems


def configuration() -> dict:
    return {"prompt": PROMPT, "prompt_version": hybrid_v2.PROMPT_VERSION,
            "prompt_sha256": hashlib.sha256(hybrid_v2.load_prompt().encode("utf-8")).hexdigest(),
            "model": rx.MODEL, "thinking_level": rx.THINKING_LEVEL,
            "max_attempts": ExtractionSettings.max_attempts, "photo_hashes_sha256": PHOTO_HASHES_SHA256,
            "ocr": "P30 CLOVA cache, table detection off"}


def git_head() -> str | None:
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def update_manifest(out: Path, command: dict) -> None:
    """Keep one configuration per run dir; a command with another configuration stops."""
    path = out / "manifest.json"
    config = configuration()
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"configuration": config, "commands": []}
    if manifest["configuration"] != config:
        different = sorted(k for k in config if manifest["configuration"].get(k) != config[k])
        raise SystemExit(f"{path} was made with another configuration ({', '.join(different)}): use another --out")
    manifest["commands"].append(command)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None, *, sleep=time.sleep) -> int:
    from extract import data_dir as default_data_dir
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--runs", type=int, nargs="+", default=list(RUNS), choices=RUNS)
    ap.add_argument("--data-dir", type=Path)
    ap.add_argument("--hashes", type=Path, default=PHOTO_HASHES, help=argparse.SUPPRESS)  # tests
    ap.add_argument("--no-hashes-sha-check", action="store_true", help=argparse.SUPPRESS)  # tests
    ap.add_argument("--mixed-lines", type=Path, default=MIXED_LINES, help=argparse.SUPPRESS)  # tests
    ap.add_argument("--check", action="store_true", help="check the photos and OCR caches; no API call")
    ap.add_argument("--max-calls", type=int, default=45, help="photos to send to Gemini in this command")
    args = ap.parse_args(argv)

    photos = load_photos(args.hashes, None if args.no_hashes_sha_check else PHOTO_HASHES_SHA256)
    data_dir = args.data_dir or default_data_dir()
    problems = check_inputs(photos, data_dir)
    if problems:
        print("\n".join(problems))
        raise SystemExit(f"STOP: {len(problems)} of {len(photos)} photos cannot be run; nothing was sent")
    print(f"photos and OCR caches verified: {len(photos)}; prompt {hybrid_v2.PROMPT_VERSION} "
          f"{configuration()['prompt_sha256'][:12]}, {rx.MODEL}, thinking {rx.THINKING_LEVEL}")
    reviewed = json.loads(args.mixed_lines.read_text(encoding="utf-8")).get("reviewed")
    print(f"non-whisky lines ({args.mixed_lines.name}): " + (f"reviewed: {reviewed}" if reviewed else "NOT reviewed yet"))
    if args.check:
        return 0
    if not reviewed:
        raise SystemExit(f"STOP: {args.mixed_lines.name} is not reviewed (\"reviewed\" is empty). The non-whisky lines "
                         f"are settled before prompt v2 is run on these photos; nothing was sent")

    key = rx.api_key()
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set in the repo .env")
    settings = ExtractionSettings(api_key=key, model=rx.MODEL, thinking_level=rx.THINKING_LEVEL)
    args.out.mkdir(parents=True, exist_ok=True)
    command = {"started_at": datetime.now(timezone.utc).isoformat(), "runs": args.runs, "code_commit": git_head(),
               "calls": 0, "stopped": None}
    update_manifest(args.out, command)

    def finish(code: int) -> int:
        manifest = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
        manifest["commands"][-1] = command
        (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
        return code

    for run in args.runs:
        for fx in photos:
            target = args.out / f"{Path(fx['photo']['file']).stem}_r{run}.json"
            if target.exists():
                rx.check_kept(json.loads(target.read_text(encoding="utf-8")), fx, PROMPT, run, target)
                continue
            if command["calls"] >= args.max_calls:
                command["stopped"] = f"--max-calls {args.max_calls}"
                print(f"stopped at --max-calls {args.max_calls}; run the command again to continue")
                return finish(1)
            if command["calls"]:
                sleep(MIN_INTERVAL_S)
            command["calls"] += 1
            try:
                record = rx.run_photo(fx, data_dir, PROMPT, settings)
            except ModelCallError as error:
                command["stopped"] = f"no answer for {fx['photo_id']} r{run}"
                print(f"{fx['photo_id']:24} r{run} no answer ({str(error).replace(key, '***')[:200]}); stopped")
                return finish(1)
            record["run"] = run
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            whisky = "rejected" if record["output"] is None else len(record["output"]["items"])
            print(f"{fx['photo_id']:24} r{run} whisky rows {whisky}  other {len(record['other_items'] or [])}  "
                  f"{record['latency_ms'] / 1000:.1f}s  attempts {record['attempts']}")
    print(f"done: runs {args.runs}, {command['calls']} calls in this command")
    return finish(0)


if __name__ == "__main__":
    raise SystemExit(main())
