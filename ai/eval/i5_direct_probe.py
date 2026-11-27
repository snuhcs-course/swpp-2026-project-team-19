"""I5-P19: does the Gemini API answer stage 2 (gemini-3.8-flash) and stage 3 (gemini-3.5-flash-lite) now?

    python ai/eval/i5_direct_probe.py --out ai/runs/2026-11-27_direct_probe.md

On 2026-11-26 17-18 h stage 2 answered 503 three times out of three. To see whether that depends
on the hour, this sends a tiny request ("ok 한 단어만 답해") 5 times to each model, one call every
10 seconds (the two models in turn), the way the server calls them: the google-genai SDK client of
app.extraction.gemini.make_client (SDK retries off), the Interactions API, thinking level medium
(EXTRACTION_THINKING_LEVEL), store off, one attempt per call (no retries) under the server's
wall-clock cap. No photo, no OCR, no OpenRouter.

Each call adds one row to the table in --out (time in KST, model, HTTP code, latency, error text);
the file is created with its header the first time and appended to after that, so the same
command can be run again at another hour. The key is read from the repo .env (GEMINI_API_KEY) and
is never printed or written: error texts are cut and the key is masked if it appears.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.extraction import gemini  # noqa: E402
from app.extraction.config import ExtractionSettings  # noqa: E402

MODELS = ("gemini-3.8-flash", "gemini-3.5-flash-lite")
CALLS_PER_MODEL = 5
INTERVAL_S = 10
PROMPT = "ok 한 단어만 답해"
KST = timezone(timedelta(hours=9))
COMMAND = "python ai/eval/i5_direct_probe.py --out ai/runs/2026-11-27_direct_probe.md"
HEADER = f"""# I5-P19: Gemini API 직접 호출 확인 (stage 2·3)

다시 돌리는 명령 (레포 루트에서, API 10회): `{COMMAND}`

`ai/eval/i5_direct_probe.py`: 서버와 같은 호출 방식(google-genai SDK 클라이언트 `app.extraction.gemini.make_client`, Interactions API, thinking `medium`, `store=False`)으로 "{PROMPT}"를 모델마다 5번, 10초 간격(두 모델 번갈아)으로 보낸다. 재시도 없이 1회씩. 사진·OCR·OpenRouter는 쓰지 않는다. 키는 레포 `.env`의 `GEMINI_API_KEY`(무료 키)이고 출력하지 않는다. 실행할 때마다 아래 표에 줄이 이어 붙는다.

| 시각 (KST) | 모델 | HTTP | 걸린 시간 (초) | 답 / 오류 |
|---|---|---|---|---|
"""


def probe(client, settings: ExtractionSettings, model: str) -> dict:
    request = dict(model=model, input=[{"type": "text", "text": PROMPT}],
                   generation_config={"thinking_level": settings.thinking_level}, store=False)
    started = datetime.now(UTC)
    t0 = time.perf_counter()
    try:
        interaction = gemini._create_with_deadline(client, request, settings)
    except Exception as exc:  # recorded, not raised: the point is to see the failures
        code = gemini._status_code(exc)
        text = f"{type(exc).__name__}: {exc}"
        return {"at": started, "model": model, "code": code if code is not None else "-",
                "seconds": time.perf_counter() - t0, "text": text}
    status = str(getattr(interaction, "status", None))
    answer = (getattr(interaction, "output_text", None) or "").strip()
    return {"at": started, "model": model, "code": 200, "seconds": time.perf_counter() - t0,
            "text": f"{answer!r}" + ("" if status == "completed" else f" (status {status})")}


def cell(text: str, key: str) -> str:
    if key:
        text = text.replace(key, "***")
    return " ".join(text.split()).replace("|", "/")[:160]


def main(argv=None) -> int:
    from dotenv import dotenv_values
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    key = (dotenv_values(REPO_ROOT / ".env").get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set in the repo .env")
    settings = ExtractionSettings(api_key=key, model=MODELS[0], thinking_level="medium", max_attempts=1)
    client = gemini.make_client(settings)
    if not args.out.exists():
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(HEADER.encode("utf-8"))
    for n in range(CALLS_PER_MODEL * len(MODELS)):
        if n:
            time.sleep(INTERVAL_S)
        row = probe(client, settings, MODELS[n % len(MODELS)])
        line = (f"| {row['at'].astimezone(KST):%Y-%m-%d %H:%M:%S} | `{row['model']}` | {row['code']} | "
                f"{row['seconds']:.1f} | {cell(row['text'], key)} |\n")
        with args.out.open("ab") as out:
            out.write(line.encode("utf-8"))
        print(line, end="", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
