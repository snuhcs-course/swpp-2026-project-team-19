# BottleMap Android CI — Testing Documentation v1.0 update proposal (I2-P37/P38)

<!-- AI-assisted with ChatGPT/GPT-6 for Hojin Nam, 2026-10-18. Human review and execution evidence required. -->

This is a proposed update to **BottleMap — Testing Documentation** (2026-10-14). It does not replace the team wiki. Merge the sections below into the wiki only after reviewing the actual Actions runs. Do not mark a test `Automated` before its CI execution is confirmed.

## Section 1.3 — When Tests Run (Android row replacement)

| When | What runs | Where |
|---|---|---|
| Every PR creation/update/reopen and each push to `main` | Android change detection; for Android-relevant changes, `lintDebug`, `testDebugUnitTest`, `assembleDebug`. A manual `workflow_dispatch` is also available. | GitHub Actions (`Android CI`), `.github/workflows/android-ci.yml` |

The Android change detector covers `android/**`, `build.gradle.kts`, `settings.gradle.kts`, `gradle/**`, `gradle.properties`, `gradlew`, `gradlew.bat`, and `.github/workflows/android-ci.yml`. Workflow-level `paths` are intentionally omitted to prevent missing required status checks on backend-only PRs.

## Section 1.4 — Required Checks Before Merge (Android row replacement)

On Android-relevant PRs, require:
- `Android / changes` (detection).
- `Android / lint`.
- `Android / unit tests`.
- `Android / debug APK`.

**Important**: job-level `if` skips Android jobs on backend-only PRs; GitHub evaluates skipped required jobs as successful. GitHub branch protection/ruleset registration remains an administrative task. A GitHub Actions failure **alone** is not proof that the PR cannot merge. Admin must verify enforcement. Avoid requiring the workflow name instead of actual job check names.

## Section 2.1 — Android Unit & Integration Testing Plan

- Framework: JUnit 4, `kotlinx-coroutines-test` for coroutine ViewModels; fake sources/gateways, no real network or external SDK account calls.
- Code under test: `android/app/src/main/java/com/zerotoone/bottlemap`.
- Test location: `android/app/src/test/java/com/zerotoone/bottlemap`, same package structure; filenames end in `Test.kt`.
- Gradle commands (repository root):
  - `./gradlew :app:lintDebug --no-daemon`
  - `./gradlew :app:testDebugUnitTest --no-daemon`
  - `./gradlew :app:assembleDebug --no-daemon`
- Environment: Ubuntu GitHub runner; JDK 17; Gradle Wrapper 9.5.1; AGP 9.3.1; compile SDK 37; no emulator required in PR.
- External service exclusion: production API, Supabase, Google account chooser, and Kakao Map rendering are not run in local unit tests. Debug APK may be built with empty BuildConfig credential fields; this does **not** establish that login or map SDK works.
- Build artifacts: `android-unit-test-reports`, `android-lint-reports`, `android-debug-apk` (installable APK when successful).
- Coverage goal: no new numeric Android coverage threshold agreed in v1.0. Record test counts by component; propose layer-specific percentage targets separately before adopting them.
- Device/manual verification remains Galaxy S22/S23 before demo.

## Section 2.2 — Android execution results (fill only from observed evidence)

| Run | Commit | Event | Lint | Unit test | APK | Reports | Evidence |
|---|---|---|---|---|---|---|---|
| Initial verification (feature branch) | `1f9c8b6` | push | Passed | Passed (53 tests) | Passed | Lint XML/HTML, unit test XML/HTML, APK | [Run 39051720904](https://github.com/snuhcs-course/swpp-2026-project-team-19/actions/runs/39051720904) |
| Intentional failing JUnit test | `4467a71` | PR #40 | Passed | **Failed (54 tests; 1 intentionally failed)** | Passed | Uploaded reports | [Run 39052068445](https://github.com/snuhcs-course/swpp-2026-project-team-19/actions/runs/39052068445) |
| Restored passing test | `a0053aa` | PR #40 | Pending | Pending | Pending | Pending | Run pending at documentation update |

Store the failing test code, failing job URL, runner log, final successful run URL, and explicit merge-block evidence. Record test pass/fail and run time here, *not* in Section 3 Status.

## Section 3.1 / 3.2 / 3.3–3.5 — Test-case recording

Current Testing Documentation v1.0 has only a **format example** `CS-08`, not an established ID registry in Sections 3.3–3.5. Before assigning new IDs, inspect the live wiki for newer rows; do not reuse any existing ID or mistake its example for a verified automated case.

The existing repository already includes test files:
- `ui/customer/CustomerSearchMapperTest.kt` and `SearchResultsViewModelTest.kt`: mapping, loading, query retention, retry and stale response.
- `ui/customer/BarDetailViewModelTest.kt` and `BarMenuDtoContractTest.kt`: detail data, options/nulls, missing menu, error/retry, selected bar ID.
- `ui/customer/BarMapTargetTest.kt`: coordinates, ID preservation, malformed/missing values.
- `ui/auth/AuthViewModelTest.kt` and `CurrentUserDtoTest.kt`: guest, login, session restoration, errors and logout.
- `ui/owner/ReviewDecisionMapperTest.kt`: owner review mapping.

Populate official cases with 10 required columns (ID, Title, Basis, Level, Preconditions, Steps, Expected Result, Owner, Test, Status) from the **current** Requirements & Specifications and API contract. Mark `Automated` only once the tests run successfully in CI; otherwise `Planned`. Rebuild Section 3.2 matrix from the final Basis columns.

## I2-P37/P38 Definition of Done

- P37: workflow committed, feature-branch Android CI successfully ran all three Gradle jobs and uploaded reports/APK; `main` trigger can only be verified after the workflow is merged into `main`, so P37 remains In Progress. Backend CI unchanged.
- P38: isolated failing JUnit test in draft PR #40; red unit-test CI verified (53 passing + 1 intentional failure), logs archived in Actions. The failing test was removed in commit `a0053aa`. Restoration CI and **enforced** merge-block verification remain outstanding; repository rulesets list is empty and branch protection read returned 403 for the linked account.
- Until all associated run and permission evidence exists, both tasks remain **In Progress**.
