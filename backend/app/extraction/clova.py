"""CLOVA General OCR (V2) for the hybrid extractor, from ai/ocr/clova.py and ai/ocr/lines.py.

One call per photo, table detection off (the E2E hybrid setting). The image sent is the
prepared photo (same bytes as the Gemini call) unless its long side is >= 8,000 px; then a
downscaled JPEG is sent. Line boxes are reported on a 0-1000 scale of the image, so they do
not depend on that downscale. The secret is read from CLOVA_OCR_SECRET and never logged.

With `deadline_s` set (the business certificate OCR, which the app waits for), the whole call,
retries included, stops at that many seconds: the body is sent and read in chunks with the
clock checked between them, each attempt's timeouts are capped by the time left, and no retry
starts that could not finish before it. One socket operation already under way can still run
for up to its timeout, so the worst case is `deadline_s` plus the per-attempt `timeout_s`.
"""

import base64
import io
import json
import logging
import os
import statistics
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from PIL import Image

from app.extraction.errors import ExtractionConfigError

logger = logging.getLogger(__name__)

MAX_LONG_SIDE = 8000
JPEG_QUALITY = 95
LANG = "ko"
RETRY_STATUS = {429, 500, 502, 503, 504}
GAP_FACTOR = 2.5  # ai/ocr/lines.py, tuned on val only (ai/docs/p12_plan.md)
FORMATS = {"image/jpeg": "jpg", "image/png": "png"}

# Replaced in tests so retries do not wait and deadlines can be reached without waiting.
sleep = time.sleep
monotonic = time.monotonic
CHUNK_BYTES = 64 * 1024


class ClovaOCRError(Exception):
    """The OCR call failed (HTTP error, network error after retries, or an unusable response)."""


@dataclass(frozen=True)
class ClovaSettings:
    invoke_url: str
    secret: str
    max_attempts: int = 3
    timeout_s: float = 60
    deadline_s: float | None = None  # wall-clock limit for the whole call, retries included

    def __repr__(self) -> str:  # keep the secret out of logs and tracebacks
        return (
            f"ClovaSettings(max_attempts={self.max_attempts}, timeout_s={self.timeout_s}, "
            f"deadline_s={self.deadline_s})"
        )


def load_clova_settings() -> ClovaSettings:
    missing = [name for name in ("CLOVA_OCR_INVOKE_URL", "CLOVA_OCR_SECRET") if not os.getenv(name, "").strip()]
    if missing:
        raise ExtractionConfigError(f"Missing required OCR environment variables: {', '.join(missing)}")
    url = os.environ["CLOVA_OCR_INVOKE_URL"].strip().rstrip("/")
    # The NCP console shows the APIGW invoke URL; the General OCR path ends in /general.
    if not url.endswith("/general"):
        url += "/general"
    return ClovaSettings(invoke_url=url, secret=os.environ["CLOVA_OCR_SECRET"].strip())


# ---- the call ----


class _DeadlinePassed(Exception):
    pass


def _post_before(client: httpx.Client, settings: ClovaSettings, body: dict, headers: dict, deadline: float):
    """POST `body`, giving up at `deadline` (a `monotonic()` time) while sending or reading."""
    left = deadline - monotonic()
    if left <= 0:
        raise _DeadlinePassed
    data = json.dumps(body, separators=(",", ":")).encode("ascii")

    def chunks():
        for start in range(0, len(data), CHUNK_BYTES):
            if monotonic() > deadline:
                raise _DeadlinePassed
            yield data[start : start + CHUNK_BYTES]

    # With Content-Length set, httpx sends the chunks as one plain body, not chunked encoding.
    request = client.build_request(
        "POST",
        settings.invoke_url,
        content=chunks(),
        headers={**headers, "Content-Length": str(len(data))},
        timeout=httpx.Timeout(min(settings.timeout_s, left)),
    )
    response = client.send(request, stream=True)
    try:
        content = bytearray()
        for chunk in response.iter_bytes():
            content += chunk
            if monotonic() > deadline:
                raise _DeadlinePassed
    finally:
        response.close()
    # The bytes are already decoded, so the new response gets no Content-Encoding header.
    return httpx.Response(response.status_code, content=bytes(content), request=request)


def ocr_image(image: bytes, mime_type: str) -> tuple[bytes, str, tuple[int, int]]:
    """(bytes to send, CLOVA format, pixel size of what is sent)."""
    with Image.open(io.BytesIO(image)) as im:
        size = im.size
        if max(size) < MAX_LONG_SIDE:
            return image, FORMATS[mime_type], size
        scale = (MAX_LONG_SIDE - 1) / max(size)
        new_size = (max(1, round(size[0] * scale)), max(1, round(size[1] * scale)))
        out = io.BytesIO()
        im.convert("RGB").resize(new_size, Image.LANCZOS).save(out, format="JPEG", quality=JPEG_QUALITY)
        return out.getvalue(), "jpg", new_size


