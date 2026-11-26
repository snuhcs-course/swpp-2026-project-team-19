"""Run the six UAT inputs (three menu photos, three menu PDFs) through the server's extraction
and report what was read (I4-P30). Calls CLOVA OCR and Gemini.

    cd backend
    uv run --env-file .env python scripts/run_uat_inputs.py --out ../ai/runs/<date>_p30
    uv run --env-file .env python scripts/run_uat_inputs.py --out ../ai/runs/<date>_p30 --only pdf-scanned
    uv run --env-file .env python scripts/run_uat_inputs.py --out ../ai/runs/<date>_p30 --force

The inputs are listed in scripts/uat_inputs.json. Each goes through the code the server runs:
a photo through `HybridMenuExtractor.extract`, a PDF through `PdfMenuExtractor.pages` and
`extract_pdf_pages` (the PDF limits of I4-P37). The settings are the server's (GEMINI_API_KEY,
EXTRACTION_MODEL, EXTRACTION_THINKING_LEVEL, CLOVA_OCR_INVOKE_URL, CLOVA_OCR_SECRET, and
EXTRACTION_HYBRID_PROMPT), except that a photo gets `--attempts` model attempts (default 2)
instead of 6, so a test run does not spend the daily quota on retries.

Written to --out:

    <id>.json           one input: every extracted item with its name and prices, the latency,
                        the model attempts, the failure reason, and the expected lines found
    uat_inputs.json     all inputs and the totals
    uat_inputs.md       the same as tables, to read or paste

Run again with the same --out and the inputs that already have a result without a failure are
kept and not called again; a failed or missing one is run. --force runs every input again.

An input never stops the run: a missing file, a file that is not the listed one, a PDF that
cannot be read, a failed page or a failed model call is that input's failure reason, and the
other inputs still run. The exit code is 1 when any input failed, and 2 when a key or setting is
missing (nothing is sent then).

With `--extractor openrouter` (I5-P19) the inputs go through MENU_EXTRACTOR=openrouter's code
instead: a photo through `OpenRouterMenuExtractor.extract` and a PDF's pages through
`RoutedPdfMenuExtractor`, so each page takes the route ladder (OpenRouter, then the Gemini API).
Its settings are those of that extractor (OPENROUTER_API_KEY, OPENROUTER_EXTRACTION_MODEL,
EXTRACTION_DIRECT_MODEL, ... see backend/README.md); a page's record then also has `route`,
the tokens and `costUsd`. `--pdf-page-attempts 1` gives every PDF page one attempt and the PDF
no retries, which bounds what a run can cost.

Nothing is sent for a real bar's photo that is not in the data directory; those photos are not
in the repository. Keys are read from the environment and are never printed or written.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:  # run as a script: python scripts/run_uat_inputs.py
    sys.path.insert(0, str(BACKEND_ROOT))  # pragma: no cover

from app.adapters.extraction import ExtractionError, ExtractionResult  # noqa: E402
from app.adapters.hybrid_extraction import HybridMenuExtractor  # noqa: E402
from app.adapters.openrouter_extraction import OpenRouterMenuExtractor  # noqa: E402
from app.adapters.pdf_extraction import PdfMenuExtractor  # noqa: E402
from app.adapters.pdf_guards import PdfGuards, classify, extract_pdf_pages  # noqa: E402
from app.adapters.pdf_routed_extraction import RoutedPdfMenuExtractor, pdf_extractor_for  # noqa: E402
from app.core.normalize import normalize  # noqa: E402
from app.extraction import ExtractionConfigError  # noqa: E402
from app.extraction.pdf import PdfError  # noqa: E402
from app.extraction.pdf_hybrid import TEXT_LAYER_PROVIDER  # noqa: E402

MANIFEST = Path(__file__).with_name("uat_inputs.json")
DEFAULT_DATA_DIR = REPO_ROOT.parent / "bottlemap-p14" / "data"
MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
PHOTO_ATTEMPTS = 2


def load_manifest(path: Path = MANIFEST) -> list[dict[str, Any]]:
    inputs = json.loads(path.read_text(encoding="utf-8"))["inputs"]
    ids = [entry["id"] for entry in inputs]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path.name}: input ids must be unique")
    for entry in inputs:
        if entry["kind"] not in ("photo", "pdf") or entry["source"] not in ("repo", "data"):
            raise ValueError(f"{path.name}: {entry['id']} needs kind photo|pdf and source repo|data")
    return inputs


def expected_rows(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """The whisky lines the input should give, one row per price."""
    if "expect" in entry:
        return entry["expect"]
    if "expect_fixture" not in entry:
        return []
    fixture = json.loads((REPO_ROOT / entry["expect_fixture"]).read_text(encoding="utf-8"))
    return [{"name": row["raw_name"], "price_krw": row["price_krw"]}
            for row in fixture["expected_items"] if row.get("gold") != "non_whisky"]


def items_of(result: ExtractionResult, page: int | None = None) -> list[dict[str, Any]]:
    """The extracted items as the report shows them: the name and every price of the line."""
    return [{
        **({"page": page} if page is not None else {}),
        "name": item.product_name or item.raw_text,
        "lineType": item.line_type.value,
        "prices": [{"priceKrw": option.price_krw, "pourMl": option.pour_ml, "label": option.option_label}
                   for option in item.options],
    } for item in result.items]


def found_expected(expected: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, Any]:
    """How many expected rows are in the items. A row is found when an item of the same name
    (compared without spaces, case and the age unit) has its price; a row without a price is
    found when an item of that name has no price."""
    prices: dict[str, set[int | None]] = {}
    for item in items:
        got = {price["priceKrw"] for price in item["prices"]} or {None}
        prices.setdefault(normalize(item["name"]), set()).update(got)
    missing = [row for row in expected if row["price_krw"] not in prices.get(normalize(row["name"]), set())]
    return {"expected": len(expected), "found": len(expected) - len(missing), "missing": missing}


def _latency(raw_output: dict[str, Any] | None) -> dict[str, int | None]:
    """The model and OCR latency of one call. A text page of a PDF has no OCR call: its lines
    come from the file."""
    raw = raw_output or {}
    ocr = raw.get("ocr") or {}
    return {"modelMs": raw.get("latencyMs"),
            "ocrMs": None if ocr.get("provider") == TEXT_LAYER_PROVIDER else ocr.get("latencyMs")}


def _route(raw_output: dict[str, Any] | None) -> dict[str, Any]:
    """Which route read a page and what it cost, for a page read through the route ladder
    (app.extraction.routed); nothing for the hybrid extractor, whose records have no route."""
    raw = raw_output or {}
    if not isinstance(raw.get("route"), dict):
        return {}
    return {"route": raw["route"], "inputTokens": raw.get("inputTokens"), "outputTokens": raw.get("outputTokens"),
            "thoughtTokens": raw.get("thoughtTokens"), "costUsd": raw.get("costUsd")}


def _sum(values: list[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def run_photo(data: bytes, mime_type: str, hybrid: HybridMenuExtractor) -> dict[str, Any]:
    try:
        result = hybrid.extract(data, mime_type, None)
    except ExtractionError as error:
        raw = error.raw_output or {}
        return {"items": [], "failure": {"code": classify(error), "message": str(error)},
                "attempts": raw.get("attempts"), **_latency(raw)}
    raw = result.raw_output
    return {"items": items_of(result), "failure": None, "attempts": raw.get("attempts"), **_latency(raw),
            "ocrFallback": (raw.get("hybridFallback") or {}).get("reason")}


def run_pdf(data: bytes, extractor: PdfMenuExtractor | RoutedPdfMenuExtractor, guards: PdfGuards) -> dict[str, Any]:
    try:
        pages = extractor.pages(data)
    except PdfError as error:
        return {"items": [], "pages": [], "failure": {"code": error.code, "message": str(error)},
                "attempts": 0, "modelMs": None, "ocrMs": None}
    outcome = extract_pdf_pages(extractor, pages, guards)
    kinds = {page.number: page for page in pages}
    report, items = [], []
    for page in outcome.pages:
        if page.result is not None:
            items += items_of(page.result, page.page)
        report.append({
            "page": page.page, "kind": kinds[page.page].kind, "textLayer": kinds[page.page].text_layer,
            "items": len(page.result.items) if page.result is not None else 0,
            "failure": None if page.ok else {"code": page.failure, "message": page.message},
            "attempts": page.attempts, **_latency(page.raw_output), **_route(page.raw_output),
        })
    failed = [page for page in report if page["failure"] is not None]
    failure = None
    if failed:
        codes = ", ".join(f"page {page['page']}: {page['failure']['code']}" for page in failed)
        failure = {"code": "pages_failed", "message": f"{len(failed)} of {len(report)} pages failed ({codes})"
                   + (f"; stopped: {outcome.stopped}" if outcome.stopped else "")}
    return {"items": items, "pages": report, "failure": failure, "attempts": outcome.model_attempts,
            "modelMs": _sum([page["modelMs"] for page in report]), "ocrMs": _sum([page["ocrMs"] for page in report])}


def run_input(
    entry: dict[str, Any],
    data_dir: Path,
    hybrid: HybridMenuExtractor,
    guards: PdfGuards,
    *,
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    """One input through the pipeline. Never raises for a bad input or a failed call."""
    root = REPO_ROOT if entry["source"] == "repo" else data_dir
    path = root / entry["path"]
    record: dict[str, Any] = {"id": entry["id"], "kind": entry["kind"], "uat": entry["uat"], "file": entry["path"],
                              "source": entry["source"], "startedAt": datetime.now(UTC).isoformat(timespec="seconds")}
    started = clock()
    if not path.is_file():
        where = "the repository" if entry["source"] == "repo" else f"the data directory {data_dir}"
        body: dict[str, Any] = {"items": [], "failure": {
            "code": "input_missing", "message": f"{entry['path']} is not in {where}; nothing was sent"}}
    elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        body = {"items": [], "failure": {
            "code": "input_changed", "message": f"{entry['path']} is not the listed file (SHA-256 differs); "
                                                 "nothing was sent"}}
    elif entry["kind"] == "photo":
        body = run_photo(path.read_bytes(), MIME_TYPES[path.suffix.lower()], hybrid)
    else:
        body = run_pdf(path.read_bytes(), pdf_extractor_for(hybrid), guards)
    record.update(body)
    record["wallMs"] = round((clock() - started) * 1000)
    record["expected"] = found_expected(expected_rows(entry), record["items"])
    return record


def run_all(
    inputs: list[dict[str, Any]],
    out: Path,
    data_dir: Path,
    hybrid_factory: Callable[[], HybridMenuExtractor],
    guards: PdfGuards,
    *,
    force: bool = False,
    log: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    """Run the inputs that have no good result in `out` yet and return every input's record."""
    out.mkdir(parents=True, exist_ok=True)
    hybrid: HybridMenuExtractor | None = None
    records = []
    for entry in inputs:
        target = out / f"{entry['id']}.json"
        kept = None if force else read_record(target)
        if kept is not None and kept.get("failure") is None and kept.get("sha256") == entry["sha256"]:
            log(f"{entry['id']}: kept ({len(kept['items'])} items)")
            records.append(kept)
            continue
        hybrid = hybrid or hybrid_factory()  # the settings are needed only when something is run
        record = {**run_input(entry, data_dir, hybrid, guards), "sha256": entry["sha256"],
                  "model": hybrid.model_name, "pipeline": hybrid.pipeline_version}
        write_record(target, record)
        failure = record["failure"]
        log(f"{entry['id']}: " + (f"FAILED {failure['code']}: {failure['message']}" if failure
                                  else f"{len(record['items'])} items in {record['wallMs']} ms"))
        records.append(record)
    return records


