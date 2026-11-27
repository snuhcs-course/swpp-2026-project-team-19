# I5-P59/P31: Glenmorangie ages (catalog v2.4-v2.6, accepted older ages), an optional missing-age guard, and the not-whisky note

> Draft. Not opened. Base: `main` at `0fae9345`. Branch `feature/i5-m3a-not-whisky` (local commits only).

## What changed

**The "not a whisky" note (I5, 2026-11-21/22), flag off**

- `ResolutionResult.kind_hint` and `LLMLayerConfig.flag_non_whisky` (default `False`, no environment variable). With the flag on, a line the LLM layer reads as `non_whisky` and the rules had no candidate for keeps its result and gets `kind_hint="non_whisky"`. Status, candidates and the review state do not change, and nothing is stored or returned by the API yet.
- Harness option `--flag-non-whisky` with the `not_whisky` numbers.

**Catalog v2.4 to v2.6** (`ai/catalog/catalog_v2_service.json`, README sections 15-17)

- v2.4: Jack Daniel's Tennessee Apple is a product (flavoured whiskeys are served as whisky). The Odbi gold line, the dev harness exception, the regression fixture and the baseline follow.
- v2.5: `age_years` of the Glenmorangie bottles: The Original 10 -> 12, Quinta Ruban 14, Nectar D'Or 16, Lasanta 12 (the last three were empty).
- v2.6: Lasanta 12 -> 15 (the bottle changed in 2025; 12 was the old bottle).

**Accepted older ages** (`backend/app/matching/accepted_ages.py`, new)

