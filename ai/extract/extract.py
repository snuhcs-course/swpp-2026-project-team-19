# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-06, PR #10). Reviewed by Jinwoo Park.
"""Menu photo -> structured items with Gemini (P14 PoC).

Settings follow ai/docs/experiment_p14.md. Photos are read from BOTTLEMAP_DATA_DIR
(outside the repo); the API key is read only from GEMINI_API_KEY in the repo .env.

    python ai/extract/extract.py <image> [--condition A|A2|B]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai._gaos.lib.compat_errors import APIConnectionError
from PIL import Image, ImageOps
from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_VERSION = "v1"
PROMPT_PATH = Path(__file__).with_name(f"prompt_{PROMPT_VERSION}.md")
USER_TEXT = "이 메뉴판 사진에서 규칙에 따라 항목을 추출해."

# Condition ID -> (model ID, thinking_level). thinking_level is always sent explicitly.
CONDITIONS = {
    "A": ("gemini-3.5-flash-lite", "minimal"),
    "A2": ("gemini-3.5-flash-lite", "medium"),
    "B": ("gemini-3.6-flash", "medium"),
}
TEMPERATURE_RECORDED = 1.0  # not sent; API default (Gemini 3 docs recommend keeping it)
MEDIA_RESOLUTION_RECORDED = "default (unspecified, 1120 tokens/image)"  # not sent
JPEG_QUALITY = 95
MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 6
REQUEST_TIMEOUT_S = 300  # SDK (read) timeout; slowest normal call so far ~104 s
WALL_TIMEOUT_S = 330  # hard wall-clock cap per attempt: a connection once hung for 50+ min
                      # without tripping the SDK timeout


class HardTimeout(Exception):
    pass


class MenuItem(BaseModel):
    raw_name: str
    price_krw: Optional[int]
    pour_ml: Optional[int]
    unit: Optional[Literal["glass", "bottle"]]


class MenuExtraction(BaseModel):
    items: list[MenuItem]


def data_dir() -> Path:
    load_dotenv(REPO_ROOT / ".env")
    raw = os.environ.get("BOTTLEMAP_DATA_DIR") or "../bottlemap-p14/data"
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_image(src: Path) -> Path:
    """Preprocess a photo once and cache it in <data_dir>/prepared/.

    EXIF orientation present (!= 1): rotate, drop EXIF, re-encode JPEG q95.
    Otherwise: copy the original bytes. Pixel size is never changed.
    An existing prepared file is reused so every call sends identical bytes.
    """
    out_dir = data_dir() / "prepared"
    with Image.open(src) as im:
        orientation = im.getexif().get(0x0112)
        rotate = orientation not in (None, 1)
        dst = out_dir / (src.stem + ".jpg" if rotate else src.name)
        if dst.exists():
            return dst
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tmp")
        if rotate:
            ImageOps.exif_transpose(im).convert("RGB").save(
                tmp, format="JPEG", quality=JPEG_QUALITY
            )
        else:
            shutil.copyfile(src, tmp)
    tmp.replace(dst)
    return dst


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def make_client() -> genai.Client:
    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set in .env")
    # SDK-internal retries off: call_model owns retries so `attempts` is the real count
    return genai.Client(api_key=key, http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=1)))


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (HardTimeout, APIConnectionError, httpx.TimeoutException, httpx.NetworkError)):
        return True
    return _status_code(exc) in RETRY_STATUS


def _status_code(exc: Exception) -> Optional[int]:
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _raw_response(interaction) -> dict:
    """Response dump without echoed request content (image bytes, prompt)."""
    dump = interaction.model_dump(mode="json", exclude_none=True)
    for key in ("input", "system_instruction"):
        dump.pop(key, None)
    if "steps" in dump:
        dump["steps"] = [s for s in dump["steps"] if s.get("type") != "user_input"]
    return dump


def _create_with_deadline(client: genai.Client, request: dict):
    """interactions.create with a hard wall-clock limit. A hung call is abandoned
    in its daemon thread; the caller retries on a fresh client."""
    box: dict = {}

    def run():
        try:
            box["result"] = client.interactions.create(**request, timeout=REQUEST_TIMEOUT_S)
        except BaseException as exc:  # handed to the caller
            box["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(WALL_TIMEOUT_S)
    if worker.is_alive():
        raise HardTimeout(f"no response within {WALL_TIMEOUT_S}s")
    if "error" in box:
        raise box["error"]
    return box["result"]


def call_model(image_path: Path, condition: str, client: Optional[genai.Client] = None) -> dict:
    """One extraction call. Returns a record with output and all metadata."""
    model, thinking_level = CONDITIONS[condition]
    client = client or make_client()
    prepared = prepare_image(Path(image_path))
    image_bytes = prepared.read_bytes()
    prompt = load_prompt()

    request = dict(
        model=model,
        system_instruction=prompt,
        input=[
            {"type": "text", "text": USER_TEXT},
            {
                "type": "image",
                "data": base64.b64encode(image_bytes).decode("ascii"),
                "mime_type": MIME_TYPES[prepared.suffix.lower()],
            },
        ],
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": MenuExtraction.model_json_schema(),
        },
        generation_config={"thinking_level": thinking_level},
        store=False,
    )

    attempts = 0
    while True:
        attempts += 1
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        try:
            interaction = _create_with_deadline(client, request)
            break
        except Exception as exc:  # retry only timeouts, network and transient HTTP errors
            if not _is_transient(exc) or attempts >= MAX_ATTEMPTS:
                raise
            wait = min(60, 5 * 2 ** (attempts - 1))
            print(f"    retry {attempts}/{MAX_ATTEMPTS - 1} after {type(exc).__name__}: "
                  f"{str(exc)[:120]} (wait {wait}s)", file=sys.stderr, flush=True)
            if isinstance(exc, HardTimeout):
                client = make_client()  # don't reuse a client holding a hung connection
            time.sleep(wait)
    latency_ms = round((time.perf_counter() - t0) * 1000)

    text = interaction.output_text or ""
    parsed, parse_error = None, None
    try:
        parsed = MenuExtraction.model_validate_json(text).model_dump()
    except ValidationError as exc:
        parse_error = str(exc)

    usage = interaction.usage
    return {
        "condition": condition,
        "model": model,
        "sdk": f"google-genai {genai.__version__}",
        "retry_policy": f"own retries x{MAX_ATTEMPTS}, SDK retries off, timeout {REQUEST_TIMEOUT_S}s, wall {WALL_TIMEOUT_S}s",
        "api": "interactions",
        "store": False,
        "temperature": TEMPERATURE_RECORDED,
        "thinking_level": thinking_level,
        "media_resolution": MEDIA_RESOLUTION_RECORDED,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "source_image": Path(image_path).name,
        "prepared_image": prepared.name,
        "prepared_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "started_at": started_at,
        "latency_ms": latency_ms,
        "attempts": attempts,
        "status": str(interaction.status),
        "input_tokens": getattr(usage, "total_input_tokens", None),
        "output_tokens": getattr(usage, "total_output_tokens", None),
        "thought_tokens": getattr(usage, "total_thought_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
        "output": parsed,
        "parse_error": parse_error,
        "raw_text": text,
        "raw_response": _raw_response(interaction),
    }


def extract(image_path, model: str = "A") -> dict:
    """extract(image_path, model) -> {"items": [...]}. `model` is a condition ID (A/A2/B)."""
    record = call_model(Path(image_path), model)
    if record["output"] is None:
        raise ValueError(f"unparseable response: {record['parse_error']}")
    return record["output"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image", type=Path)
    parser.add_argument("--condition", default="A", choices=sorted(CONDITIONS))
    parser.add_argument("--out", type=Path, help="write the full record as JSON")
    args = parser.parse_args()

    record = call_model(args.image, args.condition)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {k: v for k, v in record.items() if k not in ("raw_text", "raw_response", "output")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(record["output"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
