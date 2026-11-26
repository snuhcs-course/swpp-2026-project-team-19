# I5-P59: Catalog ages for Glenmorangie, an optional missing-age guard, and the not-whisky note (I5)

> Draft. Not opened. Base: `main` at `0fae9345`. Branch `feature/i5-m3a-not-whisky` (local commits only).

## What changed

**From 2026-11-21/22 (the "not a whisky" work, committed now)**

- Catalog v2.4: Jack Daniel's Tennessee Apple is a product (flavoured whiskeys are served as whisky). The Odbi gold line, the dev harness exception, the regression fixture and the baseline follow.
- `ResolutionResult.kind_hint` and `LLMLayerConfig.flag_non_whisky` (off by default). With the flag on, a line the LLM reads as `non_whisky` and the rules had no candidate for keeps its result and gets `kind_hint="non_whisky"`. Nothing is stored or returned by the API yet.
- Harness `--flag-non-whisky` with the `not_whisky` numbers.

**I5-P59 (2026-11-27)**

1. **Catalog v2.5** (`ai/catalog/catalog_v2_service.json`): `age_years` of Glenmorangie The Original 10 -> 12, Quinta Ruban 14, Lasanta 12, Nectar D'Or 16 (these were empty).
2. **missingAge linking guard** (`backend/app/matching/linking_guards.py`), **off by default** (`MATCHING_MISSING_AGE_GUARD=false`). A confirmed line whose name has no age (and extraction gave none) while the product has one becomes one candidate with `confirmRecommended`. An invalid value stops the server at start-up. Harness option `--missing-age-guard`.
3. **Brand + age only lines**: no rule change. With the v2.5 ages the rules already offer the one product of that age as an unconfirmed candidate. Tests pin this, and a scan finds no line in dev or I3 where it is missing.
4. Measurement scripts (API 0): `ai/eval/i5_p59_compare.py` (line-by-line diff of two harness results), `i5_p59_with_age.py` (passes the age read from the line name, as menu import passes the extracted age), `i5_p59_age_only.py` (brand + age only lines).

## Numbers (rules + server steps, label input, API 0)

| Catalog v2.4 -> v2.5 | Top-1 | FM | wrong CR | hard lines / photo (after server steps) |
|---|---|---|---|---|
| dev, 836 lines | 625 -> 626 / 804 | 0 -> 0 | 3 -> 3 | 3.86 -> 3.79 |
| I3 full, 675 lines | 500 -> 500 / 646 | 1 -> 1 | 3 -> 2 | 2.48 -> 2.39 |
| I3 ops | 511 -> 511 / 646 | 1 -> 1 | 3 -> 2 | 2.06 -> 1.97 |

- v2.5 newly confirms 2 lines correctly (dev 1, I3 1) and gives the right single candidate to 3 lines that had none. **One correct confirmation becomes a recommended candidate** (I3 "글렌모렌지 더 넥타 16Y": the brand + age step now finds Nectar D'Or and wants "D'Or" on the line). When the line's age is passed as menu import does, two more lines written with an older age ("오리지날 10년", "라산타 15Y") are no longer confirmed (I3 Top-1 500 -> 498, ops 511 -> 509).

| missingAge guard off -> on (catalog v2.5) | confirmations lost: correct / wrong | Top-1 | FM | hard lines / photo |
|---|---|---|---|---|
| dev | 24 / 0 | 626 -> 602 | 0 -> 0 | 3.79 -> 3.79 |
| I3 full | 24 / 1 | 500 -> 476 | 1 -> 0 | 2.39 -> 2.42 |
| I3 ops | 24 / 1 | 511 -> 487 | 1 -> 0 | 1.97 -> 2.00 |

The wrong one is "Ardbeg Anthology" (the I3/I4 false merge). Every lost correct confirmation keeps the right product as its one recommended candidate. The flag stays off.

The P31 re-run with M3a (Gemini) was **not** run: the handoff stops before it when a correct confirmation disappears in 1a. The end-to-end run with Gemini 3.8 Flash extraction is prepared but not run (about $0.92 per run of 33 photos, no CLOVA call).

## Flag defaults

- `MATCHING_MISSING_AGE_GUARD=false` (documented in `backend/README.md` and `backend/.env.example`).
- `flag_non_whisky=False` (no environment variable).

## Tests

- New: `backend/tests/test_linking_guards.py` (missingAge: off by default, two lines without an age, lines with an age and products without one, the extracted age, `has_age`, the setting), `backend/tests/test_resolve_staged.py` (brand + age only lines), `ai/eval/test_i5_p59.py` (catalog ages, the three scripts, the harness option). Fixed value: the I3 asis catalog digest for v2.5.
- `ai`: 391 / 392 pass. The one failure (`test_reencoded_ocr_cache_without_provenance_stops`, a Windows path separator) predates this branch. Backend: 1159 pass, 1940 skipped (need a database). `tests/test_pdf_*.py` and `test_run_uat_inputs.py` were not collected locally (no `pypdfium2`). Regression check on the 15 photos: pass.
- Coverage of the new scripts: 96% together. `linking_guards.py`: 100%.

## Not checked

- Menu import with `MATCHING_MISSING_AGE_GUARD=true` against a database (those tests skip locally).
- The Glenmorangie ages themselves (taken from the I4 AI backlog, no web check).
- `test_server_steps_add_candidates_and_never_confirm` failed once in seven local runs; cause unknown.
- The catalog is not loaded into the production database.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
