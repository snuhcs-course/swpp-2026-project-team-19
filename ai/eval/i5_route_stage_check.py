"""I5-P19 follow-up D: one real call for each route stage that had only been tested with fakes.

    python ai/eval/i5_route_stage_check.py --out ai/runs/2026-11-26_i5_p19_followup/stage_check --models
    python ai/eval/i5_route_stage_check.py --out ai/runs/2026-11-26_i5_p19_followup/stage_check --stage sonnet
    python ai/eval/i5_route_stage_check.py --out ai/runs/2026-11-26_i5_p19_followup/stage_check --stage direct
    python ai/eval/i5_route_stage_check.py --out ai/runs/2026-11-26_i5_p19_followup/stage_check --stage lite

One photo (010_sui_05, 17 priced cells), one call a stage, through `extract_menu_routed`, the
function MENU_EXTRACTOR=openrouter calls. CLOVA is answered from the cache.

  --models  lists the Gemini API's models (no generation call) and says whether the direct and the
            lite model ids exist and support generateContent
  sonnet    OpenRouter with anthropic/claude-sonnet-5.5 as the primary model and no fallback
            models; the Gemini API routes are closed. `max_tokens` is 16,000 instead of 48,000 so
            that the call cannot cost more than COST_LIMIT_USD even if it is cut and asked again
            (the photo's answer is about 3,500 tokens).
  direct    the paid budget refuses, as it does over the daily limit, so the photo starts at
            stage 2: the Gemini API with DIRECT_MODEL
  lite      the paid budget refuses and the stage 2 call is made to fail without reaching the API,
            so the photo is read at stage 3: the Gemini API with LITE_MODEL, prompt v2.1
In `direct` and `lite` only that stage's model is called. (The first two `direct` attempts of
2026-11-26 were made before this: when stage 2 answered 503 they also sent one request with a
model id that does not exist, which the API refused with 404.)

A record is written once per stage (<out>/<stage>.json); the script refuses to call again when it
exists. API keys are read from the repo .env and are never printed or written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in ("ai/regression", "ai/eval", "ai/extract", "backend"):
    sys.path.insert(0, str(REPO_ROOT / _p))

import i5_model_ladder as ladder  # noqa: E402
import i5_server_route_regression as single  # noqa: E402
from app.extraction import ExtractionSettings, gemini  # noqa: E402
from app.extraction.openrouter import OpenRouterSettings  # noqa: E402
from app.extraction.routed import CircuitBreaker, RouteSettings, extract_menu_routed  # noqa: E402

PHOTO = "010_sui_05"
SONNET = "anthropic/claude-sonnet-5.5"
SONNET_PRICE = (2.0, 10.0)
SONNET_MAX_TOKENS = 16000
COST_LIMIT_USD = 0.5
DIRECT_MODEL = "gemini-3.8-flash"  # deploy/env.production.example EXTRACTION_DIRECT_MODEL
LITE_MODEL = "gemini-3.5-flash-lite"  # EXTRACTION_MODEL
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class RefusingBudget:
    """The daily paid limit when it is used up: stage 0 is skipped without a call."""

    limit = 0

    def try_reserve(self) -> bool:
        return False

    def refund(self) -> None:
        pass


class OnlyModel:
    """A Gemini client that sends the calls of one model and fails every other call before it leaves,
    so a check of one stage makes no call of another."""

    def __init__(self, real, model: str) -> None:
        self._real, self._model = real, model
        self.interactions = self

    def create(self, **request):
        if request["model"] != self._model:
            raise RuntimeError(f"only {self._model} is called in this check; {request['model']} is failed on purpose")
        return self._real.interactions.create(**request)


def list_models(key: str) -> dict:
    """The model ids of the Gemini API, by name, with what each supports. The key goes in a header."""
    import httpx
    found, token, pages = {}, None, 0
    while pages < 20:
        response = httpx.get(MODELS_URL, headers={"x-goog-api-key": key}, timeout=30,
                             params={"pageSize": 200, **({"pageToken": token} if token else {})})
        pages += 1
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}: {response.text[:300].replace(key, '***')}"}
        data = response.json()
        for model in data.get("models", []):
            found[model["name"].removeprefix("models/")] = model.get("supportedGenerationMethods") or model.get("supportedActions") or []
        token = data.get("nextPageToken")
        if not token:
            break
    return found


def main(argv=None) -> int:
    from dotenv import dotenv_values
    from extract import data_dir as default_data_dir
    import i5_row_pairing
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--models", action="store_true")
    ap.add_argument("--stage", choices=("sonnet", "direct", "lite"))
    args = ap.parse_args(argv)
    env = dotenv_values(REPO_ROOT / ".env")
    gemini_key, openrouter_key = (env.get("GEMINI_API_KEY") or "").strip(), (env.get("OPENROUTER_API_KEY") or "").strip()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.models:
        models = list_models(gemini_key)
        (args.out / "gemini_models.json").write_bytes(json.dumps(models, ensure_ascii=False, indent=1).encode("utf-8"))
        if "error" in models:
            print(models["error"])
            return 1
        print(f"{len(models)} models; flash models:")
        for name in sorted(models):
            if "flash" in name:
                print(f"  {name}: {models[name]}")
        for wanted in (DIRECT_MODEL, LITE_MODEL):
            print(f"{wanted}: {'listed ' + str(models[wanted]) if wanted in models else 'NOT LISTED'}")
        return 0
    if not args.stage:
        ap.error("--models or --stage")
    target = args.out / f"{args.stage}.json"
    if target.exists():
        raise SystemExit(f"{target} exists; this check is made once")

    data_dir = default_data_dir()
    ladder.FIXTURES = i5_row_pairing.known_photos(data_dir)
    ladder.PHOTOS = ((PHOTO, "regression"),)
    labels = ladder.load_labels()[PHOTO]
    closed = ExtractionSettings(api_key="closed", model="closed", thinking_level="medium", max_attempts=1)
    budget, client = None, single.ClosedGemini()
    if args.stage == "sonnet":
        worst = 2 * (30000 * SONNET_PRICE[0] + SONNET_MAX_TOKENS * SONNET_PRICE[1]) / 1e6
        if worst > COST_LIMIT_USD:
            raise SystemExit(f"the call can cost ${worst:.2f}, over the limit ${COST_LIMIT_USD}")
        route = RouteSettings(openrouter=OpenRouterSettings(api_key=openrouter_key, model=SONNET, max_tokens=SONNET_MAX_TOKENS),
                              direct=closed, lite=closed)
    else:
        direct = ExtractionSettings(api_key=gemini_key, model=DIRECT_MODEL, thinking_level="medium", max_attempts=1)
        lite = ExtractionSettings(api_key=gemini_key, model=LITE_MODEL, thinking_level="medium", max_attempts=1)
        route = RouteSettings(openrouter=OpenRouterSettings(api_key="not-used", model="not-used"),
                              direct=direct, lite=lite if args.stage == "lite" else closed)
        budget = RefusingBudget()
        client = OnlyModel(gemini.make_client(direct), LITE_MODEL if args.stage == "lite" else DIRECT_MODEL)

    photo = ladder.FIXTURES[PHOTO]["photo"]
    path = data_dir / photo["photo_dir"] / photo["file"]
    cache = json.loads((data_dir / "ocr_cache" / f"{path.stem}__table-off.json").read_text(encoding="utf-8"))
    record = {"check": args.stage, "source_image": photo["file"]}
    import run_extraction as rx
    from app.extraction import ExtractionError
    try:
        result = extract_menu_routed(path.read_bytes(), rx.MIME_TYPES[path.suffix.lower()], rx.REPLAY_CLOVA, route,
                                     CircuitBreaker(), budget=budget, gemini_client=client, ocr_client=rx.ReplayOcr(cache))
    except ExtractionError as error:
        meta = getattr(error, "meta", None) or {"route": getattr(error, "route", None)}
        cause = error.__cause__
        record.update(error=f"{type(error).__name__}: {str(error)[:600]}", rows=None,
                      cause=None if cause is None else f"{type(cause).__name__}: {str(cause)[:600]}",
                      raw_text=getattr(error, "raw_text", None))
    else:
        meta = result["meta"]
        record.update(error=None, rows=single.whisky_rows(meta["rawOutput"]["items"]), items=len(result["items"]),
                      other_items=len(meta["otherItems"]))
    record["meta"] = {**meta, "ocr": {k: v for k, v in (meta.get("ocr") or {}).items() if k != "lines"}}
    text = json.dumps(record, ensure_ascii=False, indent=2)
    for secret in (gemini_key, openrouter_key):
        if secret:
            text = text.replace(secret, "***")
    target.write_bytes(text.encode("utf-8"))
    if record["error"]:
        print(f"{args.stage}: FAILED {record['error']}")
        print("route:", json.dumps(meta.get("route"), ensure_ascii=False)[:900])
        return 1
    score = ladder.score_rows(labels, record["rows"])
    before = json.loads((single.RUN_1121.parent / "2026-11-25_i5_p19_server_route" / f"{PHOTO}.json").read_text(encoding="utf-8"))
    print(f"{args.stage}: route {json.dumps(meta['route'], ensure_ascii=False)}")
    print(f"  model {meta['model']} status {meta['status']} attempts {meta['attempts']} latency {meta['latencyMs'] / 1000:.1f}s "
          f"input {meta['inputTokens']} output {meta['outputTokens']} thought {meta['thoughtTokens']} cost {meta['costUsd']}")
    print(f"  score ok/wrong/missing/name_only {score['ok']}/{score['wrong']}/{score['missing']}/{score['name_only']} "
          f"extra {score['extra']} of {score['cells']} cells; whisky rows {len(record['rows'])}, other items {record['other_items']}; "
          f"same scored rows as 3.8 Flash on 11/25: {record['rows'] == before['rows']}")
    for cell in score["wrong_cells"]:
        print("  wrong:", cell)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
