"""P30 extraction: the frozen P5 hybrid extraction on the 33 I3 photos, r1-r3 (ai/docs/i3_eval_freeze.md 3장).

    python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --check            # no API call
    python ai/eval/p30_extract.py --out ai/runs/2026-10-30_p30/hybrid_i3 --runs 1 --max-calls 45
    python ai/eval/score.py --set i3 ai/runs/2026-10-30_p30/hybrid_i3
    python ai/eval/i3_match_eval.py --set i3 --catalog full --extraction ai/runs/2026-10-30_p30/hybrid_i3 --run 1 ...

Configuration (frozen, not read from the environment): the deployed server's code path,
`backend/app/extraction/hybrid.py` `extract_menu_hybrid` with `hybrid_prompt_v1.md`, imported
from this checkout and called unchanged: CLOVA OCR lines + the photo -> `gemini-3.5-flash-lite`,
thinking medium, with the server's retry policy (`app.extraction.gemini.call_with_retries`:
6 attempts, backoff 5-60 s on timeouts and HTTP 429/5xx, request 300 s, wall 330 s). Before
anything else the frozen extraction files (FROZEN_CODE) and the scoring code (FROZEN_EVAL:
score.py, e2e_match.py) are checked against their SHA-256, the photo hash file
ai/eval/i3_photo_sha256.json against its frozen SHA-256, and every photo against that file; any
mismatch stops the command.

CLOVA OCR is called at most once per photo and shared by r1-r3. The freeze (1장 "사진 사용
제한") lets the CLOVA cache for the labeling guideline's OCR check be made before P30 and says
"P30 하이브리드 추출은 그 캐시를 그대로 쓴다". The cache is <data_dir>/ocr_cache/
<stem>__table-off.json ({"meta", "response"}, the format of ai/ocr/clova.py that
label_ocr_check.py reads). A photo without a cache gets one CLOVA call through the server's
`call_ocr` (table detection off) and the response is cached the same way; --max-clova-calls
counts its HTTP requests, retries included. A cache whose image cannot be shown to be this photo
stops the command (check_ocr_cache). The cached response
is then handed to `extract_menu_hybrid` through a stand-in HTTP client, so the OCR line table,
prompt and Gemini request are built by the server code itself. The stand-in checks that the
image the server would send is the image the cache was made from. CLOVA latency in the records
is that of the one real call behind the cache; Gemini latency is that of each run's call.

Records go to <out>/<photo stem>_r<k>.json with the model output under "output" (`{"items":
[{raw_name, price_krw, pour_ml, unit, source_lines}]}`), the format score.py and
e2e_match.load_run (i3_match_eval.py --extraction) read. A record that already exists is
skipped, so a rerun resumes. Outcomes per photo:
- answer that the server accepts: "output" = the model output.
- answer that the server rejects (InvalidModelOutputError: bad JSON, schema, converted items):
  the server fails the photo, so "output" is null (scored as an empty output) and the answer
  is kept under "parsed_output" / "raw_text". Not retried: the model did answer.
- no answer after the server's retries (ModelCallError): <stem>_r<k>.error.json, which score.py
  ignores; the next command retries that photo (the freeze retries only when there is no answer).
- call cap (--max-calls, Gemini attempts of this command), quota error (HTTP 429 on a daily
  quota at once, or 429 left after the server's retries) or a CLOVA failure: the command stops
  cleanly without writing that photo; the next command continues there.

<out>/manifest.json keeps the configuration, the frozen file hashes, the code commit, the input
hashes (photos, prepared and sent images, OCR caches) and one entry per command; a command whose
configuration or inputs differ from the manifest's stops. <out>/summary.json has per-run counts
and per-photo latency (CLOVA and Gemini, mean / p50 / p95).

Keys are read only from the repo .env (GEMINI_API_KEY, CLOVA_OCR_INVOKE_URL, CLOVA_OCR_SECRET)
and are never printed or written; error texts are redacted before they are stored.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import io
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.extraction import clova as server_clova  # noqa: E402
from app.extraction import gemini as server_gemini  # noqa: E402
from app.extraction import hybrid as server_hybrid  # noqa: E402
from app.extraction.config import ExtractionSettings  # noqa: E402
from app.extraction.errors import InvalidModelOutputError, ModelCallError, UnsupportedImageError  # noqa: E402
from app.extraction.image import prepare_image  # noqa: E402

FREEZE = "ai/docs/i3_eval_freeze.md 3장 (P5)"
MODEL = "gemini-3.5-flash-lite"
THINKING_LEVEL = "medium"
PROMPT_VERSION = "hybrid-v1"
PROMPT_SHA256 = "b73f15d2b20460fc9e51dc12926e57d09fe3548a47ef8cfc6771c6a3ebe1ac50"  # = ai/ocr/hybrid_prompt_v1.md
# SHA-256 with CRLF read as LF (a Windows checkout may convert line ends). All but clova.py are the
# blobs of 5d49c8a, the frozen commit. clova.py is that of 1e149d4 (#67), which only added the
# `deadline_s` path for business certificates; with deadline_s unset (as here and in hybrid
# extraction on the server) the call is the same as at 5d49c8a.
FROZEN_CODE = {
    "backend/app/extraction/hybrid.py": "d242aff830181225d0b792f7e74c0292ce0ea4c0b7355af30b8891fb43eb5da9",
    "backend/app/extraction/hybrid_prompt_v1.md": PROMPT_SHA256,
    "backend/app/extraction/gemini.py": "b3338ffd00eb9e10db2acee3c05f7550b80a9c7a984966d567c955fc128ec072",
    "backend/app/extraction/config.py": "365b58608aa734260c6dd2562141f3e8ad92d716d0e1623703a706d1999445e4",
    "backend/app/extraction/image.py": "c53bd44536c82421c911bf36f0751da892379f66fd5acf03e09cd36691f852eb",
    "backend/app/extraction/convert.py": "2ffa9a48c3baa4c52df75b70edbdd7c4f05500cf52c9ff34c17d97da9d35bdcf",
    "backend/app/extraction/schema.py": "dd2e22724ac259f7040bee577148df31b60e91257b5c073da84b82d076fa4d64",
    "backend/app/extraction/errors.py": "072d276d56d8f26fd44b8fba3882e754f10cf63d92fb77e029b2e5a486142a1c",
    "backend/app/extraction/clova.py": "ecb321607e56a1779bef6a2a2dc0c91be38d74ecac3ac0e56778f30863c2985c",
}
# The scoring and end-to-end line pairing code the freeze fixes (3장 "채점", 4.2 "종단 줄 맞추기"):
# score.py as committed in the freeze (15b1eff: the 5d49c8a logic plus the `--set i3` label set
# only) and e2e_match.py of 5d49c8a. Checked by every command, --check included, so a change on
# main stops the run before extraction and `--check` right before scoring confirms them again.
FROZEN_EVAL = {
    "ai/eval/score.py": "c5a3a52b45d09d7b8730aef30c54789cc94558d4f16597e9f9a9b6038d966f7b",
    "ai/eval/e2e_match.py": "865e6d18748e12cd18b55914aa8112830d94956557720184d4b55288194d90f5",
}
PHOTO_HASHES = REPO_ROOT / "ai" / "eval" / "i3_photo_sha256.json"
# SHA-256 (CRLF read as LF) of ai/eval/i3_photo_sha256.json as frozen in 15b1eff (#69). The photo
# set is defined by this file, so the file itself is pinned: an edited copy or another --hashes
# file stops the command instead of redefining which photos are checked.
PHOTO_HASHES_SHA256 = "305c4f0e7e9afd45de4b28426cdea980c18618a96da8d0f99e1bdbc0a29ff602"
PHOTO_DIR = "eval_photos_i3"
# Re-encoded OCR bytes (EXIF rotation, downscale) may differ by encoder version for the same photo.
# Such a cache is kept only when its own image decodes to the same pixels as what the server would
# send: same size and a mean absolute difference per channel at most this (0-255 scale).
MAX_REENCODE_PIXEL_DIFF = 2.0
MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
ENV_KEYS = ("GEMINI_API_KEY", "CLOVA_OCR_INVOKE_URL", "CLOVA_OCR_SECRET")
# The stand-in client answers any URL; the real invoke URL and secret are never handed to the replay.
REPLAY_CLOVA = server_clova.ClovaSettings(invoke_url="replay://ocr-cache/general", secret="")
DAILY_QUOTA = re.compile(r"per ?day|daily", re.IGNORECASE)
QUOTA = re.compile(r"RESOURCE_EXHAUSTED|quota", re.IGNORECASE)

EXIT_OK, EXIT_PREFLIGHT, EXIT_STOPPED = 0, 2, 3


class Stop(Exception):
    """Ends the command cleanly; nothing is written for the photo in progress."""


class CallCapReached(Exception):
    pass


class DailyQuota(Exception):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, obj: Any) -> None:
    """Atomic write, so a stopped command never leaves a half record that a rerun would skip."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0-1)."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