- Bars pour the old and the new bottle side by side, so a product also accepts the age its old bottle carried: The Original 10, Lasanta 12, Quinta Ruban 12 (Nectar D'Or none: sources disagree). Still one product per bottling.
- A line age (from the line name, or `age_years` from extraction) that is the product's age or an accepted age fits the product: no `ageConflict`, the brand + age step (S2) finds the product by it, and the evidence records `ageAccepted: <age>`. The pick check (`pick_check`), the `incompleteName` guard (measurement only) and the LLM layer's `age_mismatch` veto use the same rule (`ProductInfo.fits_age`).
- **No schema or API change.** The server reads products from the database only, and the seed script loads them with the ids of `catalog_v2_service.json`, so the table is keyed by those ids and lives in the matching module. `DbCatalog`, `CatalogSnapshot`, `InMemoryCatalog.from_seed` and the evaluation harness fill `ProductInfo.accepted_ages` from it.
- Effect: "글렌모렌지 오리지날 10년" and "글렌모렌지 라산타 15Y" are confirmed again when the extracted age is passed (v2.5 had made them candidates), "Glenmorangie 15yr" gets Lasanta as its one candidate, and "글렌모렌지 12" is a choice of the four products that take 12.

**missingAge linking guard** (`backend/app/matching/linking_guards.py`), **off** (`MATCHING_MISSING_AGE_GUARD=false`)

- A confirmed line whose name has no age (and extraction gave none) while the product has one becomes one candidate with `confirmRecommended`. An invalid value stops the server at start-up. Harness option `--missing-age-guard`. Kept off: on catalog v2.5 it turned 24 correct confirmations per set into recommendations to remove one false merge (I3 "Ardbeg Anthology").

**Brand + age only lines**: no rule change; tests pin the behaviour (one product of that age -> one unconfirmed candidate, the plain bottling stays confirmed, two products -> a choice).

**Measurement scripts** (API 0): `ai/eval/i5_p59_compare.py` (line-by-line diff of two harness results), `i5_p59_with_age.py` (passes the age read from the line name, as menu import passes the extracted age), `i5_p59_age_only.py` (brand + age only lines).

## Numbers

Rules + server steps, label input, API 0. Catalog v2.5 -> v2.6 (with accepted ages):

| | Top-1 | FM | wrong CR | hard lines / photo (after server steps) |
|---|---|---|---|---|
| dev, 836 lines | 626 -> 627 / 804 | 0 -> 0 | 3 -> 3 | 3.79 -> 3.76 |
| I3 full, 675 lines | 500 -> 500 / 646 | 1 -> 1 | 2 -> 2 | 2.39 -> 2.36 |
| I3 ops | 511 -> 511 / 646 | 1 -> 1 | 2 -> 2 | 1.97 -> 1.94 |
| I3 full, extracted age passed | 498 -> 500 / 646 | 1 -> 1 | 2 -> 2 | 2.39 -> 2.36 |
| I3 ops, extracted age passed | 509 -> 511 / 646 | 1 -> 1 | 2 -> 2 | 1.97 -> 1.94 |

No correct confirmation is lost and no false merge is added. With the age passed, I3 is back at the v2.4 Top-1.

Re-evaluation with the LLM layer (M3a, `gemini-3.1-flash-lite`, `--flag-non-whisky`): rules + M3a + server steps, label input. Earlier runs: P46 (I4, 2026-11-17, catalog v2.3) and 2026-11-21 (v2.4); on I3 the two are identical.

| | Top-1 | FM | wrong CR | hard lines / photo | confirm / choose / register / wrong | not-whisky note: non-whisky right · whisky wrong · unknown |
|---|---|---|---|---|---|---|
| dev r1, r2: 11/21 | 625 / 804 | 0 | 3, 3 | 2.69, 2.66 | 133/54/18/6, 134/53/18/6 | 16/16 · 0/179 · 0/16 |
| dev r1, r2: now | 627 / 804 | 0 | 3, 3 | 2.59, 2.55 | 134/52/18/5, 135/51/18/5 | 16/16 · 0/177 · 0/16 |
| I3 full r1-r3: P46 = 11/21 | 500 / 646 | 1 | 3, 3, 5 | 1.67, 1.67, 1.70 | 111/41/8/6, 111/41/9/5, 110/41/9/6 | 4/4 · 0/138 · 0/24 (11/21) |
| I3 full r1-r3: now | 500 / 646 | 1 | 2, 2, 4 | 1.55, 1.55, 1.58 | 115/40/8/3, 115/40/9/2, 114/40/9/3 | 4/4 · 0/138 · 0/24 |
| I3 ops r1-r3: P46 = 11/21 | 511 / 646 | 1 | 3, 3, 3 | 1.58, 1.58, 1.61 | 103/39/8/5, 103/39/8/5, 102/40/8/5 | 4/4 · 0/127 · 0/24 (11/21) |
| I3 ops r1-r3: now | 511 / 646 | 1 | 2, 2, 2 | 1.45, 1.45, 1.48 | 107/38/8/2, 107/38/8/2, 106/39/8/2 | 4/4 · 0/127 · 0/24 |

- Every line that changed against 11/21 is a Glenmorangie line. The one false merge is still "Ardbeg Anthology".
- **Fixed on the test set:** the Glenmorangie ages were set after looking at I3 lines, so the I3 numbers include that fix.
- One correct confirmation is still a recommendation: "글렌모렌지 더 넥타 16Y" (the product's edition "Nectar D'Or" has "D'Or", the line does not; the bottle is now called "The Nectar"). Not changed here.

API calls for these numbers: Gemini 14 (free key, all first attempts), OpenRouter 0, CLOVA 0.

## Flag defaults

- `MATCHING_MISSING_AGE_GUARD=false` (documented in `backend/README.md` and `backend/.env.example`).
- `flag_non_whisky=False` (no environment variable).
- Accepted ages have no flag: they apply once the code is deployed. The Lasanta age (15) reaches the database with the next catalog seed.

## Tests

- New: `backend/tests/test_accepted_ages.py` (26: accepted and current ages from extraction and from the line, a third age still conflicting, brand + age candidates, products without accepted ages unchanged, pick check, `incompleteName`, the LLM veto, the table against the catalog file, and the two database catalogs, which needs a database), `backend/tests/test_linking_guards.py` (missingAge), `backend/tests/test_resolve_staged.py` (brand + age only lines), `ai/eval/test_i5_p59.py` (catalog ages, the harness's accepted ages, the three scripts, the harness option). Fixed value: the I3 asis catalog digest for v2.6.
- Locally: backend 1184 passed, 1941 skipped (need a database), 0 failed (`tests/test_pdf_*.py` and `test_run_uat_inputs.py` not collected: no `pypdfium2`). `ai`: 393 / 394; the one failure (`test_reencoded_ocr_cache_without_provenance_stops`, a Windows path separator) predates this branch. Regression check on the 15 photos: pass, no changed line.
- Coverage (branches): `accepted_ages.py`, `linking_guards.py`, `pick_check.py`, `llm_layer.py`, `types.py` 100%; the measurement scripts 95% together.

## Not checked

- The tests that need a database (one new: the database catalogs fill the accepted ages), and menu import with real extracted ages or with `MATCHING_MISSING_AGE_GUARD=true`.
- The Glenmorangie ages themselves (the team's decision, no web check).
- The end-to-end run with Gemini 3.8 Flash extraction (about $0.92 per run of 33 photos, no CLOVA call): after the OpenRouter extraction PR is on `main`.
- `ai/eval/match_eval.py` (the frozen pre-P47 harness) does not fill the accepted ages.
- `test_server_steps_add_candidates_and_never_confirm` failed once in seven runs on the 11/27 night run (cause unknown); it did not fail in the day runs.
- The catalog is not loaded into the production database.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
