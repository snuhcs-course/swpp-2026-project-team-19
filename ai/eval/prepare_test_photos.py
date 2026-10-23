"""Copy the held-out test photos into <data_dir>/eval_photos_test with ASCII names.

    python ai/eval/prepare_test_photos.py <folder with the Drive downloads>

The source folder may hold the three Drive folders (011_미라보, 012_Beck,
013_포레스트) or the photos directly, unzipped. Each photo is found by its Drive
file name (e.g. 011_미라보_04.jpeg), copied byte-for-byte, and listed in
photo_map.json (filename -> photo_id in eval/labels_heldout_v1.json). The script
stops if any of the 14 photos is missing or appears twice. Photos stay outside
the repo.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LABELS = REPO_ROOT / "eval" / "labels_heldout_v1.json"
ASCII_BAR = {"011_미라보": "011_mirabeau", "012_Beck": "012_beck", "013_포레스트": "013_forest"}
EXTS = {".jpg", ".jpeg", ".png"}


def nfc(s: str) -> str:
    # macOS/zip downloads can store Korean file names decomposed (NFD)
    return unicodedata.normalize("NFC", s)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
    from extract import data_dir

    photo_ids = [p["photo_id"] for p in json.loads(LABELS.read_text(encoding="utf-8"))["photos"]]
    found: dict[str, list[Path]] = {pid: [] for pid in photo_ids}
    for f in args.source.rglob("*"):
        if f.is_file() and f.suffix.lower() in EXTS and nfc(f.stem) in found:
            found[nfc(f.stem)].append(f)

    missing = [pid for pid, fs in found.items() if not fs]
    dupes = {pid: [str(x) for x in fs] for pid, fs in found.items() if len(fs) > 1}
    if missing or dupes:
        raise SystemExit(f"missing: {missing}\nduplicates: {dupes}")

    out = data_dir() / "eval_photos_test"
    out.mkdir(parents=True, exist_ok=True)
    mapping = {}
    for pid, (src,) in found.items():
        bar, idx = pid.rsplit("_", 1)
        name = f"{ASCII_BAR[bar]}_{idx}{src.suffix.lower()}"
        shutil.copyfile(src, out / name)
        mapping[name] = pid
    (out / "photo_map.json").write_text(json.dumps(
        {"_note": "filename -> photo_id in eval/labels_heldout_v1.json", "map": mapping},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"copied {len(mapping)} photos to {out}")


if __name__ == "__main__":
    main()
