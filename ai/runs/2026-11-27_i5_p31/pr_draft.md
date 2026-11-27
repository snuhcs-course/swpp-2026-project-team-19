# I5-P59/P31: Glenmorangie ages and names (catalog v2.4-v2.7, accepted older ages), an article rule, an optional missing-age guard, and the not-whisky note

> Draft. Not opened. Base: `main` at `0fae9345`. Branch `feature/i5-m3a-not-whisky` (local commits only). Sections follow `.github/pull_request_template.md`.

## Task and why

I5-P59 (matching rule fixes from the I4 AI backlog) and I5-P31 (matching re-evaluation), with the I5 "not a whisky" note from 2026-11-21/22. Glenmorangie changed the ages and names on its bottles, and bars pour old and new bottles side by side: menu lines written with either age or name should match the one product, and the owner should confirm fewer lines. Independent of the OpenRouter extraction PR (`feature/i5-p19-openrouter-extraction`); the end-to-end measurement with that extraction comes after it is on `main`.

## What changed

- **Matching rules** (`backend/app/matching/`)
  - `accepted_ages.py` (new): older ages a product also goes by (The Original 10, Lasanta 12, Quinta Ruban 12), keyed by the catalog product ids. `ProductInfo.accepted_ages` and `fits_age()` (`types.py`), filled by `DbCatalog`, `CatalogSnapshot` (`db_catalog.py`) and `InMemoryCatalog.from_seed` (`memory_catalog.py`). An accepted age is no `ageConflict` (`resolve.py`), the brand + age step finds the product by it (`staged.py`), and the evidence records `ageAccepted`. The pick check (`pick_check.py`), the `incompleteName` guard (`linking_guards.py`, measurement only) and the LLM layer's `age_mismatch` veto (`llm_layer.py`) use the same rule.
  - `staged.py`: an article on the line (`the`, `더`) fits a product whose edition name has "The" when another word of the line fits that product too, so it is no longer left out as a generic word that keeps the line from being confirmed ("글렌모렌지 더 넥타 16Y" -> The Nectar, "브룩라디 더 클래식" -> The Classic Laddie). A line with only the article, or naming a product without one ("글렌모렌지 더 시그넷"), is as before.
  - `linking_guards.py`: the `missingAge` guard, **off** (`MATCHING_MISSING_AGE_GUARD=false`; `app/main.py` stops at start-up on any other value than `true`/`false`). With it on, a confirmed line without an age whose product has one becomes one recommended candidate. Kept off: on catalog v2.5 it turned 24 correct confirmations per set into recommendations to remove one false merge (I3 "Ardbeg Anthology").
  - `types.py`, `llm_layer.py`, `embedding.py`: `ResolutionResult.kind_hint` and `LLMLayerConfig.flag_non_whisky` (default `False`, no environment variable). With the flag on, a line the LLM layer reads as `non_whisky` and the rules had no candidate for keeps its result and gets `kind_hint="non_whisky"`. Nothing stores or returns it yet. `services/menu_import_processing.py` passes the flag and the extracted age to these steps.
- **Catalog** (`ai/catalog/catalog_v2_service.json`, README sections 15-18)
  - v2.4: Jack Daniel's Tennessee Apple is a product (flavoured whiskeys are served as whisky); the Odbi gold line, the regression fixture and baseline follow.
  - v2.5: Glenmorangie `age_years`: The Original 10 -> 12, Quinta Ruban 14, Nectar 16, Lasanta 12.
  - v2.6: Lasanta 12 -> 15 (the bottle changed in 2025).
  - v2.7: Nectar D'Or under its current name, `Glenmorangie The Nectar` (edition `The Nectar`). Key, id and aliases unchanged, so the old name stays an alias.