def read_record(path: Path) -> dict[str, Any] | None:
    """A kept record, or None when there is none or it cannot be used: a file a stopped run left
    half written, or one that is not a record of this script. Such an input is run again."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    usable = isinstance(record, dict) and isinstance(record.get("items"), list) and "failure" in record
    return record if usable else None


def write_record(path: Path, record: dict[str, Any]) -> None:
    """Write the record whole or not at all: to a file beside it, then moved into place."""
    partial = path.with_name(path.name + ".part")
    partial.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(partial, path)


def _price(price: dict[str, Any]) -> str:
    amount = "no price" if price["priceKrw"] is None else f"{price['priceKrw']:,}"
    detail = f"{price['pourMl']}ml" if price["pourMl"] else price["label"]
    return f"{amount} ({detail})" if detail else amount


def _ms(value: int | None) -> str:
    return "-" if value is None else f"{value / 1000:.1f} s"


def markdown(records: list[dict[str, Any]]) -> str:
    lines = ["# UAT inputs through the extraction pipeline (I4-P30)", "",
             f"{len(records)} inputs, {sum(record['failure'] is None for record in records)} without a failure. "
             "Latency: the model call, the OCR call, and the whole input as the script measured it.", "",
             "| Input | Kind | Items | Expected lines found | Model | OCR | Whole | Attempts | Failure reason |",
             "|---|---|---|---|---|---|---|---|---|"]
    for record in records:
        expected = record["expected"]
        found = f"{expected['found']}/{expected['expected']}" if expected["expected"] else "-"
        failure = record["failure"]
        reason = f"{failure['code']}: {failure['message']}" if failure else "-"
        lines.append(f"| {record['id']} | {record['kind']} | {len(record['items'])} | {found} | "
                     f"{_ms(record.get('modelMs'))} | {_ms(record.get('ocrMs'))} | {_ms(record['wallMs'])} | "
                     f"{record.get('attempts') if record.get('attempts') is not None else '-'} | {reason} |")
    for record in records:
        lines += ["", f"## {record['id']}", "", f"{record['uat']}. File: `{record['file']}`."]
        for page in record.get("pages", []):
            failure = page["failure"]
            lines.append(f"- Page {page['page']} ({page['kind']}, text layer {page['textLayer']}): "
                         f"{page['items']} items, model {_ms(page['modelMs'])}, OCR {_ms(page['ocrMs'])}, "
                         f"attempts {page['attempts']}"
                         + (f", failed {failure['code']}: {failure['message']}" if failure else ""))
        if record.get("ocrFallback"):
            lines.append(f"- OCR failed and the model read the photo alone: {record['ocrFallback']}")
        if record["items"]:
            lines += ["", "| Name | Prices |", "|---|---|"]
            lines += [f"| {item['name']} | {', '.join(_price(price) for price in item['prices']) or 'no price'} |"
                      for item in record["items"]]
        missing = record["expected"]["missing"]
        if missing:
            lines += ["", "Expected lines not found: " + "; ".join(
                f"{row['name']} {'(no price)' if row['price_krw'] is None else format(row['price_krw'], ',')}"
                for row in missing)]
    return "\n".join(lines) + "\n"


def write_report(records: list[dict[str, Any]], out: Path) -> None:
    summary = {
        "inputs": len(records),
        "failed": [record["id"] for record in records if record["failure"] is not None],
        "items": sum(len(record["items"]) for record in records),
        "expected": sum(record["expected"]["expected"] for record in records),
        "expectedFound": sum(record["expected"]["found"] for record in records),
    }
    (out / "uat_inputs.json").write_text(
        json.dumps({"summary": summary, "inputs": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "uat_inputs.md").write_text(markdown(records), encoding="utf-8")


def server_hybrid(attempts: int = PHOTO_ATTEMPTS) -> HybridMenuExtractor:
    """The server's extractor from the environment, with fewer model attempts for a photo."""
    hybrid = HybridMenuExtractor()
    return HybridMenuExtractor(replace(hybrid.settings, max_attempts=attempts), hybrid.clova, prompt=hybrid.prompt)


