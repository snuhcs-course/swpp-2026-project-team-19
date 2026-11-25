"""I5 model ladder: from which model tier do the prices stop slipping? Calls a model per photo.

    python ai/eval/i5_model_ladder.py --stage 0 --out ai/runs/<date>_i5_row_pairing/ladder --check
    python ai/eval/i5_model_ladder.py --stage 0 --out ai/runs/<date>_i5_row_pairing/ladder
    python ai/eval/i5_model_ladder.py --stage 0 --out ai/runs/<date>_i5_row_pairing/ladder --report

Five photos, two conditions, three runs each (30 calls a stage):
  A  the photo only, ai/extract/prompt_v2.md (the image-only prompt the hybrid prompt grew from)
  B  the photo and its OCR lines, backend/app/extraction/hybrid_prompt_v2.md, as the server sends
     them (the same request as extract_menu_hybrid_v2)
The image is the prepared image the hybrid extractor sends. The prompts are not changed per model.

Stage 0 is gemini-3.5-flash-lite through the team's Gemini key (thinking medium), with the
server's request builder. Stages 1-3 go through OpenRouter (chat completions): the same system
prompt, user text and image, `reasoning.effort` medium, the same response schema as a strict
json_schema, `provider.data_collection: deny`, and the cost OpenRouter reports for the call. A
paid stage stops once its records have cost STAGE_COST_LIMIT_USD. Records go to <out>/<model>/<A|B>/<stem>_r<run>.json; an existing record
is kept. A call is tried again once when it fails in transport or its answer is not the schema
(`format_retry` and `failures` in the record); a price error is never retried. A call that gets no
answer twice (503, quota) is logged in <out>/<model>/transport_failures.jsonl, writes no record and
stops the command, so the same command continues later.

Scoring (per call, against the label items of the photo): ai/eval/score.py match_photo (strict,
then lenient, same unit) pairs label items with output rows; B is scored on its `whisky` rows.
  ok       paired and the price is the label's
  wrong    paired and the price is another number
  missing  the label item has no row, or its row has no price
  name_only  score.py could not pair the item, but a left-over row of the same unit with the
           label's price is the item under another spelling (see related_name). Not a price
           failure, so it is not in the pass criterion. If that row has another price, the cell
           is `wrong`.
  extra    output rows that belong to no label item
A wrong price gets a kind (wrong_kind): unit scale, glass/bottle swap, neighbour row, other.
score.py does not read pour_ml; none of the five photos has two glass prices for one name.

tale_07, tale_11 and cheongchun_02 are photos of the frozen I3 set: this compares models and is
not a reason to change a prompt or the code.

`--photos regression` runs the same two conditions on the 15 regression photos and the two photos
the old row rule was written for (복춘_02, Beck_04), scored against the regression fixtures'
expected items; `--max-tokens` and `--cost-limit` set the output cap and the spending limit of
that run. `--prompt-b` runs condition B with another hybrid prompt file (section 10: v2.1);
`--runs` and `--only` choose the run numbers and the photos to call.

API keys are read from the repo .env and are never printed or written.
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
for _p in ("ai/regression", "ai/eval", "ai/extract", "backend"):
    sys.path.insert(0, str(REPO_ROOT / _p))

import i5_row_pairing  # noqa: E402
import run_extraction as rx  # noqa: E402
import score  # noqa: E402
from app.extraction import ExtractionSettings, ModelCallError  # noqa: E402
from app.extraction import hybrid_v2  # noqa: E402
from app.extraction.gemini import build_request, call_with_retries  # noqa: E402
from app.extraction.hybrid import run_ocr, user_text  # noqa: E402
from app.extraction.schema import MenuExtraction  # noqa: E402
from pydantic import ValidationError  # noqa: E402

PHOTOS = (("014_tale_07", "i3"), ("014_tale_11", "i3"), ("011_mirabeau_03", "test_v1_1"),
          ("007_bokchun_01", "val_v1_1"), ("018_cheongchun_02", "i3"))
CONDITIONS = ("A", "B")
RUNS = (1, 2, 3)
PROMPT_A = REPO_ROOT / "ai" / "extract" / "prompt_v2.md"
PROMPT_B: Path | None = None  # set by --prompt-b
USER_TEXT_A = "이 메뉴판 사진에서 규칙에 따라 항목을 추출해."  # ai/extract/extract.py, backend gemini.py
STAGES = {0: {"model": "gemini-3.5-flash-lite", "route": "gemini", "thinking": "medium"},
          1: {"model": "anthropic/claude-haiku-5.5", "route": "openrouter", "thinking": "medium"},
          2: {"model": "google/gemini-3.8-flash", "route": "openrouter", "thinking": "medium"},
          3: {"model": "anthropic/claude-sonnet-5.5", "route": "openrouter", "thinking": "medium"}}
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
STAGE_COST_LIMIT_USD = {1: 3.0, 2: 3.0, 3: 4.0}  # a paid stage stops before the next call at this (stage 3: raised to $4 by Jinwoo, 2026-11-21)
MAX_TOKENS = 20000           # answer and reasoning together, so one call cannot run away
MIN_INTERVAL_S = 4.5
MISSING_LIMIT = 0.05
TRANSPORT_WAIT_S = 30.0  # before the one retry of a call that got no answer (503, network)


def read_lf(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def inputs(fixture: dict, condition: str, data_dir: Path) -> dict:
    """What one call sends: system prompt, user text, prepared image, response model."""
    photo = fixture["photo"]
    path = data_dir / photo["photo_dir"] / photo["file"]
    mime = rx.MIME_TYPES[path.suffix.lower()]
    cache = json.loads((data_dir / "ocr_cache" / f"{path.stem}__table-off.json").read_text(encoding="utf-8"))
    ocr = run_ocr(path.read_bytes(), mime, rx.REPLAY_CLOVA, rx.ReplayOcr(cache))  # no CLOVA call
    if condition == "A":
        prompt, text, model, name = read_lf(PROMPT_A), USER_TEXT_A, MenuExtraction, "ai/extract/prompt_v2.md"
    else:
        prompt, text, model = hybrid_v2.load_prompt(), user_text(ocr["table"]), hybrid_v2.HybridExtractionV2
        name = "backend/app/extraction/hybrid_prompt_v2.md"
        if PROMPT_B:  # --prompt-b: another hybrid prompt file, same request otherwise
            prompt, name = read_lf(PROMPT_B), PROMPT_B.relative_to(REPO_ROOT).as_posix()
    return {"prompt": prompt, "prompt_file": name, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "user_text": text, "image": ocr["prepared"], "mime": ocr["preparedMime"], "response_model": model,
            "image_sha256": hashlib.sha256(ocr["prepared"]).hexdigest(), "ocr_lines": len(ocr["table"])}


def call_gemini(stage: dict, sent: dict, key: str) -> dict:
    settings = ExtractionSettings(api_key=key, model=stage["model"], thinking_level=stage["thinking"], max_attempts=1)
    request = build_request(settings, sent["prompt"], sent["image"], sent["mime"],
                            sent["response_model"].model_json_schema())
    request["input"][0]["text"] = sent["user_text"]
    result = call_with_retries(settings, request)
    interaction, usage = result.interaction, getattr(result.interaction, "usage", None)
    return {"text": getattr(interaction, "output_text", None) or "", "status": str(getattr(interaction, "status", None)),
            "latency_ms": result.latency_ms, "input_tokens": getattr(usage, "total_input_tokens", None),
            "output_tokens": getattr(usage, "total_output_tokens", None),
            "thought_tokens": getattr(usage, "total_thought_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None), "cost_usd": None,
            "structured_output": "response_format schema (Gemini interactions API)"}


class TransportError(Exception):
    pass


def strict_schema(node):
    """The pydantic schema with `additionalProperties: false` on every object (strict json_schema)."""
    if isinstance(node, dict):
        node = {k: strict_schema(v) for k, v in node.items()}
        if node.get("type") == "object":
            node["additionalProperties"] = False
        return node
    return [strict_schema(v) for v in node] if isinstance(node, list) else node


def call_openrouter(stage: dict, sent: dict, key: str) -> dict:
    """One chat completion. Text first, then the image, as the Gemini request orders them.

    `provider.data_collection: deny` keeps the photo away from providers that store or train on
    inputs; `require_parameters` keeps it away from providers that would ignore the schema or the
    reasoning setting. The cost is the one OpenRouter reports in `usage`, not an estimate.
    """
    import base64

    import httpx
    body = {
        "model": stage["model"],
        "messages": [
            {"role": "system", "content": sent["prompt"]},
            {"role": "user", "content": [
                {"type": "text", "text": sent["user_text"]},
                {"type": "image_url", "image_url": {
                    "url": f"data:{sent['mime']};base64,{base64.b64encode(sent['image']).decode('ascii')}"}}]}],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "menu_extraction", "strict": True,
            "schema": strict_schema(sent["response_model"].model_json_schema())}},
        "reasoning": {"effort": stage["thinking"]},
        "max_tokens": stage.get("max_tokens", MAX_TOKENS),
        "provider": {"data_collection": "deny", "require_parameters": True},
        "usage": {"include": True},
    }
    t0 = time.perf_counter()
    try:
        response = httpx.post(OPENROUTER_URL, json=body, timeout=300,
                              headers={"Authorization": f"Bearer {key}", "X-Title": "menu-extraction-eval"})
    except httpx.HTTPError as error:
        raise TransportError(f"{type(error).__name__}: {error}") from error
    latency_ms = round((time.perf_counter() - t0) * 1000)
    try:
        data = response.json()
    except ValueError as error:
        raise TransportError(f"HTTP {response.status_code}, not JSON: {response.text[:200]}") from error
    if response.status_code != 200 or "error" in data or not data.get("choices"):
        raise TransportError(f"HTTP {response.status_code}: {json.dumps(data.get('error', data), ensure_ascii=False)[:300]}")
    choice, usage = data["choices"][0], data.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    return {"text": choice["message"].get("content") or "",
            "status": "completed" if choice.get("finish_reason") == "stop" else str(choice.get("finish_reason")),
            "latency_ms": latency_ms, "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"), "thought_tokens": details.get("reasoning_tokens"),
            "total_tokens": usage.get("total_tokens"), "cost_usd": usage.get("cost"),
            "usage_raw": usage, "provider": data.get("provider"), "generation_id": data.get("id"),
            "structured_output": "response_format json_schema strict (OpenRouter)"}


def parse_rows(sent: dict, condition: str, text: str) -> list[dict]:
    """The rows that are scored. Raises ValidationError when the answer is not the schema."""
    items = sent["response_model"].model_validate_json(text).model_dump()["items"]
    if condition == "B":
        items = [it for it in items if it["category"] == "whisky"]
    return [{k: it[k] for k in ("raw_name", "price_krw", "pour_ml", "unit")} for it in items]


SCALES = (10, 100, 1000, 0.1, 0.01, 0.001)
KINDS = ("unit_scale", "glass_bottle_swap", "neighbour_row", "other")


def wrong_kind(labels: list[dict], label: dict, got: int) -> str:
    """Why a price is wrong, tried in this order: the label x10/x100/.. (unit scale), the price of
    the same name's other unit, the label price of a row within 3 rows in the same unit column
    (label order), other."""
    if any(abs(got - label["price_krw"] * k) < 0.5 for k in SCALES):
        return "unit_scale"
    if any(x["price_krw"] == got for x in labels if x["raw_name"] == label["raw_name"] and x["unit"] != label["unit"]):
        return "glass_bottle_swap"
    column = [x for x in labels if x["unit"] == label["unit"]]
    k = next(i for i, x in enumerate(column) if x is label)
    if any(column[j]["price_krw"] == got for j in range(max(0, k - 3), min(len(column), k + 4)) if j != k):
        return "neighbour_row"
    return "other"


def related_name(label_name: str, row_name: str) -> bool:
    """The row is this label item under another spelling: one name contains the other (a brand
    heading left out, "마키어 베이" for "킬호만(Kilchoman) 마키어 베이"), or they differ by a few
    characters (an OCR spelling copied as is, "Ardbeg toy" for "Ardbeg 10y")."""
    for x in score.candidates(label_name):
        for y in score.candidates(row_name):
            short, long = sorted((x, y), key=len)
            if len(short) >= 2 and short in long:
                return True
            if score.levenshtein(x, y) <= max(2, round(0.2 * len(long))):
                return True
    return False


def score_rows(labels: list[dict], rows: list[dict]) -> dict:
    """ok / wrong / missing of the priced label items of one photo.

    A label item that score.py's matching leaves without a row is looked for once more among the
    rows left over (same unit, `related_name`), rows with the label's price first:
      name_only        such a row has the label's price: only the name failed to pair
      wrong_name_only  such a row has another price: a wrong price (counted in `wrong` too)
    What is left is `missing`: no row for the item, or a row without a price.
    """
    pairs, gt_left, out_left = score.match_photo(labels, rows, lenient=True)
    out = {"cells": sum(score.price_checked(g) for g in labels), "ok": 0, "wrong": 0, "missing": 0,
           "name_only": 0, "wrong_name_only": 0, "kinds": {k: 0 for k in KINDS}, "wrong_cells": []}

    def wrong(g: dict, o: dict) -> None:
        kind = wrong_kind(labels, g, o["price_krw"])
        out["wrong"] += 1
        out["kinds"][kind] += 1
        out["wrong_cells"].append({"name": g["raw_name"], "unit": g["unit"], "label": g["price_krw"],
                                   "got": o["price_krw"], "kind": kind})

    for gi, oi, _ in pairs:
        g, o = labels[gi], rows[oi]
        if not score.price_checked(g):
            continue
        if o["price_krw"] is None:
            out["missing"] += 1
        elif o["price_krw"] == g["price_krw"]:
            out["ok"] += 1
        else:
            wrong(g, o)
    left = [gi for gi in sorted(gt_left) if score.price_checked(labels[gi])]
    free = set(out_left)
    for same_price in (True, False):
        for gi in list(left):
            g = labels[gi]
            oi = next((oi for oi in sorted(free) if rows[oi]["unit"] == g["unit"] and rows[oi]["price_krw"] is not None
                       and (rows[oi]["price_krw"] == g["price_krw"]) == same_price
                       and related_name(g["raw_name"], rows[oi]["raw_name"])), None)
            if oi is None:
                continue
            free.discard(oi)
            left.remove(gi)
            if same_price:
                out["name_only"] += 1
            else:
                out["wrong_name_only"] += 1
                wrong(g, rows[oi])
    out["missing"] += len(left)
    out["extra"] = len(free)
    return out


def load_labels() -> dict[str, list[dict]]:
    stems = {}
    for stem, label_set in PHOTOS:
        fixture = FIXTURES[stem]
        if label_set == "regression":  # the regression fixture's own expected items (ai/regression/fixtures)
            stems[stem] = fixture["expected_items"]
            continue
        stems[stem] = score.load_labels(label_set)[fixture["photo_id"]]
    return stems


def run_one(stage: dict, fixture: dict, condition: str, data_dir: Path, keys: dict) -> dict:
    sent = inputs(fixture, condition, data_dir)
    record = {"model": stage["model"], "route": stage["route"], "reasoning": stage["thinking"], "condition": condition,
              "photo_id": fixture["photo_id"], "source_image": fixture["photo"]["file"],
              "prompt_file": sent["prompt_file"], "prompt_sha256": sent["prompt_sha256"],
              "image_sha256": sent["image_sha256"], "ocr_lines_sent": sent["ocr_lines"] if condition == "B" else 0,
              "format_retry": False, "failures": []}
    for attempt in (1, 2):
        started = datetime.now(timezone.utc).isoformat()
        try:
            key = keys[stage["route"]]
            answer = (call_gemini if stage["route"] == "gemini" else call_openrouter)(stage, sent, key)
        except (ModelCallError, TransportError) as error:
            record["failures"].append({"attempt": attempt, "kind": "transport",
                                       "detail": str(error).replace(key, "***")[:300]})
            answer = None
        else:
            try:
                if answer["status"] != "completed":
                    raise ValueError(f"status {answer['status']}")
                rows = parse_rows(sent, condition, answer["text"])
            except (ValidationError, ValueError) as error:
                record["failures"].append({"attempt": attempt, "kind": "format", "detail": str(error)[:300],
                                           "raw_text": answer["text"][:2000], "latency_ms": answer["latency_ms"],
                                           "input_tokens": answer["input_tokens"],
                                           "output_tokens": answer["output_tokens"],
                                           "thought_tokens": answer["thought_tokens"], "cost_usd": answer["cost_usd"]})
                answer = None
            else:
                record.update(started_at=started, attempts=attempt, rows=rows, raw_text=answer.pop("text"), **answer)
                record["format_retry"] = any(f["kind"] == "format" for f in record["failures"])
                return record
        if attempt == 1:
            time.sleep(TRANSPORT_WAIT_S if record["failures"][-1]["kind"] == "transport" else MIN_INTERVAL_S)
    record.update(started_at=started, attempts=2, rows=None, raw_text=None)
    return record


def stage_cost(base: Path) -> float:
    """What the records of a stage have cost so far (failed format attempts included)."""
    total = 0.0
    for path in base.glob("*/*_r*.json"):
        rec = json.loads(path.read_text(encoding="utf-8"))
        total += (rec.get("cost_usd") or 0) + sum(f.get("cost_usd") or 0 for f in rec["failures"])
    return total


def report(out: Path, stage: dict, labels: dict) -> dict:
    base = out / stage["model"].replace("/", "__")
    summary = {}
    print(f"\n{stage['model']} ({stage['route']}, reasoning {stage['thinking']})")
    print(f"{'cond photo':22} run cells   ok wrong miss name-only extra  thought   out    sec  cost   note")
    for condition in CONDITIONS:
        worst = {"wrong": 0, "missing_share": 0.0, "runs": 0, "failed": 0, "format_retries": 0, "cost": 0.0}
        for stem, _ in PHOTOS:
            for run in RUNS:
                path = base / condition / f"{stem}_r{run}.json"
                if not path.exists():
                    print(f"{condition} {stem:20} r{run} no record")
                    continue
                rec = json.loads(path.read_text(encoding="utf-8"))
                worst["runs"] += 1
                worst["format_retries"] += rec["format_retry"]
                worst["cost"] += sum(f.get("cost_usd") or 0 for f in rec["failures"]) + (rec.get("cost_usd") or 0)
                if rec["rows"] is None:
                    worst["failed"] += 1
                    print(f"{condition} {stem:20} r{run} FAILED {[f['kind'] for f in rec['failures']]}")
                    continue
                s = score_rows(labels[stem], rec["rows"])
                share = s["missing"] / s["cells"] if s["cells"] else 0.0  # a photo without whisky lines
                worst["wrong"] = max(worst["wrong"], s["wrong"])
                worst["missing_share"] = max(worst["missing_share"], share)
                worst.setdefault("total_wrong", 0)
                worst["total_wrong"] += s["wrong"]
                cost = "" if rec.get("cost_usd") is None else f"{rec['cost_usd']:.4f}"
                note = "format-retry" * rec["format_retry"] + " 503-retry" * (rec["attempts"] == 2 and not rec["format_retry"]) + " >5% missing" * (share > MISSING_LIMIT)
                for kind in KINDS:
                    worst[kind] = worst.get(kind, 0) + s["kinds"][kind]
                worst["name_only"] = worst.get("name_only", 0) + s["name_only"]
                print(f"{condition} {stem:20} r{run} {s['cells']:5d} {s['ok']:4d} {s['wrong']:5d} "
                      f"{s['missing']:4d} {s['name_only']:9d} {s['extra']:5d} {rec['thought_tokens'] or 0:8d} "
                      f"{rec['output_tokens'] or 0:5d} {rec['latency_ms'] / 1000:6.1f} {cost:6} {note}")
        worst["pass"] = (worst["runs"] == len(PHOTOS) * len(RUNS) and not worst["failed"] and worst["wrong"] == 0
                         and worst["missing_share"] <= MISSING_LIMIT)
        summary[condition] = worst
        print(f"  condition {condition}: worst run wrong {worst['wrong']}, worst missing share {worst['missing_share']:.1%}, "
              f"wrong cells over all runs {worst.get('total_wrong', 0)} {({k: worst.get(k, 0) for k in KINDS})}, "
              f"name-only {worst.get('name_only', 0)}, failed calls {worst['failed']}, "
              f"format retries {worst['format_retries']}, cost ${worst['cost']:.4f} -> {'PASS' if worst['pass'] else 'no pass'}")
    return summary


def main(argv=None) -> int:
    from dotenv import dotenv_values
    from extract import data_dir as default_data_dir
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stage", type=int, choices=sorted(STAGES), required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--data-dir", type=Path)
    ap.add_argument("--check", action="store_true", help="check the inputs and count the calls; no API call")
    ap.add_argument("--report", action="store_true", help="score the records; no API call")
    ap.add_argument("--max-calls", type=int, default=30)
    ap.add_argument("--photos", choices=("ladder", "regression"), default="ladder",
                    help="ladder: the 5 photos; regression: the 15 regression photos + 복춘_02 + Beck_04")
    ap.add_argument("--prompt-b", type=Path, help="hybrid prompt file for condition B instead of hybrid_prompt_v2.md")
    ap.add_argument("--runs", type=int, nargs="+", help="run numbers to call (default 1 2 3)")
    ap.add_argument("--only", nargs="+", metavar="STEM", help="call only these photos of --photos")
    ap.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS),
                    help="the conditions to call in this command (the report always shows both)")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS, help="output cap of an OpenRouter call (answer + reasoning)")
    ap.add_argument("--cost-limit", type=float, help="stop before the next call once the records in --out cost this (USD)")
    args = ap.parse_args(argv)
    stage, data_dir = {**STAGES[args.stage], "max_tokens": args.max_tokens}, args.data_dir or default_data_dir()
    global FIXTURES, PHOTOS, PROMPT_B
    if args.prompt_b:
        PROMPT_B = args.prompt_b.resolve()
    FIXTURES = i5_row_pairing.known_photos(data_dir)
    if args.photos == "regression":
        import regression
        PHOTOS = tuple((Path(fx["photo"]["file"]).stem, "regression") for fx in regression.load_fixtures()) + (
            ("007_bokchun_02", "val_v1_1"), ("012_beck_04", "test_v1_1"))
    cost_limit = args.cost_limit if args.cost_limit is not None else STAGE_COST_LIMIT_USD.get(args.stage, 0.0)
    fixtures = [FIXTURES[stem] for stem, _ in PHOTOS]
    labels = load_labels()
    if args.report:
        report(args.out, stage, labels)
        return 0
    import p46_extract
    problems = p46_extract.check_inputs(fixtures, data_dir)
    if problems:
        raise SystemExit("\n".join(problems))
    base = args.out / stage["model"].replace("/", "__")
    todo = [(run, fx, cond, base / cond / f"{Path(fx['photo']['file']).stem}_r{run}.json")
            for run in (args.runs or RUNS) for fx in fixtures for cond in args.conditions
            if not args.only or Path(fx["photo"]["file"]).stem in args.only]
    todo = [job for job in todo if not job[3].exists()]
    print(f"stage {args.stage}: {stage['model']} via {stage['route']}; photos {len(fixtures)}; "
          f"calls to make {len(todo)} (max {args.max_calls}); output cap {stage['max_tokens']}")
    if args.check:
        for cond in CONDITIONS:
            sent = inputs(fixtures[0], cond, data_dir)
            print(f"  {cond}: {sent['prompt_file']} {sent['prompt_sha256'][:12]}, user text {len(sent['user_text'])} chars")
        return 0
    env = dotenv_values(REPO_ROOT / ".env")
    keys = {"gemini": (env.get("GEMINI_API_KEY") or "").strip(), "openrouter": (env.get("OPENROUTER_API_KEY") or "").strip()}
    if not keys[stage["route"]]:
        raise SystemExit(f"the {stage['route']} API key is not set in the repo .env")
    for calls, (run, fx, cond, target) in enumerate(todo):
        if calls >= args.max_calls:
            print(f"stopped at --max-calls {args.max_calls}")
            return 1
        spent = stage_cost(base)
        if spent >= cost_limit and stage["route"] != "gemini":
            print(f"stopped: the records have cost ${spent:.2f}, the limit is ${cost_limit}")
            return 1
        if calls:
            time.sleep(MIN_INTERVAL_S)
        record = run_one(stage, fx, cond, data_dir, keys)
        record["run"] = run
        record["max_tokens"] = stage["max_tokens"] if stage["route"] == "openrouter" else None
        target.parent.mkdir(parents=True, exist_ok=True)
        if record["rows"] is None and all(f["kind"] == "transport" for f in record["failures"]):
            # no answer at all (quota, 503): not a result of the model. Logged, and the call stays to do.
            with (base / "transport_failures.jsonl").open("ab") as log:
                log.write((json.dumps({"at": record["started_at"], "condition": cond, "photo": target.stem,
                                       "failures": record["failures"]}, ensure_ascii=False) + chr(10)).encode("utf-8"))
            print(f"{cond} {target.stem} no answer twice ({record['failures'][-1]['detail'][:90]}); stopped", flush=True)
            return 1
        target.write_bytes(json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"))
        rows = "FAILED" if record["rows"] is None else len(record["rows"])
        print(f"{cond} {target.stem} rows {rows} attempts {record['attempts']} "
              f"{(record.get('latency_ms') or 0) / 1000:.1f}s thought {record.get('thought_tokens')}", flush=True)
    report(args.out, stage, labels)
    return 0


FIXTURES: dict = {}

if __name__ == "__main__":
    raise SystemExit(main())