- **Matching flow document** (`docs/menu_ai_matching_flow.md`): two paragraphs, the article rule (after the I4 generic-word paragraph) and the accepted ages (10.1, age comparison).
- **Settings documents**: `MATCHING_MISSING_AGE_GUARD` in `backend/README.md` and `backend/.env.example`.
- **Evaluation harness** (`ai/eval/`): `i3_match_eval.py` gains `--flag-non-whisky`, `--missing-age-guard` and fills the accepted ages; measurement scripts `i5_kind_table.py`, `i5_p59_compare.py` (line-by-line diff of two results), `i5_p59_with_age.py` (passes the line's age as menu import passes the extracted age), `i5_p59_age_only.py` (brand + age only lines). `p30_extract.py`: the catalog and `llm_layer.py` join the files released from the P30 freeze.
- **Reports**: `ai/runs/2026-11-21_i5_not_whisky/report.md`, `ai/runs/2026-11-27_i5_p31/report.md` with line diffs (`.md`), `ai/runs/ai_usage_log.md`. Run records (M3a caches, result JSON, logs) stay on the runner's PC (`.gitignore`, as on the OpenRouter branch); `ai/runs/2026-11-21_i5_not_whisky/mixed_report.json` is kept because `ai/regression/test_mixed_report.py` compares with it.

## Contract and scope

**No contract change.**
- Not changed: no API path, field or error code, no schema or migration, no Android or owner web change. The accepted ages live in the matching module, not in the database. `kind_hint` is neither stored nor returned.
- Behaviour that changes: which menu lines menu import confirms (more Glenmorangie lines, and lines whose edition name starts with "The"), documented in `docs/menu_ai_matching_flow.md`. New optional server setting `MATCHING_MISSING_AGE_GUARD`, default `false`.

## Verification

Rules + server steps, label input, API 0 (`ai/eval/i3_match_eval.py --server-steps`):

| | Top-1: v2.5 -> v2.6 (accepted ages) -> article rule (v2.7) | FM | wrong CR | hard lines / photo after server steps |
|---|---|---|---|---|
| dev, 836 lines | 626 -> 627 -> 630 / 804 | 0 | 3 | 3.79 -> 3.76 -> 3.76 |
| I3 full, 675 lines | 500 -> 500 -> 502 / 646 | 1 | 2 | 2.39 -> 2.36 -> 2.36 |
| I3 ops | 511 -> 511 -> 513 / 646 | 1 | 2 | 1.97 -> 1.94 -> 1.94 |
| I3 full, extracted age passed | 498 -> 500 -> 502 / 646 | 1 | 2 | 2.39 -> 2.36 -> 2.36 |

At each step no correct confirmation is lost and no false merge is added (line-by-line diffs in `ai/runs/2026-11-27_i5_p31/day_*`). The v2.7 rename alone changes no line.

With the LLM layer (M3a, `gemini-3.1-flash-lite`, `--flag-non-whisky`), rules + M3a + server steps, label input, against P46 (I4, 2026-11-17) and 2026-11-21, which are identical on I3:

| | Top-1 | FM | wrong CR (per run) | hard lines / photo | not-whisky note: non-whisky right · whisky wrong · unknown |
|---|---|---|---|---|---|
| dev r1, r2: 11/21 -> now | 625 -> 630 / 804 | 0 | 3, 3 -> 3, 3 | 2.69, 2.66 -> 2.59, 2.55 | 16/16 · 0 · 0 both |
| I3 full r1-r3: P46 -> now | 500 -> 502 / 646 | 1 | 3, 3, 5 -> 2, 2, 4 | 1.67, 1.67, 1.70 -> 1.55, 1.55, 1.58 | 4/4 · 0 · 0 |
| I3 ops r1-r3: P46 -> now | 511 -> 513 / 646 | 1 | 3, 3, 3 -> 2, 2, 2 | 1.58, 1.58, 1.61 -> 1.45, 1.45, 1.48 | 4/4 · 0 · 0 |

- The one false merge is still "Ardbeg Anthology". Every line that changed against 11/21 is a Glenmorangie line or "브룩라디 더 클래식", except "브룩라디 포트샬롯" in three runs: the photo's M3a input changed, it stays a choice with the right product.
- **Fixed on the test set:** the Glenmorangie ages and the article rule were set after looking at I3 lines, so the I3 numbers include those fixes.
- API calls: Gemini 32 (free key, all first attempts), OpenRouter 0, CLOVA 0.

Tests:

- New: `backend/tests/test_accepted_ages.py` (26), `backend/tests/test_linking_guards.py` (missingAge), `backend/tests/test_resolve_staged.py` (brand + age only lines, the article rule), `ai/eval/test_i5_p59.py`, tests for `kind_hint` and the harness options. Fixed value: the I3 asis catalog digest for v2.7.
- In a clean checkout of this branch (no run records on disk): backend 1189 passed, 1941 skipped (need a database), 0 failed (`tests/test_pdf_*.py` and `test_run_uat_inputs.py` not collected: no `pypdfium2` locally). `ai`: 392 passed, 1 skipped (CLOVA keys not set), 1 failed: `test_reencoded_ocr_cache_without_provenance_stops` (a Windows path separator), failing before this branch. Regression check on the 15 photos: pass.
- Coverage (branches): `accepted_ages.py`, `linking_guards.py`, `pick_check.py`, `llm_layer.py`, `types.py` 100%, `staged.py` 97%; the measurement scripts 95% together.

Not verified:

- The tests that need a database (one new: the database catalogs fill the accepted ages); menu import with real extracted ages or with `MATCHING_MISSING_AGE_GUARD=true`.
- The Glenmorangie ages and the new name were checked against trade press on 2026-11-27 (The Original 12, Lasanta 15 since 2025, Quinta Ruban 14, The Nectar 16). The older age of Nectar D'Or is reported differently by source, so no older age is accepted for it.
- The end-to-end run with Gemini 3.8 Flash extraction (about $0.92 per run of 33 photos): after the OpenRouter extraction PR is on `main`.

## Notes for reviewers (optional)

- The accepted-ages table is keyed by product id. It works because `scripts/seed_catalog.py` loads products with the ids of `catalog_v2_service.json`; a product created in the database some other way has none.
- The article rule needs another word of the line to fit the product: the first version (an article always fits) put The Nectar on "글렌모렌지 더 시그넷", and a test now pins that it does not.
- `ai/eval/match_eval.py` (the frozen pre-P47 harness) does not fill the accepted ages; changing it would release another file from the P30 freeze.
- `test_server_steps_add_candidates_and_never_confirm` failed once in seven runs on the 11/27 night run (cause unknown) and not since.
- `.gitignore`: both this branch and the OpenRouter branch append a block at the end; the second to merge resolves a small conflict by keeping both.

## After merge

- Load catalog v2.7 into the production database with the Seed catalog workflow (`dry-run`, then `apply`): Lasanta becomes 15 and Nectar D'Or is shown as The Nectar. The accepted ages and the rules apply on deploy without it.
- No secret or migration. `MATCHING_MISSING_AGE_GUARD` stays unset (false).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
