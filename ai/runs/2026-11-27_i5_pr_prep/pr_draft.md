# PR draft: I5-P18 / P19 / A2 / P43 — menu extraction through OpenRouter, daily limits, concurrency check

> Draft for Jinwoo's review (2026-11-27). Branch `feature/i5-p19-openrouter-extraction`, 18 commits on top of `54a0bf26`. Not pushed.
> Checked before writing: no merge conflict with `origin/main` (`0fae9345`); the only files both sides touched are `backend/DEPLOY.md` and `backend/app/main.py`, and they merge cleanly. The only keys in the diff are test values (`or-secret-test-key`, `secret-test-key`).
> **Run records are not committed; reports only.** The JSON, JSONL, log and text records under `ai/runs/` stay on Jinwoo's PC (Testing Doc 4.4), and the branch history was rewritten so that no commit contains them.

---

## Summary

Server menu extraction moves from `gemini-3.5-flash-lite` (Gemini API, free key) to `google/gemini-3.8-flash` through OpenRouter, with a fallback ladder back to the Gemini API. Two daily limits keep the single course-issued OpenRouter key from being drained during the alpha and beta. PDF pages take the same route and count against the same limits. Whisky lines without a price that lie wholly in the left or right 10% of a photo are taken for a facing page's lines and dropped before they are stored; they stay in `raw_output.droppedEdgeRows`.

## Route

| Stage | Model | When |
|---|---|---|
| 0 | `google/gemini-3.8-flash` via OpenRouter, hybrid prompt v2.1 + CLOVA OCR lines | Default |
| 1 | `anthropic/claude-sonnet-5.5` (OpenRouter `models` array) | Stage 0 model errors on OpenRouter's side |
| 2 | Gemini API direct, `EXTRACTION_DIRECT_MODEL` | OpenRouter fails, returns 402, the breaker is open, or the daily limit is used up |
| 3 | `gemini-3.5-flash-lite` direct, prompt v2.1 | Stage 2 fails |
| 4 | — | Everything failed; the import is marked failed as before |

- Breaker: 3 OpenRouter failures in a row skip it for 10 minutes (`OPENROUTER_BREAKER_FAILURES`, `OPENROUTER_BREAKER_COOLDOWN_S`).
- Kill switch: `MENU_EXTRACTOR=gemini` restores the old extractor even if OpenRouter settings remain (tested).
- Every record stores the route in `raw_output.route` (stage, model, provider, skipped stages), tokens, `costUsd` and `latencyMs`.
- Facing-page guard (`backend/app/extraction/edge_guard.py`): after any stage, before storing and matching, a whisky line with no price (a glass/bottle mark or a pour size alone does not count) whose OCR name box lies wholly in the left or right strip is dropped. `EXTRACTION_EDGE_STRIP_PERMILLE` (default 100, `0` = off; an invalid value stops start-up). Applies to photos and scanned PDF pages, not to PDF pages read from their text layer, not to `MENU_EXTRACTOR=gemini`. One log line per photo (`extraction edge guard dropped=N`, WARNING when N > 0).

## Limits

| Limit | Default | Setting | Notes |
|---|---|---|---|
| Photos per account per day (I5-A2) | 30 | `MENU_PHOTO_DAILY_LIMIT` | Over the limit: `429 RATE_LIMITED` with `details.remaining`, `dailyLimit`, `requested`, `retryAfter`. Resets on restart (no uploader column in the schema) |
| Photos through OpenRouter per day, server-wide | 300 | `OPENROUTER_DAILY_PHOTO_LIMIT` | Over the limit, photos start at stage 2 instead of being refused. Counted from `extraction_runs`, so it survives a restart. KST day |

## Evidence