def call_ocr(settings: ClovaSettings, image: bytes, mime_type: str, client: httpx.Client | None = None) -> dict:
    """One OCR call on a prepared image. Returns {"response", "sentSize", "latencyMs", "attempts"}.

    Retries timeouts, network errors and HTTP 429/5xx; raises ClovaOCRError otherwise.
    """
    data, fmt, sent_size = ocr_image(image, mime_type)
    body = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "lang": LANG,
        "images": [{"format": fmt, "name": "menu", "data": base64.b64encode(data).decode("ascii")}],
        "enableTableDetection": False,
    }
    headers = {"X-OCR-SECRET": settings.secret, "Content-Type": "application/json"}
    deadline = None if settings.deadline_s is None else monotonic() + settings.deadline_s
    own = client is None
    client = client or httpx.Client(timeout=settings.timeout_s)
    try:
        attempts = 0
        while True:
            attempts += 1
            t0 = time.perf_counter()
            try:
                if deadline is None:
                    response = client.post(settings.invoke_url, json=body, headers=headers)
                else:
                    response = _post_before(client, settings, body, headers, deadline)
                status = response.status_code
                detail = f"HTTP {status}"
            except _DeadlinePassed as exc:
                raise ClovaOCRError(
                    f"CLOVA OCR stopped at its {settings.deadline_s:g} s deadline after {attempts} attempt(s)"
                ) from exc
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                response, status, detail = None, None, type(exc).__name__
            except httpx.HTTPError as exc:  # e.g. a malformed invoke URL: not worth retrying
                raise ClovaOCRError(f"CLOVA OCR request failed: {type(exc).__name__}") from exc
            latency_ms = round((time.perf_counter() - t0) * 1000)
            if status == 200:
                break
            retryable = (status is None or status in RETRY_STATUS) and attempts < settings.max_attempts
            # A retry that would start after the deadline is not made.
            if retryable and (deadline is None or monotonic() + 5 * attempts < deadline):
                logger.warning("CLOVA OCR retry %d/%d after %s", attempts, settings.max_attempts - 1, detail)
                sleep(5 * attempts)
                continue
            raise ClovaOCRError(f"CLOVA OCR failed after {attempts} attempt(s): {detail}")
    finally:
        if own:
            client.close()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ClovaOCRError("CLOVA OCR response is not JSON") from exc
    result = image_result(payload)
    if result.get("inferResult") != "SUCCESS":
        raise ClovaOCRError(f"CLOVA OCR inferResult is {result.get('inferResult')!r}")
    return {"response": payload, "sentSize": list(sent_size), "latencyMs": latency_ms, "attempts": attempts}


# ---- lines (ai/ocr/lines.py) ----


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class Line:
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (min(w.x0 for w in self.words), min(w.y0 for w in self.words),
                max(w.x1 for w in self.words), max(w.y1 for w in self.words))


def image_result(response: dict) -> dict:
    images = response.get("images") or []
    return images[0] if images else {}


def _word(f: dict) -> Word:
    vs = (f.get("boundingPoly") or {}).get("vertices") or []
    xs = [v.get("x", 0.0) for v in vs] or [0.0]
    ys = [v.get("y", 0.0) for v in vs] or [0.0]
    return Word(f.get("inferText", ""), min(xs), min(ys), max(xs), max(ys))


def _split_gaps(words: list[Word], gap_factor: float) -> list[list[Word]]:
    if len(words) < 2:
        return [words]
    height = statistics.median(w.y1 - w.y0 for w in words) or 1.0
    parts, cur = [], [words[0]]
    for prev, w in zip(words, words[1:]):
        if w.x0 - prev.x1 > gap_factor * height:
            parts.append(cur)
            cur = []
        cur.append(w)
    parts.append(cur)
    return parts


def build_lines(response: dict, gap_factor: float = GAP_FACTOR) -> list[Line]:
    """Fields grouped by lineBreak, then split where the gap exceeds gap_factor x line height."""
    raw, cur = [], []
    for f in image_result(response).get("fields") or []:
        cur.append(_word(f))
        if f.get("lineBreak"):
            raw.append(cur)
            cur = []
    if cur:
        raw.append(cur)
    return [Line(part) for words in raw for part in _split_gaps(words, gap_factor)]


def image_size(response: dict, fallback: tuple[int, int]) -> tuple[float, float]:
    info = image_result(response).get("convertedImageInfo") or {}
    if info.get("width") and info.get("height"):
        return float(info["width"]), float(info["height"])
    return float(fallback[0]), float(fallback[1])


def line_id(i: int) -> str:
    return f"L{i + 1:03d}"


def scaled_box(line: Line, size: tuple[float, float]) -> list[int]:
    w, h = size
    x0, y0, x1, y1 = line.box
    return [round(x0 / w * 1000), round(y0 / h * 1000), round(x1 / w * 1000), round(y1 / h * 1000)]


def ocr_lines_table(lines: list[Line], size: tuple[float, float]) -> list[dict[str, Any]]:
    """[{id, box (0-1000 of the image), text}] in OCR order, the ids the prompt sees."""
    return [{"id": line_id(i), "box": scaled_box(line, size), "text": line.text} for i, line in enumerate(lines)]


def format_lines(table: list[dict[str, Any]]) -> str:
    """`L001 [x0,y0,x1,y1] text`, P12 / E2E format."""
    return "\n".join(f"{row['id']} [{','.join(str(v) for v in row['box'])}] {row['text']}" for row in table)
