"""Run the P14 experiment (ai/docs/experiment_p14.md): photos x runs x conditions.

    python ai/extract/run_experiment.py                      # 9 photos x 5 runs x A/A2/B
    python ai/extract/run_experiment.py --tag pilot --runs 1 --photos 007_bokchun_03.jpg

Writes ai/runs/<date>[_<tag>]_<condition>/<photo_stem>_r<k>.json plus manifest.json.
Existing records are skipped, so an interrupted run can be resumed with the same
arguments. Calls are ordered run -> condition -> photo so drift over time is spread
across conditions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

from extract import (CONDITIONS, PROMPT_VERSION, REPO_ROOT, call_model, load_prompt,
                     data_dir, genai, make_client, prepare_image, sha256_file)

LABELS_PATH = REPO_ROOT / "eval" / "labels_v1.json"


def eval_photos(names: list[str] | None) -> list[Path]:
    photo_dir = data_dir() / "eval_photos"
    mapping = json.loads((photo_dir / "photo_map.json").read_text(encoding="utf-8"))["map"]
    chosen = names or sorted(mapping)
    unknown = [n for n in chosen if n not in mapping]
    if unknown:
        raise SystemExit(f"not in photo_map.json: {unknown}")
    return [photo_dir / n for n in chosen]


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--conditions", nargs="+", default=list(CONDITIONS), choices=list(CONDITIONS))
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--photos", nargs="+", help="eval photo filenames (default: all 9)")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--tag", help="extra name part, e.g. pilot")
    args = parser.parse_args()

    photos = eval_photos(args.photos)
    prepared = {p.name: prepare_image(p) for p in photos}  # once per photo, before any call
    prefix = args.date + (f"_{args.tag}" if args.tag else "")
    run_dirs = {c: REPO_ROOT / "ai" / "runs" / f"{prefix}_{c}" for c in args.conditions}

    for cond, run_dir in run_dirs.items():
        run_dir.mkdir(parents=True, exist_ok=True)
        model, thinking = CONDITIONS[cond]
        write_json(run_dir / "manifest.json", {
            "condition": cond, "model": model, "thinking_level": thinking,
            "sdk": f"google-genai {genai.__version__}", "api": "interactions", "store": False,
            "temperature": 1.0, "media_resolution": "default",
            "prompt_version": PROMPT_VERSION, "prompt_sha256": hashlib.sha256(load_prompt().encode("utf-8")).hexdigest(),
            "labels_sha256": sha256_file(LABELS_PATH),
            "runs": args.runs,
            "photos": {name: {"prepared": p.name, "prepared_sha256": sha256_file(p)}
                       for name, p in prepared.items()},
            "api_tier": "free (inputs may be used to improve Google products)",
            "written_at": datetime.now(timezone.utc).isoformat(),
        })

    client = make_client()
    total = args.runs * len(run_dirs) * len(photos)
    done = 0
    for k in range(1, args.runs + 1):
        for cond, run_dir in run_dirs.items():
            for photo in photos:
                done += 1
                out = run_dir / f"{photo.stem}_r{k}.json"
                if out.exists():
                    print(f"[{done}/{total}] skip {out.relative_to(REPO_ROOT)}")
                    continue
                try:
                    record = call_model(photo, cond, client=client)
                    record["run"] = k
                    status = (f"{len(record['output']['items'])} items" if record["output"]
                              else "PARSE ERROR")
                    tokens = f"in {record['input_tokens']} out {record['output_tokens']} " \
                             f"thought {record['thought_tokens']}"
                    print(f"[{done}/{total}] {cond} r{k} {photo.name}: {status}, {tokens}, "
                          f"{record['latency_ms']} ms")
                except Exception as exc:  # keep going; the failure is recorded and scored as empty
                    record = {"condition": cond, "run": k, "source_image": photo.name,
                              "output": None, "error": f"{type(exc).__name__}: {exc}",
                              "traceback": traceback.format_exc(limit=3),
                              "started_at": datetime.now(timezone.utc).isoformat()}
                    print(f"[{done}/{total}] {cond} r{k} {photo.name}: ERROR {record['error']}")
                    out = out.with_name(out.stem + ".error.json")
                write_json(out, record)


if __name__ == "__main__":
    main()