def server_openrouter(attempts: int = PHOTO_ATTEMPTS) -> OpenRouterMenuExtractor:
    """MENU_EXTRACTOR=openrouter's extractor from the environment, with fewer OpenRouter attempts for a
    photo. It has no daily paid budget: this is a test run, not the server."""
    extractor = OpenRouterMenuExtractor()
    route = replace(extractor.route, openrouter=replace(extractor.route.openrouter, max_attempts=attempts))
    return OpenRouterMenuExtractor(route, extractor.clova)


def main(argv: list[str] | None = None, *, hybrid_factory: Callable[[], HybridMenuExtractor] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the records and the report")
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("BOTTLEMAP_DATA_DIR") or DEFAULT_DATA_DIR),
                        help="where the real bars' photos are (default: BOTTLEMAP_DATA_DIR or ../bottlemap-p14/data)")
    parser.add_argument("--only", action="append", help="run only this input id (can be given more than once)")
    parser.add_argument("--attempts", type=int, default=PHOTO_ATTEMPTS, help="model attempts for a photo")
    parser.add_argument("--force", action="store_true", help="run inputs that already have a good result again")
    parser.add_argument("--extractor", choices=("hybrid", "openrouter"), default="hybrid",
                        help="hybrid: the Gemini API extractor (default, as in I4-P30); openrouter: the route ladder")
    parser.add_argument("--pdf-page-attempts", type=int,
                        help="model attempts for one PDF page (default: the PDF limits' own, 3); 1 also takes the "
                             "PDF's retries away")
    args = parser.parse_args(argv)

    inputs = load_manifest()
    if args.only:
        unknown = sorted(set(args.only) - {entry["id"] for entry in inputs})
        if unknown:
            parser.error(f"unknown input id: {', '.join(unknown)}")
        inputs = [entry for entry in inputs if entry["id"] in args.only]
    server = server_openrouter if args.extractor == "openrouter" else server_hybrid
    factory = hybrid_factory or (lambda: server(args.attempts))
    guards = PdfGuards()
    if args.pdf_page_attempts is not None:
        guards = PdfGuards(page_attempts=args.pdf_page_attempts,
                           document_retries=0 if args.pdf_page_attempts == 1 else guards.document_retries)
    try:
        records = run_all(inputs, args.out, args.data_dir, factory, guards, force=args.force)
    except ExtractionConfigError as error:  # a key or setting is missing: nothing was sent
        print(f"settings: {error}", file=sys.stderr)
        return 2
    write_report(records, args.out)
    failed = [record["id"] for record in records if record["failure"] is not None]
    print(f"{len(records) - len(failed)} of {len(records)} inputs without a failure; "
          f"report: {args.out / 'uat_inputs.md'}")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