# ---- keys -----------------------------------------------------------------------------------


class Secrets:
    """Keys from the repo .env only. Never printed; `redact` removes them from any stored text."""

    def __init__(self, values: dict[str, str | None]):
        self._values = {k: (values.get(k) or "").strip() for k in ENV_KEYS}

    @classmethod
    def from_env_file(cls, path: Path) -> "Secrets":
        from dotenv import dotenv_values
        return cls(dotenv_values(path) if path.exists() else {})

    def has(self, *names: str) -> bool:
        return all(self._values[n] for n in names)

    def get(self, name: str) -> str:
        return self._values[name]

    def redact(self, text: str) -> str:
        for value in sorted(self._values.values(), key=len, reverse=True):
            if len(value) >= 4:
                text = text.replace(value, "***")
        return text

    def clova_settings(self) -> server_clova.ClovaSettings:
        """As app.extraction.clova.load_clova_settings, from the .env values."""
        url = self.get("CLOVA_OCR_INVOKE_URL").rstrip("/")
        if not url.endswith("/general"):
            url += "/general"
        return server_clova.ClovaSettings(invoke_url=url, secret=self.get("CLOVA_OCR_SECRET"))


# ---- inputs ---------------------------------------------------------------------------------


@dataclass
class Photo:
    file: str
    photo_id: str
    sha256: str
    path: Path
    mime: str
    data: bytes = field(repr=False)
    prepared: bytes = field(repr=False)
    prepared_mime: str
    sent_sha256: str  # what the server sends to CLOVA (prepared, or downscaled when >= 8,000 px)
    reencoded: bool  # the bytes sent to CLOVA are not the original file (EXIF rotation or downscale)

    @property
    def stem(self) -> str:
        return Path(self.file).stem


