# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, P12). Reviewed by Jinwoo Park.
"""CLOVA General OCR (V2) calls with a response cache (ai/docs/p12_plan.md).

    python ai/ocr/clova.py --set val                       # all val photos, table off + on
    python ai/ocr/clova.py --set val --photos 007_bokchun_03.jpg --variants off

The invoke URL and secret are read only from CLOVA_OCR_INVOKE_URL and
CLOVA_OCR_SECRET in the repo .env; neither is printed or written anywhere.
Raw responses go to <data_dir>/ocr_cache/<stem>__table-<off|on>.json (outside the
repo). Per-call latency is appended to ai/runs/<date>_p12_clova/ocr_calls.json.
The photo sent is extract.prepare_image's output, the same bytes E1 used.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
from extract import data_dir, prepare_image  # noqa: E402

VARIANTS = {"off": False, "on": True}  # variant -> enableTableDetection
FORMATS = {".jpg": "jpg", ".jpeg": "jpg", ".png": "png"}
LANG = "ko"
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
TIMEOUT_S = 120
PHOTO_SETS = {"val": "eval_photos", "test": "eval_photos_test"}


class ClovaError(Exception):
    """Non-retryable CLOVA error. `code` is CLOVA's error code when present (e.g. 0028)."""

    def __init__(self, status: int, code: str | None, message: str):
        super().__init__(f"HTTP {status} code={code}: {message}")
        self.status, self.code = status, code


def credentials() -> tuple[str, str]:
    load_dotenv(REPO_ROOT / ".env")
    url = os.environ.get("CLOVA_OCR_INVOKE_URL", "").strip()
    secret = os.environ.get("CLOVA_OCR_SECRET", "").strip()
    if not url or not secret:
        raise RuntimeError("CLOVA_OCR_INVOKE_URL / CLOVA_OCR_SECRET are not set in .env")
    # The console shows the APIGW invoke URL; the General OCR path ends in /general.
    if not url.rstrip("/").endswith("/general"):
        url = url.rstrip("/") + "/general"
    return url, secret


def cache_path(stem: str, variant: str) -> Path:
    return data_dir() / "ocr_cache" / f"{stem}__table-{variant}.json"


def build_request(image_bytes: bytes, fmt: str, name: str, table: bool) -> dict:
    return {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "lang": LANG,
        "images": [{"format": fmt, "name": name,
                    "data": base64.b64encode(image_bytes).decode("ascii")}],
        "enableTableDetection": table,
    }


def _error_code(resp: httpx.Response) -> tuple[str | None, str]:
    try:
        body = resp.json()
    except ValueError:
        return None, resp.text[:200]
    code = body.get("code") or (body.get("error") or {}).get("errorCode")
    msg = body.get("message") or (body.get("error") or {}).get("message") or ""
    return (str(code) if code is not None else None), str(msg)[:200]


def call_ocr(image_path: Path, table: bool, client: httpx.Client | None = None) -> tuple[dict, dict]:
    """One OCR call. Returns (raw response, call meta). Retries transient errors only."""
    url, secret = credentials()
    prepared = prepare_image(Path(image_path))
    image_bytes = prepared.read_bytes()
    body = build_request(image_bytes, FORMATS[prepared.suffix.lower()], prepared.stem, table)
    headers = {"X-OCR-SECRET": secret, "Content-Type": "application/json"}
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        attempts = 0
        while True:
            attempts += 1
            started_at = datetime.now(timezone.utc).isoformat()
            t0 = time.perf_counter()
            try:
                resp = client.post(url, json=body, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempts >= MAX_ATTEMPTS:
                    raise
                print(f"    retry {attempts} after {type(exc).__name__}", file=sys.stderr)
                time.sleep(5 * attempts)
                continue
            latency_ms = round((time.perf_counter() - t0) * 1000)
            if resp.status_code in RETRY_STATUS and attempts < MAX_ATTEMPTS:
                print(f"    retry {attempts} after HTTP {resp.status_code}", file=sys.stderr)
                time.sleep(5 * attempts)
                continue
            if resp.status_code != 200:
                code, msg = _error_code(resp)
                raise ClovaError(resp.status_code, code, msg)
            break
    finally:
        if own:
            client.close()

    raw = resp.json()
    image = (raw.get("images") or [{}])[0]
    meta = {
        "source_image": Path(image_path).name,
        "prepared_image": prepared.name,
        "prepared_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "table_detection": table,
        "version": "V2",
        "lang": LANG,
        "started_at": started_at,
        "latency_ms": latency_ms,
        "attempts": attempts,
        "infer_result": image.get("inferResult"),
        "n_fields": len(image.get("fields") or []),
        "n_tables": len(image.get("tables") or []),
    }
    return raw, meta


def load_cached(stem: str, variant: str = "off") -> dict | None:
    """Cached record {"meta": ..., "response": ...} or None."""
    path = cache_path(stem, variant)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def ocr_photo(image_path: Path, variant: str, client: httpx.Client | None = None) -> tuple[dict, bool]:
    """Cached OCR for one photo/variant. Returns (record, from_cache)."""
    stem = Path(image_path).stem
    cached = load_cached(stem, variant)
    if cached is not None:
        return cached, True
    raw, meta = call_ocr(image_path, VARIANTS[variant], client)
    record = {"meta": meta, "response": raw}
    path = cache_path(stem, variant)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return record, False


def set_photos(label_set: str, names: list[str] | None = None) -> list[Path]:
    photo_dir = data_dir() / PHOTO_SETS[label_set]
    mapping = json.loads((photo_dir / "photo_map.json").read_text(encoding="utf-8"))["map"]
    chosen = names or sorted(mapping)
    unknown = [n for n in chosen if n not in mapping]
    if unknown:
        raise SystemExit(f"not in photo_map.json: {unknown}")
    return [photo_dir / n for n in chosen]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", dest="label_set", choices=sorted(PHOTO_SETS), default="val")
    parser.add_argument("--photos", nargs="+")
    parser.add_argument("--variants", nargs="+", choices=sorted(VARIANTS), default=["off", "on"])
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    photos = set_photos(args.label_set, args.photos)
    log_path = REPO_ROOT / "ai" / "runs" / f"{args.date}_p12_clova" / "ocr_calls.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []

    skip_on = False
    with httpx.Client(timeout=TIMEOUT_S) as client:
        for photo in photos:
            for variant in args.variants:
                if variant == "on" and skip_on:
                    continue
                try:
                    record, cached = ocr_photo(photo, variant, client)
                except ClovaError as exc:
                    if variant == "on" and exc.code == "0028":
                        print("table detection is off in the console (0028); table-on skipped")
                        skip_on = True
                        continue
                    raise
                m = record["meta"]
                tag = "cache" if cached else f"{m['latency_ms']} ms"
                print(f"{photo.name} table-{variant}: {m['infer_result']}, "
                      f"{m['n_fields']} fields, {m['n_tables']} tables ({tag})")
                if not cached:
                    log.append({"set": args.label_set, **m})
                    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