| Check | Photos | Result | Cost |
|---|---|---|---|
| Model ladder (11/21), 5 hard photos × 3 runs | 5 | Only Gemini 3.8 Flash with OCR lines had 0 wrong prices and 0 missing cells (4,290 cells) | $1.437 |
| Fallback ladder (P18, 11/25), criterion committed before any call (`e2fa7874`) | 6 × 3 | Only Sonnet 5.5 passed (0 wrong of 990). Gemini 3.7 Flash and GPT-6.1 Terra failed | $2.387 |
| Server code, regression set (P19, 11/25) | 17 | 572/572 correct, 0 wrong, 0 missing (flash-lite + v2: 552 correct, 6 wrong, 13 missing). Median 35.1 s, p95 55.9 s, $0.0281 per photo | $0.478 |
| Sonnet 5.5 on the regression set (11/26) | 17 | 557/572, 6 wrong prices (one photo at a tenth), 4 missing bottler titles. Kept as stage 1 by Jinwoo's decision | $0.983 |
| Three concurrent imports (P43, 11/26) | 3 × 2 | Did not block each other: 69.7 s wall clock for 144.8 s of calls; 135/135 correct | $0.125 |
| Real call per stage (11/26) | 1 | Stage 1 Sonnet 17/17; stage 3 flash-lite + v2.1 16/17, no wrong price; stage 2 Gemini 3.8 Flash direct returned 503 three times in an hour | $0.042 |
| UAT PDFs through the new route (11/26) | 3 PDFs, 5 pages | 24/24 expected lines, all at stage 0, 2 CLOVA calls | $0.050 |
| Facing-page guard on the recorded answers (11/27), the server's own functions | 114 records, 5,024 whisky rows | Drops 60/60 lines of the page next to 011_mirabeau_03 and 0/7 real lines without a price; nothing else; the 17 server-code records still score 572/572. The 10% comes from that one photo; at 15% three real lines of a skewed photo would go too | $0 |
| Gemini API direct, a one-word request (11/27 13:34 KST), the server's SDK call, no retries | – | `gemini-3.8-flash` (stage 2): 503 "high demand" 5/5, about 31 s each; `gemini-3.5-flash-lite` (stage 3): 200 5/5, about 1.3 s. To be repeated at 15 h and 18 h (`ai/runs/2026-11-27_direct_probe.md`) | $0 (free key) |

Reports: `ai/runs/2026-11-21_i5_row_pairing/report.md` (sections 8–12), `ai/runs/2026-11-25_i5_p19_server_route/report.md`, `ai/runs/2026-11-26_i5_a2_p43/report.md`, `ai/runs/2026-11-26_i5_p19_followup/report.md`, `ai/runs/2026-11-27_i5_pr_prep/report.md` (guard, records).

The regression set is the I1/I2 photos (seen while building the pipeline), and every run above is one run unless stated.

## Tests

- New: `test_openrouter_extraction.py` (route stages, breaker, 402, truncation retry, schema violations), `test_paid_photo_budget.py` (23), `test_menu_photo_limit.py`, `test_extraction_concurrency.py`, `test_pdf_routed_extraction.py` (26), `test_edge_guard.py` (42; fixture of the 67 recorded lines: name, box, kind), `test_deploy_files.py`. New and changed modules: 100% line and branch coverage.
- Backend locally: 1,428 passed, 1,940 skipped (DB tests run in CI), 0 failed.
- AI locally: 394 passed, 1 failed (`test_p30_extract.py::test_reencoded_ocr_cache_without_provenance_stops`: a Windows path-separator failure seen on this PC since 11/21, unrelated to this branch).
- Not run locally: `test_pdf_extraction.py` (5 tests; Windows environment-variable length limit, unrelated to this change).

## Not verified

- The OpenRouter `models` array fallback with a real call: OpenRouter documents no way to force it. Whether `data_collection: "deny"` also applies to the fallback model is unknown.
- The PostgreSQL form of the daily-count query (checked on SQLite only). Please run it once on the real DB.
- Concurrent imports with the DB (checked at extractor level only).
- Stage 2 answering at all: `gemini-3.8-flash` on the free key returned 503 "high demand" every time so far (3/3 on 11/26 17–18 h, 5/5 on 11/27 13:34). Until it answers, photos that miss OpenRouter go to stage 3 (flash-lite) after the stage 2 retries.

## Deploy (after merge)

1. Put the course OpenRouter key in the server `.env` as `OPENROUTER_API_KEY` (the deploy workflow does not send it) and as a GitHub secret if a workflow needs it.
2. Set `MENU_EXTRACTOR=openrouter`, `EXTRACTION_DIRECT_MODEL=gemini-3.8-flash`, and the two limits. `EXTRACTION_EDGE_STRIP_PERMILLE` is optional (default 100).
3. Check the key: `GET https://openrouter.ai/api/v1/key` (command in `DEPLOY.md`). On 11/26: $92.36 left of $100, expires 2026-12-20 23:59 KST.
4. Stage 0 is not logged at WARNING; check `raw_output.route` of the first import.

## For teammates

**Haeul**
- Spec draft in `docs/frontend_backend_api_spec.md` (4.1, 4.4, new 4.5, 3.11.14, 3.11.19): please confirm or edit.
- Run the daily-count SQL once on PostgreSQL.
- If A2 should survive restarts: `menu_imports.uploaded_by_subject varchar(255) null` + index `(uploaded_by_subject, created_at)`.
- PDF upload: call `pdf_extractor_for(...)`, pass the **page count** to `acquire_menu_photos`, and store one `extraction_runs` row per page with `raw_output` unchanged. Otherwise PDFs skip both limits.
- P41: one call can take up to 330 s; make sure the health check does not kill long extractions.
- `extraction_runs.model_name` always shows the stage 0 model; the model that actually read the photo is in `raw_output.model`.

**Hojin**
- `429` messages for photos and PDFs (drafts in the A2/P43 report section 3 and the follow-up report G.4).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