def verify_photos(photo_dir: Path, hashes_path: Path) -> list[Photo]:
    """Every photo of the hash file, checked against it and photo_map.json. Raises Stop on any mismatch.

    The hash file is checked first against PHOTO_HASHES_SHA256, so it cannot redefine the set."""
    if not hashes_path.exists():
        raise Stop(f"photo check failed: {hashes_path} not found")
    digest = sha256_text_file(hashes_path)
    if digest != PHOTO_HASHES_SHA256:
        raise Stop(f"photo check failed (no API call made): {hashes_path.name} SHA-256 {digest[:12]}... "
                   f"!= frozen {PHOTO_HASHES_SHA256[:12]}... (ai/eval/i3_photo_sha256.json of 15b1eff)")
    expected = json.loads(hashes_path.read_text(encoding="utf-8"))["photos"]
    map_path = photo_dir / "photo_map.json"
    if not map_path.exists():
        raise Stop(f"photo check failed: {map_path} not found")
    mapping = json.loads(map_path.read_text(encoding="utf-8"))["map"]
    problems = []
    files = {p["file"] for p in expected}
    if len(files) != len(expected):
        problems.append("hash file lists a file twice")
    if set(mapping) != files:
        problems.append(f"photo_map.json files differ from the hash file: only in map {sorted(set(mapping) - files)}, "
                        f"only in hash file {sorted(files - set(mapping))}")
    stems = [Path(f).stem for f in files]
    if len(set(stems)) != len(stems):
        problems.append("two photos share a file stem (records are named by stem)")
    photos = []
    for p in sorted(expected, key=lambda p: p["file"]):
        path = photo_dir / p["file"]
        if mapping.get(p["file"], p["photo_id"]) != p["photo_id"]:
            problems.append(f"{p['file']}: photo_map.json says {mapping[p['file']]!r}, hash file {p['photo_id']!r}")
        mime = MIME_TYPES.get(path.suffix.lower())
        if mime is None:
            problems.append(f"{p['file']}: unsupported extension")
            continue
        if not path.exists():
            problems.append(f"{p['file']}: missing")
            continue
        data = path.read_bytes()
        digest = sha256_bytes(data)
        if digest != p["sha256"]:
            problems.append(f"{p['file']}: SHA-256 {digest[:12]}... != frozen {p['sha256'][:12]}...")
            continue
        try:
            prepared, prepared_mime = prepare_image(data, mime)
        except UnsupportedImageError as error:
            problems.append(f"{p['file']}: {error}")
            continue
        sent, _, _ = server_clova.ocr_image(prepared, prepared_mime)
        photos.append(Photo(p["file"], p["photo_id"], digest, path, mime, data, prepared, prepared_mime,
                            sha256_bytes(sent), sent != data))
    if problems:
        raise Stop("photo check failed (no API call made):\n  " + "\n  ".join(problems))
    return photos


def check_frozen_code(repo: Path) -> dict[str, str]:
    """Frozen extraction files, prompt, and the scoring code (FROZEN_EVAL). Raises Stop on a change."""
    actual = {rel: sha256_text_file(repo / rel) for rel in FROZEN_CODE}
    diff = [rel for rel, digest in actual.items() if digest != FROZEN_CODE[rel]]
    if diff:
        raise Stop(f"frozen extraction files changed (no API call made): {', '.join(diff)}")
    scoring = {rel: sha256_text_file(repo / rel) if (repo / rel).exists() else None for rel in FROZEN_EVAL}
    diff = [rel for rel, digest in scoring.items() if digest != FROZEN_EVAL[rel]]
    if diff:
        raise Stop(f"frozen scoring files changed (no API call made): {', '.join(diff)}")
    prompt_sha = sha256_bytes(server_hybrid.load_prompt().encode("utf-8"))
    if server_hybrid.PROMPT_VERSION != PROMPT_VERSION or prompt_sha != PROMPT_SHA256:
        raise Stop(f"prompt {server_hybrid.PROMPT_VERSION} {prompt_sha[:12]}... is not the frozen {PROMPT_VERSION}")
    return actual


