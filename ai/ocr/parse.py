# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-14, P12). Reviewed by Jinwoo Park.
"""Stage 2: OCR lines + boxes -> items with a text LLM (ai/docs/p12_plan.md).

    python ai/ocr/parse.py --set val --tag val_v1 --runs 3
    python ai/ocr/parse.py --set val --tag pilot --runs 1 --photos 007_bokchun_03.jpg
    python ai/eval/score.py --set val ai/runs/<date>_p12_clova/val_v1_parse

Same model, thinking level, output schema and retry policy as E1 (condition A2),
but no image: the input is the rebuilt OCR lines from the CLOVA cache
(clova.py must have run first). Writes <run_dir>/<photo_stem>_r<k>.json in the
score.py record format, plus manifest.json. Existing records are skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ai" / "extract"))
import extract  # noqa: E402
from extract import (CONDITIONS, MAX_ATTEMPTS, REQUEST_TIMEOUT_S, WALL_TIMEOUT_S, MenuExtraction,  # noqa: E402
                     _create_with_deadline, _is_transient, _raw_response, data_dir, genai, make_client)

from clova import load_cached, set_photos  # noqa: E402
from lines import GAP_FACTOR, build_lines, format_lines, format_tables, image_size  # noqa: E402

CONDITION = "A2"  # E1 setting: gemini-3.5-flash-lite, thinking medium
USER_HEADER = "아래는 메뉴판 사진 한 장의 OCR 줄 목록이다. 규칙에 따라 항목을 추출해."


def prompt_path(version: str) -> Path:
    return Path(__file__).with_name(f"ocr_parse_prompt_{version}.md")


def ocr_user_text(stem: str, gap: float = GAP_FACTOR, tables: bool = False) -> tuple[str, dict]:
    """User message for one photo from the OCR cache, and the input meta."""
    rec = load_cached(stem, "on" if tables else "off")
    if rec is None:
        raise FileNotFoundError(f"no OCR cache for {stem} (table-{'on' if tables else 'off'})")
    resp = rec["response"]
    sent_size = rec["meta"].get("sent_size")  # boxes are in the pixels of the image sent
    if sent_size is None:
        with Image.open(data_dir() / "prepared" / rec["meta"]["prepared_image"]) as im:
            sent_size = im.size
    size = image_size(resp, tuple(sent_size))
    lines = build_lines(resp, gap)
    text = f"{USER_HEADER}\n\n<ocr_lines>\n{format_lines(lines, size)}\n</ocr_lines>"
    table_text = format_tables(resp) if tables else ""
    if table_text:
        text += f"\n\nOCR 표 인식 결과 (행·열 번호):\n<ocr_tables>\n{table_text}\n</ocr_tables>"
    return text, {"ocr_variant": "on" if tables else "off", "ocr_meta": rec["meta"],
                  "n_lines": len(lines), "gap_factor": gap}


def call_parse(user_text: str, prompt: str, client=None) -> dict:
    """One text-only parse call with E1's model settings and retry policy."""
    model, thinking_level = CONDITIONS[CONDITION]
    client = client or make_client()
    request = dict(
        model=model,
        system_instruction=prompt,
        input=[{"type": "text", "text": user_text}],
        response_format={"type": "text", "mime_type": "application/json",
                         "schema": MenuExtraction.model_json_schema()},
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

    text = interaction.output_text or ""
    parsed, parse_error = None, None
    try:
        parsed = MenuExtraction.model_validate_json(text).model_dump()
    except Exception as exc:  # pydantic ValidationError
        parse_error = str(exc)
    usage = interaction.usage
    return {
        "condition": "OCR+LLM",
        "model": model,
        "thinking_level": thinking_level,
        "sdk": f"google-genai {genai.__version__}",
        "api": "interactions",
        "store": False,
        "retry_policy": f"own retries x{MAX_ATTEMPTS}, SDK retries off, timeout {REQUEST_TIMEOUT_S}s, wall {WALL_TIMEOUT_S}s",
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
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


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", dest="label_set", choices=["val", "test"], default="val")
    parser.add_argument("--photos", nargs="+")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--prompt", default="v1", help="ocr_parse_prompt_<version>.md")
    parser.add_argument("--gap", type=float, default=GAP_FACTOR, help="column split gap (x line height)")
    parser.add_argument("--tables", action="store_true", help="use the table-on OCR response + cell list")
    parser.add_argument("--tag", required=True, help="run dir name part, e.g. val_v1, test")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    prompt = prompt_path(args.prompt).read_text(encoding="utf-8")
    photos = set_photos(args.label_set, args.photos)
    inputs = {p.stem: ocr_user_text(p.stem, args.gap, args.tables) for p in photos}  # fail early on missing cache

    run_dir = REPO_ROOT / "ai" / "runs" / f"{args.date}_p12_clova" / f"{args.tag}_parse"
    run_dir.mkdir(parents=True, exist_ok=True)
    model, thinking = CONDITIONS[CONDITION]
    write_json(run_dir / "manifest.json", {
        "condition": "OCR+LLM", "model": model, "thinking_level": thinking,
        "label_set": args.label_set, "runs": args.runs,
        "prompt_version": args.prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "gap_factor": args.gap, "ocr_variant": "on" if args.tables else "off",
        "photos": {p.name: {"n_lines": inputs[p.stem][1]["n_lines"],
                            "ocr_latency_ms": inputs[p.stem][1]["ocr_meta"]["latency_ms"]} for p in photos},
        "api_tier": "free (inputs may be used to improve Google products)",
        "written_at": datetime.now(timezone.utc).isoformat(),
    })

    client = make_client()
    total, done = args.runs * len(photos), 0
    for k in range(1, args.runs + 1):
        for photo in photos:
            done += 1
            out = run_dir / f"{photo.stem}_r{k}.json"
            if out.exists():
                print(f"[{done}/{total}] skip {out.name}")
                continue
            user_text, meta = inputs[photo.stem]
            try:
                record = call_parse(user_text, prompt, client)
                status = f"{len(record['output']['items'])} items" if record["output"] else "PARSE ERROR"
                print(f"[{done}/{total}] r{k} {photo.name}: {status}, in {record['input_tokens']} "
                      f"out {record['output_tokens']} thought {record['thought_tokens']}, {record['latency_ms']} ms")
            except Exception as exc:  # recorded and scored as empty
                record = {"condition": "OCR+LLM", "output": None,
                          "error": f"{type(exc).__name__}: {exc}",
                          "traceback": traceback.format_exc(limit=3),
                          "started_at": datetime.now(timezone.utc).isoformat()}
                print(f"[{done}/{total}] r{k} {photo.name}: ERROR {record['error']}")
                out = out.with_name(out.stem + ".error.json")
            record.update({"run": k, "source_image": photo.name, "prompt_version": args.prompt,
                           "user_text": user_text, **{kk: v for kk, v in meta.items() if kk != "ocr_meta"},
                           "ocr_latency_ms": meta["ocr_meta"]["latency_ms"]})
            write_json(out, record)


if __name__ == "__main__":
    main()
