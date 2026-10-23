"""Hybrid extraction: photo + cached CLOVA lines -> items with source lines (ai/docs/e2e_plan.md).

    python ai/ocr/hybrid.py --set val --tag val_v1 --runs 1
    python ai/ocr/hybrid.py --set val --tag smoke --runs 1 --photos 007_bokchun_03.jpg
    python ai/eval/score.py --set val_v1_1 ai/runs/<date>_e2e/hybrid_val_v1

Same model, thinking level and retry policy as E1 (condition A2). The input is the
prepared photo (same bytes as E1) plus the rebuilt CLOVA lines in P12's format
(`L012 [x0,y0,x1,y1] text`, table detection off). No new CLOVA call is made: a photo
without an OCR cache is an error. Each item also returns `source_lines` (OCR line ids
for the name and the price), and each record stores the missed-output check: OCR lines
that look like prices and that no item cites. API calls (retries included) are capped
per run; past the cap the run stops.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from PIL import Image
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
import extract  # noqa: E402
from extract import (CONDITIONS, MAX_ATTEMPTS, MIME_TYPES, REQUEST_TIMEOUT_S, WALL_TIMEOUT_S,  # noqa: E402
                     _create_with_deadline, _is_transient, _raw_response, data_dir, genai, make_client,
                     prepare_image)

from clova import load_cached, set_photos  # noqa: E402
from lines import GAP_FACTOR, Line, build_lines, format_lines, image_size  # noqa: E402

CONDITION = "A2"  # E1 setting: gemini-3.5-flash-lite, thinking medium
CALL_LIMIT = 80  # API calls per run, retries included (e2e_plan.md)
USER_HEADER = "메뉴판 사진 한 장과, 같은 사진의 OCR 줄 목록이다. 규칙에 따라 항목을 추출해."
LINE_ID = re.compile(r"^L(\d{3,})$")


class SourceLines(BaseModel):
    name: list[str]
    price: list[str]


class HybridItem(BaseModel):
    raw_name: str
    price_krw: Optional[int]
    pour_ml: Optional[int]
    unit: Optional[Literal["glass", "bottle"]]
    source_lines: SourceLines


class HybridExtraction(BaseModel):
    items: list[HybridItem]


class CallLimitReached(RuntimeError):
    pass


def prompt_path(version: str) -> Path:
    return Path(__file__).with_name(f"hybrid_prompt_{version}.md")


# ---------- OCR input ----------

def ocr_lines(stem: str, gap: float = GAP_FACTOR) -> tuple[list[Line], tuple[float, float], dict]:
    """Rebuilt CLOVA lines (table detection off), the box scale and the cache meta."""
    rec = load_cached(stem, "off")
    if rec is None:
        raise FileNotFoundError(f"no OCR cache for {stem} (table-off); hybrid makes no CLOVA call")
    resp = rec["response"]
    sent_size = rec["meta"].get("sent_size")  # boxes are in the pixels of the image sent
    if sent_size is None:
        with Image.open(data_dir() / "prepared" / rec["meta"]["prepared_image"]) as im:
            sent_size = im.size
    return build_lines(resp, gap), image_size(resp, tuple(sent_size)), rec["meta"]


def user_text(lines: list[Line], size: tuple[float, float]) -> str:
    return f"{USER_HEADER}\n\n<ocr_lines>\n{format_lines(lines, size)}\n</ocr_lines>"


def line_id(i: int) -> str:
    """0-based index -> the id format_lines prints ("L001")."""
    return f"L{i + 1:03d}"


# ---------- missed-output check (e2e_plan.md, 누락 감지) ----------

_CURRENCY = re.compile(r"(?i)krw|won|[₩w원k]")
_SEPARATORS = re.compile(r"[/|\-~\s]+")
_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+|\d+\.\d{1,3}|\d+")


def _price_value_ok(token: str) -> bool:
    if "," in token:
        return True
    if "." in token:
        return 1 <= float(token) <= 999
    value = int(token)
    return 10 <= value <= 999 or (1000 <= value <= 9_999_999 and not 1900 <= value <= 2030)


def price_like(text: str) -> bool:
    """True when the line is only price numbers (with currency marks and separators)."""
    rest = _SEPARATORS.sub(" ", _CURRENCY.sub(" ", text)).split()
    if not rest:
        return False
    if not all(_NUMBER.fullmatch(tok) for tok in rest):
        return False
    return any(_price_value_ok(tok) for tok in rest)


def cited_ids(items: list[dict]) -> set[str]:
    return {i for it in items for key in ("name", "price") for i in (it.get("source_lines") or {}).get(key, [])}


def source_check(items: list[dict], lines: list[Line]) -> dict:
    ids = [line_id(i) for i in range(len(lines))]
    cited = cited_ids(items)
    price_ids = [i for i, ln in zip(ids, lines) if price_like(ln.text)]
    uncited = [i for i in price_ids if i not in cited]
    return {
        "n_lines": len(lines),
        "price_like_lines": len(price_ids),
        "uncited_price_lines": len(uncited),
        "uncited": uncited,
        "flag_missing": len(uncited) >= max(4, 0.2 * len(price_ids)),
        "invalid_refs": sorted(cited - set(ids)),
        "items_without_name_source": sum(not (it.get("source_lines") or {}).get("name") for it in items),
    }


# ---------- model call ----------

class Budget:
    def __init__(self, limit: int = CALL_LIMIT):
        self.limit = limit
        self.calls = 0

    def take(self) -> None:
        if self.calls >= self.limit:
            raise CallLimitReached(f"API call limit {self.limit} reached; stopping (e2e_plan.md)")
        self.calls += 1


def call_hybrid(image_path: Path, text: str, prompt: str, budget: Budget, client=None) -> dict:
    """One photo + OCR lines call with E1's model settings and retry policy."""
    model, thinking_level = CONDITIONS[CONDITION]
    client = client or make_client()
    prepared = prepare_image(Path(image_path))
    image_bytes = prepared.read_bytes()
    request = dict(
        model=model,
        system_instruction=prompt,
        input=[
            {"type": "text", "text": text},
            {"type": "image", "data": base64.b64encode(image_bytes).decode("ascii"),
             "mime_type": MIME_TYPES[prepared.suffix.lower()]},
        ],
        response_format={"type": "text", "mime_type": "application/json",
                         "schema": HybridExtraction.model_json_schema()},
        generation_config={"thinking_level": thinking_level},
        store=False,
    )
    attempts = 0
    while True:
        budget.take()
        attempts += 1
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        try:
            interaction = _create_with_deadline(client, request)
            break
        except Exception as exc:
            if not _is_transient(exc) or attempts >= MAX_ATTEMPTS:
                raise
            wait = min(60, 5 * 2 ** (attempts - 1))
            print(f"    retry {attempts}/{MAX_ATTEMPTS - 1} after {type(exc).__name__} (wait {wait}s)",
                  file=sys.stderr, flush=True)
            if isinstance(exc, extract.HardTimeout):
                client = make_client()
            time.sleep(wait)
    latency_ms = round((time.perf_counter() - t0) * 1000)

    raw = interaction.output_text or ""
    parsed, parse_error = None, None
    try:
        parsed = HybridExtraction.model_validate_json(raw).model_dump()
    except Exception as exc:  # pydantic ValidationError
        parse_error = str(exc)
    usage = interaction.usage
    return {
        "condition": "hybrid",
        "model": model,
        "thinking_level": thinking_level,
        "sdk": f"google-genai {genai.__version__}",
        "api": "interactions",
        "store": False,
        "retry_policy": f"own retries x{MAX_ATTEMPTS}, SDK retries off, timeout {REQUEST_TIMEOUT_S}s, wall {WALL_TIMEOUT_S}s",
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
        "raw_text": raw,
        "raw_response": _raw_response(interaction),
    }


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", dest="label_set", choices=["val", "test", "final"], default="val")
    parser.add_argument("--photos", nargs="+")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--first-run", type=int, default=1, help="number of the first run (r2, r3 later)")
    parser.add_argument("--prompt", default="v1", help="hybrid_prompt_<version>.md")
    parser.add_argument("--tag", required=True, help="run dir name part, e.g. val_v1, test_v1")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--limit", type=int, default=CALL_LIMIT, help="API calls per run (retries included)")
    args = parser.parse_args()

    prompt = prompt_path(args.prompt).read_text(encoding="utf-8")
    photos = set_photos(args.label_set, args.photos)
    inputs = {p.stem: ocr_lines(p.stem) for p in photos}  # fail early on a missing OCR cache
    prepared = {p.name: prepare_image(p) for p in photos}

    run_dir = REPO_ROOT / "ai" / "runs" / f"{args.date}_e2e" / f"hybrid_{args.tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    model, thinking = CONDITIONS[CONDITION]
    write_json(run_dir / "manifest.json", {
        "condition": "hybrid", "model": model, "thinking_level": thinking,
        "label_set": args.label_set, "runs": list(range(args.first_run, args.first_run + args.runs)),
        "prompt_version": args.prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "gap_factor": GAP_FACTOR, "ocr_variant": "off", "call_limit": args.limit,
        "photos": {p.name: {"n_lines": len(inputs[p.stem][0]), "prepared": prepared[p.name].name,
                            "ocr_latency_ms": inputs[p.stem][2]["latency_ms"]} for p in photos},
        "api_tier": "free (inputs may be used to improve Google products)",
        "written_at": datetime.now(timezone.utc).isoformat(),
    })

    client = make_client()
    budget = Budget(args.limit)
    runs = range(args.first_run, args.first_run + args.runs)
    total, done = len(runs) * len(photos), 0
    for k in runs:
        for photo in photos:
            done += 1
            out = run_dir / f"{photo.stem}_r{k}.json"
            if out.exists():
                print(f"[{done}/{total}] skip {out.name}")
                continue
            lines, size, meta = inputs[photo.stem]
            text = user_text(lines, size)
            try:
                record = call_hybrid(photo, text, prompt, budget, client)
                items = record["output"]["items"] if record["output"] else []
                record["source_check"] = source_check(items, lines)
                status = f"{len(items)} items" if record["output"] else "PARSE ERROR"
                sc = record["source_check"]
                print(f"[{done}/{total}] r{k} {photo.name}: {status}, in {record['input_tokens']} "
                      f"out {record['output_tokens']} thought {record['thought_tokens']}, {record['latency_ms']} ms, "
                      f"uncited price lines {sc['uncited_price_lines']}/{sc['price_like_lines']}"
                      f"{' FLAG' if sc['flag_missing'] else ''}", flush=True)
            except CallLimitReached as exc:
                print(f"STOP: {exc} (calls so far {budget.calls})")
                break
            except Exception as exc:  # recorded and scored as empty
                record = {"condition": "hybrid", "output": None,
                          "error": f"{type(exc).__name__}: {exc}",
                          "traceback": traceback.format_exc(limit=3),
                          "started_at": datetime.now(timezone.utc).isoformat()}
                print(f"[{done}/{total}] r{k} {photo.name}: ERROR {record['error']}")
                out = out.with_name(out.stem + ".error.json")
            record.update({"run": k, "source_image": photo.name, "prompt_version": args.prompt,
                           "user_text": text, "n_lines": len(lines), "gap_factor": GAP_FACTOR,
                           "ocr_variant": "off", "ocr_latency_ms": meta["latency_ms"]})
            write_json(out, record)
        else:
            continue
        break
    print(f"API calls this run: {budget.calls} (limit {budget.limit})")


if __name__ == "__main__":
    main()