def git_info(repo: Path) -> dict[str, Any]:
    def run(*cmd: str) -> str | None:
        try:
            return subprocess.run(["git", "-C", str(repo), *cmd], capture_output=True, text=True,
                                  check=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    status = run("status", "--porcelain", "--", "backend/app/extraction", "ai/eval/p30_extract.py")
    return {"commit": run("rev-parse", "HEAD"), "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
            "uncommitted_changes": None if status is None else [line for line in status.splitlines() if line]}


# ---- CLOVA ----------------------------------------------------------------------------------


def ocr_cache_path(data_dir: Path, photo: Photo) -> Path:
    return data_dir / "ocr_cache" / f"{photo.stem}__table-off.json"


def pixel_diff(a: bytes, b: bytes) -> float | None:
    """Mean absolute difference per RGB channel (0-255), or None when the pixel sizes differ."""
    from PIL import Image, ImageChops, ImageStat

    with Image.open(io.BytesIO(a)) as ia, Image.open(io.BytesIO(b)) as ib:
        if ia.size != ib.size:
            return None
        diff = ImageChops.difference(ia.convert("RGB"), ib.convert("RGB"))
        return statistics.mean(ImageStat.Stat(diff).mean)


def regenerate_hint(photo: Photo, data_dir: Path) -> str:
    return (f"; delete {ocr_cache_path(data_dir, photo).relative_to(data_dir)} to make a new cache "
            "(one CLOVA call)")


def check_ocr_cache(record: dict, photo: Photo, data_dir: Path) -> dict:
    """Is the cache for the image the server sends? Raises Stop when it is for another image or
    when that cannot be shown.

    The exact check is the cache's `sent_sha256` against the bytes the server sends. When the
    server sends the original file bytes, a different hash is a different image. When it sends
    re-encoded bytes (EXIF rotation, downscale), an encoder version change can alter the bytes of
    the same photo, so a different hash is kept only with provenance: a cache this runner made
    records `source_sha256`, which must be the verified photo's; a cache from ai/ocr/clova.py
    (freeze 1장) names the image it sent (`sent_image`, under <data_dir>/prepared or
    prepared_ocr), which must still hash to `sent_sha256` and decode to the same pixels as what
    the server would send (MAX_REENCODE_PIXEL_DIFF).
    """
    meta = record.get("meta") or {}
    if meta.get("table_detection") not in (None, False):
        raise Stop(f"{photo.file}: OCR cache was made with table detection on")
    result = server_clova.image_result(record.get("response") or {})
    if result.get("inferResult") != "SUCCESS":
        raise Stop(f"{photo.file}: OCR cache inferResult is {result.get('inferResult')!r}")
    if meta.get("source_image") not in (None, photo.file):
        raise Stop(f"{photo.file}: OCR cache is for {meta.get('source_image')!r}" + regenerate_hint(photo, data_dir))
    if meta.get("source_sha256") not in (None, photo.sha256):
        raise Stop(f"{photo.file}: OCR cache was made from another photo (source_sha256 differs)"
                   + regenerate_hint(photo, data_dir))
    cached = meta.get("sent_sha256")
    if cached is None:
        return {"image_check": "unverified (cache has no sent_sha256)"}
    if cached == photo.sent_sha256:
        return {"image_check": "same image"}
    if not photo.reencoded:
        raise Stop(f"{photo.file}: OCR cache was made from another image (sent_sha256 differs)")
    if meta.get("source_sha256") == photo.sha256:
        return {"image_check": "re-encoded bytes differ; cache made from the verified photo (source_sha256)"}
    sent_name = meta.get("sent_image")
    sent_path = data_dir / ("prepared_ocr" if meta.get("resized") else "prepared") / sent_name if sent_name else None
    if sent_path is None or not sent_path.is_file():
        raise Stop(f"{photo.file}: re-encoded OCR bytes differ and the cache's sent image is not on disk to "
                   "check" + regenerate_hint(photo, data_dir))
    sent_bytes = sent_path.read_bytes()
    if sha256_bytes(sent_bytes) != cached:
        raise Stop(f"{photo.file}: {sent_path.name} no longer hashes to the cache's sent_sha256"
                   + regenerate_hint(photo, data_dir))
    server_sent, _, _ = server_clova.ocr_image(photo.prepared, photo.prepared_mime)
    diff = pixel_diff(sent_bytes, server_sent)
    if diff is None or diff > MAX_REENCODE_PIXEL_DIFF:
        what = "a different pixel size" if diff is None else f"mean pixel difference {diff:.2f}"
        raise Stop(f"{photo.file}: the cache's sent image has {what} from what the server would send"
                   + regenerate_hint(photo, data_dir))
    return {"image_check": f"re-encoded bytes differ; same pixels as the cache's sent image "
                           f"(mean difference {diff:.2f})"}


class Budget:
    def __init__(self, limit: int, what: str):
        self.limit, self.what, self.used = limit, what, 0

    def take(self) -> None:
        if self.used >= self.limit:
            raise CallCapReached(f"{self.what} call cap {self.limit} reached")
        self.used += 1


class CountedHttp:
    """httpx stand-in in front of the client the server's call_ocr uses: every HTTP request, the
    server's retries included, takes one from the CLOVA budget, so --max-clova-calls caps requests."""

    def __init__(self, inner: Any, budget: Budget):
        self.inner, self.budget = inner, budget

    def post(self, url: str, **kwargs: Any) -> Any:
        self.budget.take()  # CallCapReached is not an httpx error, so call_ocr does not retry it
        return self.inner.post(url, **kwargs)


def make_ocr_cache(photo: Photo, path: Path, settings: server_clova.ClovaSettings, client: Any,
                   budget: Budget, secrets: Secrets) -> dict:
    """One CLOVA OCR through the server's call_ocr (its retries count against the budget too);
    cached in the ai/ocr/clova.py format."""
    if budget.used >= budget.limit:
        raise Stop(f"{budget.what} call cap {budget.limit} reached")
    started_at = now()
    own = client is None
    inner = client if client is not None else httpx.Client(timeout=settings.timeout_s)
    try:
        ocr = server_clova.call_ocr(settings, photo.prepared, photo.prepared_mime, CountedHttp(inner, budget))
    except CallCapReached as error:
        raise Stop(f"{error} during the server's retries for {photo.file}") from None
    except server_clova.ClovaOCRError as error:
        raise Stop(f"CLOVA OCR failed for {photo.file}: {secrets.redact(str(error))}") from None
    finally:
        if own:
            inner.close()
    sent, _, sent_size = server_clova.ocr_image(photo.prepared, photo.prepared_mime)
    image = server_clova.image_result(ocr["response"])
    record = {"meta": {
        "source_image": photo.file, "source_sha256": photo.sha256,
        "prepared_sha256": sha256_bytes(photo.prepared), "sent_sha256": photo.sent_sha256,
        "sent_size": list(sent_size), "resized": sent != photo.prepared,
        "table_detection": False, "version": "V2", "lang": server_clova.LANG, "started_at": started_at,
        "latency_ms": ocr["latencyMs"], "attempts": ocr["attempts"], "infer_result": image.get("inferResult"),
        "n_fields": len(image.get("fields") or []), "n_tables": len(image.get("tables") or []),
        "made_by": "ai/eval/p30_extract.py (backend app.extraction.clova.call_ocr)",
    }, "response": ocr["response"]}
    write_json(path, record)
    return record


class ReplayResponse:
    status_code = 200

    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return copy.deepcopy(self._payload)


class ReplayClova:
    """httpx stand-in for the server's call_ocr: answers with the cached response after checking
    that the request carries the image the cache was checked against."""

    def __init__(self, record: dict, photo: Photo):
        self.record, self.photo, self.requests = record, photo, 0

    def post(self, url: str, json: dict | None = None, headers: dict | None = None) -> ReplayResponse:
        self.requests += 1
        image = json["images"][0]
        if json.get("enableTableDetection") is not False:
            raise Stop("the server asked CLOVA for table detection; the cache is table-off")
        if sha256_bytes(base64.b64decode(image["data"])) != self.photo.sent_sha256:
            raise Stop(f"{self.photo.file}: the server would send other OCR bytes than the preflight checked")
        return ReplayResponse(self.record["response"])


# ---- Gemini ---------------------------------------------------------------------------------


class _CountedInteractions:
    def __init__(self, inner: Any, budget: Budget):
        self.inner, self.budget = inner, budget

    def create(self, **kwargs: Any) -> Any:
        self.budget.take()  # raised inside the server's call: not transient, so no retry
        try:
            return self.inner.interactions.create(**kwargs)
        except Exception as error:
            if server_gemini._status_code(error) == 429 and DAILY_QUOTA.search(str(error)):
                raise DailyQuota(f"{type(error).__name__}: {error}") from None
            raise


class CountingClient:
    """The genai client the server makes, behind the command's call cap and a daily-quota check.
    A daily quota error is raised as non-transient, so the server does not spend its 6 attempts."""

    def __init__(self, inner: Any, budget: Budget):
        self.interactions = _CountedInteractions(inner, budget)


@contextmanager
def counted_gemini(factory: Callable[[ExtractionSettings], Any], budget: Budget):
    """The server replaces its client after a hard timeout (gemini.make_client); count that one too."""
    original = server_gemini.make_client
    server_gemini.make_client = lambda settings: CountingClient(factory(settings), budget)
    try:
        yield
    finally:
        server_gemini.make_client = original


def causes(error: BaseException):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        yield error
        error = error.__cause__ or error.__context__


def stop_reason(error: ModelCallError, secrets: Secrets) -> str | None:
    """Why a failed call stops the command (cap or quota), or None (record the failure)."""
    chain = list(causes(error))
    for cause in chain:
        if isinstance(cause, CallCapReached):
            return str(cause)
        if isinstance(cause, DailyQuota):
            return f"daily quota: {secrets.redact(str(cause))[:300]}"
    for cause in chain:
        if server_gemini._status_code(cause) == 429 or QUOTA.search(str(cause)):
            return f"quota (HTTP 429 after the server's retries): {secrets.redact(str(cause))[:300]}"
    return None


# ---- records --------------------------------------------------------------------------------


def settings_for(api_key: str) -> ExtractionSettings:
    """The deployed values (backend/.env.example, P14 A2); retry and timeouts are the server defaults."""
    return ExtractionSettings(api_key=api_key, model=MODEL, thinking_level=THINKING_LEVEL)


def config_block(settings: ExtractionSettings) -> dict:
    return {
        "freeze": FREEZE,
        "code_path": "backend/app/extraction/hybrid.py extract_menu_hybrid, called unchanged",
        "model": settings.model, "thinking_level": settings.thinking_level,
        "prompt_version": PROMPT_VERSION, "prompt_file": "backend/app/extraction/hybrid_prompt_v1.md",
        "prompt_sha256": PROMPT_SHA256,
        "retry_policy": (f"server call_with_retries: {settings.max_attempts} attempts, backoff 5-60 s on timeouts "
                         f"and HTTP 429/5xx, SDK retries off, request {settings.request_timeout_s:g} s, "
                         f"wall {settings.wall_timeout_s:g} s"),
        "ocr": "CLOVA General OCR V2, table detection off, lang ko; one call per photo shared by all runs "
               "(<data_dir>/ocr_cache/<stem>__table-off.json, freeze 1장)",
        "api": "interactions, store=False",
        "server_failure_handling": "InvalidModelOutputError -> output null (server fails the photo); "
                                   "ModelCallError -> .error.json, retried by the next command",
    }


def ocr_info(record: dict, from_cache: bool, path: Path) -> dict:
    meta = record.get("meta") or {}
    return {"latency_ms": meta.get("latency_ms"), "attempts": meta.get("attempts"),
            "started_at": meta.get("started_at"), "from_cache": from_cache, "cache_file": path.name,
            "cache_sha256": sha256_bytes(path.read_bytes())}


def base_record(photo: Photo, run: int, settings: ExtractionSettings, clova: dict) -> dict:
    return {"condition": "hybrid", "config": FREEZE, "run": run, "source_image": photo.file,
            "photo_id": photo.photo_id, "photo_sha256": photo.sha256, "model": settings.model,
            "thinking_level": settings.thinking_level, "prompt_version": PROMPT_VERSION,
            "prompt_sha256": PROMPT_SHA256, "clova": clova}


def meta_fields(meta: dict) -> dict:
    return {"sdk": meta.get("sdk"), "api": meta.get("api"), "store": False,
            "prepared_sha256": meta.get("imageSha256"), "started_at": meta.get("startedAt"),
            "latency_ms": meta.get("latencyMs"), "attempts": meta.get("attempts"), "status": meta.get("status"),
            "input_tokens": meta.get("inputTokens"), "output_tokens": meta.get("outputTokens"),
            "thought_tokens": meta.get("thoughtTokens"), "total_tokens": meta.get("totalTokens"),
            "gemini": {"latency_ms": meta.get("latencyMs"), "attempts": meta.get("attempts"),
                       "started_at": meta.get("startedAt")},
            "ocr_lines": (meta.get("ocr") or {}).get("lines")}


# ---- the command ----------------------------------------------------------------------------


@dataclass
class Clients:
    """Factories for the API clients; tests pass fakes. None means the real client."""
    gemini: Callable[[ExtractionSettings], Any] | None = None
    clova: Any = None


def plan(photos: list[Photo], runs: list[int], out: Path, data_dir: Path) -> dict:
    todo = {k: [p.file for p in photos if not (out / f"{p.stem}_r{k}.json").exists()] for k in runs}
    no_cache = [p.file for p in photos if not ocr_cache_path(data_dir, p).exists()]
    return {"todo": todo, "gemini_calls_min": sum(len(v) for v in todo.values()),
            "clova_calls": len([f for f in no_cache if any(f in v for v in todo.values())]), "no_ocr_cache": no_cache}


def load_manifest(out: Path, config: dict, frozen: dict, photos: list[Photo]) -> dict:
    path = out / "manifest.json"
    inputs = {p.file: {"photo_id": p.photo_id, "sha256": p.sha256, "prepared_sha256": sha256_bytes(p.prepared),
                       "ocr_sent_sha256": p.sent_sha256} for p in photos}
    if not path.exists():
        return {"task": "P30 extraction, I3 test set (33 photos x r1-r3)", "config": config, "frozen_code": frozen,
                "frozen_code_reference": "5d49c8a (clova.py: 1e149d4, deadline_s path only)",
                "frozen_eval": FROZEN_EVAL, "frozen_eval_reference": "score.py: 15b1eff, e2e_match.py: 5d49c8a",
                "photo_hashes_file": "ai/eval/i3_photo_sha256.json",
                "photo_hashes_file_sha256": None, "photos": inputs, "ocr_caches": {}, "commands": []}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for key, value in (("config", config), ("frozen_code", frozen), ("photos", inputs)):
        if manifest.get(key) != value:
            raise Stop(f"{path}: '{key}' differs from this command's; use a new --out for another configuration")
    return manifest


def summarize(out: Path, photos: list[Photo], runs: list[int]) -> dict:
    per_run = {}
    found = {int(m[1]) for f in out.glob("*_r*.json") if (m := re.match(r".+_r(\d+)\.json$", f.name))}
    for k in sorted(set(runs) | found):
        records, errors, missing = [], [], []
        for p in photos:
            path = out / f"{p.stem}_r{k}.json"
            if path.exists():
                records.append(json.loads(path.read_text(encoding="utf-8")))
            else:
                missing.append(p.file)
                if (out / f"{p.stem}_r{k}.error.json").exists():
                    errors.append(p.file)

        def stats(values: list) -> dict:
            values = [v for v in values if v is not None]
            return {"n": len(values), "mean": statistics.mean(values) if values else None,
                    "p50": percentile(values, 0.5), "p95": percentile(values, 0.95),
                    "max": max(values) if values else None}

        per_run[f"r{k}"] = {
            "records": len(records), "missing": missing, "no_answer_error_files": errors,
            "server_rejected_output": [r["source_image"] for r in records if r.get("output") is None],
            "retried_calls": sum((r.get("attempts") or 1) - 1 for r in records),
            "items": sum(len((r.get("output") or {}).get("items") or []) for r in records),
            "latency_ms": {"clova": stats([(r.get("clova") or {}).get("latency_ms") for r in records]),
                           "gemini": stats([(r.get("gemini") or {}).get("latency_ms") for r in records])},
        }
    return {"note": "CLOVA latency: the one real call behind each photo's OCR cache (shared by the runs). "
                    "Gemini latency: the successful attempt (server CallResult.latency_ms). Percentiles are nearest-rank.",
            "photos": len(photos), "runs": per_run, "written_at": now()}


def run_command(args: argparse.Namespace, secrets: Secrets, clients: Clients | None = None) -> int:
    clients = clients or Clients()
    out: Path = args.out
    data_dir: Path = args.data_dir
    try:
        frozen = check_frozen_code(REPO_ROOT)
        photos = verify_photos(data_dir / PHOTO_DIR, args.hashes)
        caches = {}
        for p in photos:
            path = ocr_cache_path(data_dir, p)
            if path.exists():
                caches[p.file] = check_ocr_cache(json.loads(path.read_text(encoding="utf-8")), p, data_dir)
    except Stop as stop:
        print(f"STOP: {stop}")
        return EXIT_PREFLIGHT

    todo = plan(photos, args.runs, out, data_dir)
    print(f"photos verified: {len(photos)} (SHA-256 = {args.hashes.name}); frozen code and prompt {PROMPT_VERSION} OK")
    print(f"OCR caches: {len(photos) - len(todo['no_ocr_cache'])}/{len(photos)} present"
          + (f"; CLOVA calls needed: {todo['clova_calls']}" if todo["no_ocr_cache"] else ""))
    for k, files in todo["todo"].items():
        print(f"r{k}: {len(photos) - len(files)} done, {len(files)} to run")
    if args.check:
        print(f"check only: no API call (Gemini calls needed: at least {todo['gemini_calls_min']})")
        return EXIT_OK

    settings = settings_for(secrets.get("GEMINI_API_KEY"))
    config = config_block(settings)
    try:
        manifest = load_manifest(out, config, frozen, photos)
    except Stop as stop:
        print(f"STOP: {stop}")
        return EXIT_PREFLIGHT
    if todo["gemini_calls_min"] and not secrets.has("GEMINI_API_KEY"):
        print("STOP: GEMINI_API_KEY is not set in the repo .env")
        return EXIT_PREFLIGHT
    if todo["clova_calls"] and not secrets.has("CLOVA_OCR_INVOKE_URL", "CLOVA_OCR_SECRET"):
        print(f"STOP: {todo['clova_calls']} photo(s) have no OCR cache and CLOVA keys are not set in the repo .env")
        return EXIT_PREFLIGHT

    manifest["photo_hashes_file_sha256"] = sha256_text_file(args.hashes)
    command = {"started_at": now(), "git": git_info(REPO_ROOT), "argv": sys.argv[1:], "runs": args.runs,
               "max_calls": args.max_calls, "max_clova_calls": args.max_clova_calls, "gemini_calls": 0,
               "clova_calls": 0, "written": [], "skipped": 0, "no_answer": [], "stopped": None}
    manifest["commands"].append(command)
    write_json(out / "manifest.json", manifest)

    gemini_budget = Budget(args.max_calls, "Gemini")
    clova_budget = Budget(args.max_clova_calls, "CLOVA")
    factory = clients.gemini or server_gemini.make_client  # the server's, captured before counted_gemini
    gemini_client = None
    last_call = None
    total = len(args.runs) * len(photos)
    done = 0
    status = EXIT_OK
    try:
        with counted_gemini(factory, gemini_budget):
            for k in args.runs:
                for photo in photos:
                    done += 1
                    path = out / f"{photo.stem}_r{k}.json"
                    if path.exists():
                        command["skipped"] += 1
                        continue
                    cache_path = ocr_cache_path(data_dir, photo)
                    from_cache = cache_path.exists()
                    if from_cache:
                        ocr_record = json.loads(cache_path.read_text(encoding="utf-8"))
                    else:
                        clova_settings = secrets.clova_settings()
                        ocr_record = make_ocr_cache(photo, cache_path, clova_settings, clients.clova, clova_budget,
                                                    secrets)
                        command["clova_calls"] = clova_budget.used
                        caches[photo.file] = check_ocr_cache(ocr_record, photo, data_dir)
                        print(f"  CLOVA {photo.file}: {ocr_record['meta']['latency_ms']} ms -> {cache_path.name}")
                    clova = {**ocr_info(ocr_record, from_cache, cache_path), **caches[photo.file]}
                    known = manifest["ocr_caches"].setdefault(photo.file, clova["cache_sha256"])
                    if known != clova["cache_sha256"]:
                        raise Stop(f"{photo.file}: OCR cache changed since an earlier command of this run dir")

                    if last_call is not None:
                        wait = last_call + args.min_interval - time.monotonic()
                        if wait > 0:
                            time.sleep(wait)
                    if gemini_client is None:
                        gemini_client = CountingClient(factory(settings), gemini_budget)
                    replay = ReplayClova(ocr_record, photo)
                    record = base_record(photo, k, settings, clova)
                    last_call = time.monotonic()
                    try:
                        result = server_hybrid.extract_menu_hybrid(photo.data, photo.mime, REPLAY_CLOVA,
                                                                   settings=settings, client=gemini_client,
                                                                   ocr_client=replay)
                    except InvalidModelOutputError as error:
                        meta = error.meta or {}
                        record.update(meta_fields(meta))
                        record.update({"output": None, "server_result": "failed (InvalidModelOutputError)",
                                       "parse_error": secrets.redact(str(error)), "raw_text": error.raw_text,
                                       "parsed_output": meta.get("rawOutput")})
                        line = "SERVER REJECTED OUTPUT (scored empty)"
                    except ModelCallError as error:
                        reason = stop_reason(error, secrets)
                        command["gemini_calls"] = gemini_budget.used
                        if reason:
                            raise Stop(f"{reason} (at r{k} {photo.file})") from None
                        write_json(path.with_name(f"{photo.stem}_r{k}.error.json"), {
                            **record, "output": None, "server_result": "failed (ModelCallError)",
                            "attempts": error.attempts, "error": secrets.redact(str(error)), "at": now()})
                        command["no_answer"].append(f"r{k} {photo.file}")
                        print(f"[{done}/{total}] r{k} {photo.file}: NO ANSWER after {error.attempts} attempt(s), "
                              "written as .error.json (retried by the next command)")
                        continue
                    else:
                        meta = result["meta"]
                        record.update(meta_fields(meta))
                        record.update({"output": meta["rawOutput"], "server_result": "ok", "parse_error": None,
                                       "flow_items": result["items"], "item_sources": meta.get("itemSources")})
                        line = f"{len(meta['rawOutput']['items'])} items"
                    if replay.requests != 1:
                        raise Stop(f"{photo.file}: expected one OCR request from the server code, got {replay.requests}")
                    write_json(path, record)
                    path.with_name(f"{photo.stem}_r{k}.error.json").unlink(missing_ok=True)
                    command["written"].append(path.name)
                    command["gemini_calls"] = gemini_budget.used
                    print(f"[{done}/{total}] r{k} {photo.file}: {line}, gemini {record['latency_ms']} ms "
                          f"(attempts {record['attempts']}), clova {clova['latency_ms']} ms"
                          f"{' (cache)' if from_cache else ''}", flush=True)
    except Stop as stop:
        command["stopped"] = str(stop)
        print(f"STOP: {stop}")
        status = EXIT_STOPPED
    except KeyboardInterrupt:
        command["stopped"] = "interrupted"
        print("STOP: interrupted")
        status = EXIT_STOPPED
    finally:
        command["gemini_calls"] = gemini_budget.used
        command["clova_calls"] = clova_budget.used
        command["finished_at"] = now()
        write_json(out / "manifest.json", manifest)
        write_json(out / "summary.json", summarize(out, photos, args.runs))
    print(f"API calls this command: Gemini {gemini_budget.used} (cap {args.max_calls}), "
          f"CLOVA {clova_budget.used} (cap {args.max_clova_calls}); records written {len(command['written'])}, "
          f"skipped {command['skipped']}, no answer {len(command['no_answer'])}")
    if status == EXIT_OK and command["no_answer"]:
        status = EXIT_STOPPED
    return status


def default_data_dir() -> Path:
    sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
    from extract import data_dir
    return data_dir()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True, help="run dir, e.g. ai/runs/2026-10-30_p30/hybrid_i3")
    ap.add_argument("--runs", type=int, nargs="+", default=[1, 2, 3], help="run numbers, in this order")
    ap.add_argument("--max-calls", type=int, default=45, help="Gemini API calls (attempts) per command")
    ap.add_argument("--max-clova-calls", type=int, default=33, help="CLOVA HTTP requests per command, the server's retries included (photos without cache)")
    ap.add_argument("--min-interval", type=float, default=4.5, help="seconds between photos' Gemini requests")
    ap.add_argument("--check", action="store_true", help="verify inputs and show what is left; no API call")
    ap.add_argument("--data-dir", type=Path, help="default: BOTTLEMAP_DATA_DIR (repo .env) as ai/extract/extract.py")
    ap.add_argument("--hashes", type=Path, default=PHOTO_HASHES,
                    help="photo hash file; must have the frozen SHA-256 (PHOTO_HASHES_SHA256)")
    ap.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    args = ap.parse_args(argv)
    if any(k < 1 for k in args.runs) or len(set(args.runs)) != len(args.runs):
        ap.error("--runs: distinct numbers >= 1")
    return args


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = parse_args(argv)
    if args.data_dir is None:
        args.data_dir = default_data_dir()
    if not args.out.is_absolute():
        args.out = Path(os.getcwd()) / args.out
    return run_command(args, Secrets.from_env_file(args.env_file))


if __name__ == "__main__":
    sys.exit(main())
