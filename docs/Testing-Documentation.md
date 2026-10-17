# BottleMap — Testing Documentation

## Table of Contents

- [Document Revision History](#document-revision-history)
- [1. Test Responsibility & Schedule (Iteration 2)](#1-test-responsibility--schedule-iteration-2)
  - [1.1 Test Ownership by Component](#11-test-ownership-by-component)
  - [1.2 Policy for New Code](#12-policy-for-new-code)
  - [1.3 When Tests Run](#13-when-tests-run)
  - [1.4 Required Checks Before Merge](#14-required-checks-before-merge)
- [2. Unit & Integration Testing (from Iteration 2)](#2-unit--integration-testing-from-iteration-2)
  - [2.1 Plan](#21-plan)
  - [2.2 Results](#22-results)
- [3. Test Cases (from Iteration 2)](#3-test-cases-from-iteration-2)
  - [3.1 Test-Case Format](#31-test-case-format)
  - [3.2 Requirements-to-Test Matrix](#32-requirements-to-test-matrix)
  - [3.3 Customer Search Cases (FR 4.1, 4.2)](#33-customer-search-cases-fr-41-42)
  - [3.4 Bar Detail Cases (FR 4.3)](#34-bar-detail-cases-fr-43)
  - [3.5 Login Cases](#35-login-cases)
  - [3.6 Owner Flow Cases](#36-owner-flow-cases)
- [4. AI Module Testing (from Iteration 3)](#4-ai-module-testing-from-iteration-3)
  - [4.1 Plan](#41-plan)
  - [4.2 Results](#42-results)
- [5. Acceptance Testing (from Iteration 3)](#5-acceptance-testing-from-iteration-3)
  - [5.1 Plan (Iteration 3)](#51-plan-iteration-3)
  - [5.2 Results (Iteration 4)](#52-results-iteration-4)
- [6. Alpha & Beta Testing (Iteration 5)](#6-alpha--beta-testing-iteration-5)
  - [6.1 Plan](#61-plan)
  - [6.2 Results](#62-results)

## Document Revision History

| Version | Date | Major Changes |
|---|---|---|
| 1.0 | 2026-10-14 | Initial document structure. Filled in Section 1 (test responsibility and schedule), and the shared test-case format in 3.1. |
| 1.1 | 2026-10-18 | Updated only Hojin Nam's Android CI policy, unit-test plan/results, and Android test-case traceability based on GitHub Actions PR #38 / test PR #40. Non-Android responsibilities and Iteration 3–5 sections retained unchanged. |

---

## 1. Test Responsibility & Schedule (Iteration 2)

### 1.1 Test Ownership by Component

Each component owner writes and maintains the tests for their component.

| Component | What is tested | Test types | Test location and naming | Owner |
|---|---|---|---|---|
| Android app (`android/app/`) | ViewModels, mappers, repositories, and the loading, success, empty, error, and retry states of each screen | Local unit tests (JUnit 4); manual tests on Galaxy S22 and S23 | `android/app/src/test/java/com/zerotoone/bottlemap/`, mirroring the package of the code under test; files named `*Test.kt` | Hojin Nam |
| Backend (`backend/`) | API routes, services, matching, database models, and migrations | Unit tests and API integration tests (pytest) against a PostgreSQL test database | `backend/tests/test_*.py` | Haeul Yang |
| AI pipeline (`ai/`) | Menu extraction, scoring scripts, and the evaluation set | Unit tests for the scoring scripts (pytest); evaluation runs on the held-out set (Section 4) | `ai/eval/test_*.py` | Jinwoo Park |

### 1.2 Policy for New Code

- The author of a feature or a fix writes or updates its tests and submits them in the same PR.
- A bug fix adds a regression test that fails without the fix.
- A change to the API contract updates the API spec and the backend tests in the same PR. The PR description states what the Android side must change, and the Android owner updates the Android tests.
- Tests never call external services: Gemini, Supabase, Google, or S3. Backend tests use the mock menu extractor and never call the Gemini API. Tests of Supabase token verification sign their own tokens with an ES256 key generated in the test and verify them against a fake JWKS, never against Supabase.
- Android unit tests never call a real server, including the deployed one. They use fake data that follows the API spec (`docs/frontend_backend_api_spec.md`), so they also work before the backend side is built.
- New test cases are recorded in Section 3 in the format of Section 3.1, with the requirement they verify.

### 1.3 When Tests Run

| When | What runs | Where |
|---|---|---|
| Every PR that changes `backend/`, `ai/catalog/`, `eval/`, or the backend workflow | Backend tests with coverage on PostgreSQL 18 | GitHub Actions (`Backend CI/CD`) |
| Every push to `main` with the same paths | The same backend tests, then deployment to production only if they pass | GitHub Actions (`Backend CI/CD`) |
| After each deployment | `GET /health` must report the commit that was just deployed as its `version`; otherwise the deploy job fails | GitHub Actions (`Backend CI/CD`, `deploy` job) |
| Every PR open/update/reopen and `main` push (Android-relevant paths detected in-job: `android/**`, shared Gradle files, Android workflow); manual dispatch available | `:app:lintDebug`, `:app:testDebugUnitTest`, `:app:assembleDebug`; unrelated PRs skip Android build jobs | GitHub Actions (`Android CI`, `.github/workflows/android-ci.yml`) |
| When `ai/eval/` changes | Scoring script tests, run locally by the AI owner | Local **(TBD: whether to run them in CI)** |
| Before each demo | End-to-end customer search and bar detail on Galaxy S22 and S23 with the build used in the demo | Manual |

### 1.4 Required Checks Before Merge

- Backend: the `backend-tests` job must pass, including a total coverage of at least 98% for `backend/app`, with line and branch coverage combined into one number (`branch = true`, `fail_under = 98`). A failing run blocks deployment of `main`.
- Android: for Android-relevant PRs, `Android / changes`, `Android / lint`, `Android / unit tests`, and `Android / debug APK` must pass. Checks appear in PR #38. The professor-owned repository does not allow the team to configure enforced Required Checks; the team's agreed policy is **do not merge on a failed CI check**, enforced manually by reviewers, not by GitHub Branch Protection.
- These checks are a team rule: a PR is merged only after its checks pass.

## 2. Unit & Integration Testing (from Iteration 2)

### 2.1 Plan

#### Frameworks

**Android (Hojin Nam).** Android JVM local tests use JUnit 4 (4.13.2) and `kotlinx-coroutines-test` with in-memory fake sources and gateways; no MockK or JaCoCo plugin is currently configured. UI models and HTTP DTOs are exercised with mapping assertions and Moshi deserialization tests. Android Studio / Gradle Wrapper test entry point is `:app:testDebugUnitTest`. Eight Android `*Test.kt` files contained 53 runnable tests at the passing CI baseline.


#### Coverage Goals by Architectural Layer

**Android (Hojin Nam; proposed forward-looking goals, not retrospectively achieved thresholds).**

| Architectural layer | Proposed line-coverage goal | Justification / verification status |
|---|---:|---|
| ViewModels (Search, Bar Detail, Auth) | ≥ 80% | Branching state transitions and error/retry paths; **not measured** (no coverage collector configured). |
| Mappers and DTO contract code | ≥ 85% | Deterministic contract parsing and conversions; **not measured**. |
| Android repositories / network adapters | ≥ 70% | Network boundaries to be isolated by fakes; **not measured**. |
| Jetpack Compose View / Kakao SDK UI | Excluded from JVM line-coverage target | UI behavior needs manual Galaxy S22/S23 checks (or later instrumentation); JVM tests do not validate rendering. |

These are proposed Android-only targets for the **next measured baseline**, pending team agreement. `:app:testDebugUnitTest` currently checks correctness but does not generate a coverage percentage or JaCoCo screenshot. Accordingly no numeric actual/goal attainment is claimed for Iteration 2. Adding coverage instrumentation is future work, separate from I2-P37/P38.


#### Scope & Exclusions

**Android (Hojin Nam).** Covered: customer search state/mapping, published bar-menu detail, coordinate validation for map navigation, Google/Supabase authentication state, DTO contract handling, and existing owner review-mapping unit tests. The main scenarios include Loading, Success, Empty, Error and Retry where applicable. All test doubles are local and deterministic; Android JVM tests never call the deployed Backend, Google, Supabase or Kakao services. Generated `BuildConfig`, third-party SDK internals, UI rendering, real device permissions, and emulator E2E are excluded from JVM tests. A green debug APK build does not prove on-device login, SDK map rendering, or end-to-end behavior.

**Android known contract discrepancy to review separately.** The repository test `SearchResultsViewModelTest.backendQueryValidationCodesReturnToInputWithoutRetry` treats `MISSING` as an editable InvalidQuery; API `3.10.5` specifies an application-bug/general error for a missing query parameter. No spec-aligned claim is made for that particular assertion. This is a follow-up frontend issue, not a reason to rewrite the API contract in a CI PR.


#### Reproducible Commands

**Android (Hojin Nam; run at the repository root).** Use the checked-in Gradle Wrapper 9.5.1, JDK 17, Android Gradle Plugin 9.3.1, compile SDK 37 and Android SDK command-line tools. CI uses Ubuntu 24.04 and `android-actions/setup-android@v3` with `platform-tools`; Gradle resolves the compile platform. No service credentials are required for the debug compile.

```bash
./gradlew :app:lintDebug --no-daemon
./gradlew :app:testDebugUnitTest --no-daemon
./gradlew :app:assembleDebug --no-daemon
```

The Android workflow is `.github/workflows/android-ci.yml` (`Android CI`). It runs on PR open/update/reopen/ready-for-review, `main` push, and manual dispatch; an internal change job filters `android/**` plus shared Gradle/build files and this workflow. Android checks are `Android / changes`, `Android / lint`, `Android / unit tests`, and `Android / debug APK`. Reports are uploaded as `android-lint-reports` and `android-unit-test-reports`; the APK is `android-debug-apk`. Job failures are not suppressed; even failed JUnit runs upload diagnostic reports. A Python standard-library summary counts tests/failures/errors/skips and rejects a successful but zero-test run.

**Team merge policy:** the professor-owned repository does not grant our team administration rights to configure Branch Protection. Team members have agreed not to merge a PR with any failed relevant CI check; **this is a manual review rule, not an enforced GitHub Required Check**. Android-related PRs must pass all four Android jobs. On non-Android PRs, only the change-detection job runs and Android build jobs are skipped. The `main` push trigger cannot be verified until PR #38 is merged.


##### Backend Local Environment

Database tests run against a separate PostgreSQL test database named by `POSTGRES_TEST_DATABASE` in `backend/.env` (same host and credentials as the app).

- The name must end with `_test`; otherwise the run stops. Each run drops and rebuilds the whole schema of that database from the Alembic migrations, so never point it at a development or production database.
- Each test runs inside a transaction that is rolled back, so tests do not affect each other.
- If `POSTGRES_TEST_DATABASE` is not set, the database tests are skipped without failing and the coverage falls below 98%. A local run counts as passing only when no database test was skipped.

### 2.2 Results

#### Test Run Information

**Android (Hojin Nam).** All evidence below is GitHub-hosted Actions execution, not local-only YAML review.

| Date (KST) | Revision / event | Command or check | Result | Evidence |
|---|---|---|---|---|
| 2026-10-18 | `0ccfaf7` / PR #38 | `:app:lintDebug`, `:app:testDebugUnitTest`, `:app:assembleDebug` | All three passed; test/lint reports and debug APK uploaded | [Successful PR run #39052646147](https://github.com/snuhcs-course/swpp-2026-project-team-19/actions/runs/39052646147) |
| 2026-10-18 | `4467a71` / isolated PR #40 | `:app:testDebugUnitTest` | Expected failure: 54 tests executed, 1 intentional `AssertionError`; lint and APK build passed | [Deliberate failure #39052068445](https://github.com/snuhcs-course/swpp-2026-project-team-19/actions/runs/39052068445) |
| 2026-10-18 | `a0053aa` / PR #40 after removal | `:app:lintDebug`, `:app:testDebugUnitTest`, `:app:assembleDebug` | All three passed; test-only PR #40 closed without merge | [Restored run #39052354880](https://github.com/snuhcs-course/swpp-2026-project-team-19/actions/runs/39052354880) |

Current working PR: [#38](https://github.com/snuhcs-course/swpp-2026-project-team-19/pull/38) (not merged). `main` push behavior and actual GitHub merge blocking are not verified. GitHub branch-protection administration is outside the team's permissions; manual no-red-check merging is the agreed policy.


#### Coverage by Component

**Android (Hojin Nam).** Required coverage collection is not yet configured. The following values are not coverage achievements.

| Component | Frameworks | Target | Actual | Date | Command / Report |
|---|---|---|---|---|---|
| Android ViewModel | JUnit 4 + coroutines-test | Proposed ≥80% | **Not measured** | 2026-10-18 | `:app:testDebugUnitTest`; [test artifact in run #39052646147](https://github.com/snuhcs-course/swpp-2026-project-team-19/actions/runs/39052646147) |
| Android Mapper / DTO | JUnit 4 + Moshi | Proposed ≥85% | **Not measured** | 2026-10-18 | Same run; no JaCoCo coverage report |
| Android Repository / network | Local fake sources | Proposed ≥70% | **Not measured** | 2026-10-18 | Same run; integration / line coverage pending |

No coverage screenshots or numerical pass-against-threshold judgments can be supplied without a coverage report. This limitation must be addressed before claiming a complete coverage-goal result for Iteration 2.


#### Test Counts & Known Failures

**Android (Hojin Nam).** At the passing PR baseline, 53 local JVM tests across 8 `*Test.kt` files passed. No failing test was retained. The isolated deliberate-failure run had 54 tests, 1 expected failed assertion; after removing that file the green baseline was restored. Tests that require actual Kakao map rendering, Google account selection, Supabase integration, and Galaxy S22/S23 end-to-end execution are **not covered by this CI** and must be tracked as device/manual work.

| Android test area | Test files | Tests in baseline | CI result |
|---|---:|---:|---|
| Customer search (mapping and ViewModel) | 2 | 17 | Passed |
| Bar detail, menu DTO and map target | 3 | 16 | Passed |
| Auth / session and current-user DTO | 2 | 18 | Passed |
| Existing owner review mapping | 1 | 2 | Passed |
| **Android total** | **8** | **53** | **53 passed, 0 failed** |

I2-P38 demonstrates **failure detection and recovery**, but NOT automatic Merge blocking. No fixed test case was deleted to obtain the final pass. The temporary `IntentionalCiFailureTest.kt` was on isolated PR #40 only and was removed before that PR was closed.


## 3. Test Cases (from Iteration 2)

### 3.1 Test-Case Format

Every test case in Sections 3.3 to 3.6 uses the fields below. Each section lists its cases as one table with these fields as columns.

| Field | Meaning | Example |
|---|---|---|
| ID | `<Area>-<NN>`. Areas: `CS` customer search (3.3), `BD` bar detail (3.4), `LG` login (3.5), `OW` owner flows (3.6) | `CS-07` |
| Title | The behavior checked, in one line | Known product with no bars returns an empty result |
| Basis | The requirements and spec sections the case verifies. Functional requirements are written as `FR<section>-AC<n>` (acceptance criterion `n` of that section in [[Requirements and Specifications]]), non-functional ones as `NFR-<n>`, and API spec sections as `API <section>`, where the section number refers to [`docs/frontend_backend_api_spec.md`](https://github.com/snuhcs-course/swpp-2026-project-team-19/blob/main/docs/frontend_backend_api_spec.md) in the repository | `FR4.1-AC6`, `NFR-8`, `API 3.10.4` |
| Level | `Unit` (runs without a device or a database: backend and AI pytest unit tests, and Android JVM local tests in `src/test`, including mappers and ViewModels), `Integration` (API with the test database), `UI` (Android Compose UI tests in `src/androidTest`, run on a device or an emulator), or `Device` (manual on Galaxy S22 and S23) | `Integration` |
| Preconditions | The data and app state before the test | Glenfiddich 15 is an active product, and no current menu board lists it |
| Steps | The request sent or the user actions | `GET /api/search/bars?query=글렌피딕 15년` |
| Expected Result | What can be observed when the case passes: HTTP status, `error.code`, response fields, or the screen state. Never the message text | `200`; one product in `matchedProducts` with `resultCount` 0; `items` is empty |
| Owner | The member who writes and maintains the test (Section 1.1) | Haeul Yang |
| Test | The automated test as `<file>::<test name>`, or `Manual` | `backend/tests/test_search_api.py::test_known_product_without_bars_has_matched_products_but_no_items` |
| Status | See the status values below | `Automated` |

Status values:

| Status | Meaning |
|---|---|
| `Automated` | An automated test exists and runs in CI |
| `Manual` | Checked by hand with the steps in the case |
| `Planned` | Due in the current iteration, but the test does not exist yet |
| `Deferred (I<n>)` | Moved to Iteration `n`, for example `Deferred (I3)`. Only ID, Title, Basis, and Owner are filled in until then |
| `Dropped` | No longer needed. The row stays with the reason in Expected Result |

Rules:

- This section is kept up to date in every iteration: new cases are added, statuses are updated, and deferred cases are filled in when their iteration starts.
- One case checks one behavior.
- Expected results come from the API spec and the requirements. If the code behaves differently, the case keeps the spec value and the difference is reported to the owner of that area.
- IDs are never reused or renumbered. A case that is no longer needed is marked `Dropped`, not deleted.
- Section 3.2 is built from the Basis column of every case.
- Pass and fail results are not recorded here; they belong in Section 2.2 and, for acceptance tests, Section 5.2.

A case for the Android side looks like this:

| ID | Title | Basis | Level | Preconditions | Steps | Expected Result | Owner | Test | Status |
|---|---|---|---|---|---|---|---|---|---|
| `CS-08` | Known product with no bars shows the no-bars empty state | `FR4.1-AC6`, `NFR-8`, `API 3.10.4` | `Unit` | The search response has one product in `matchedProducts` and an empty `items` | Map the response to the screen state | The no-bars empty state, not a blank list | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/CustomerSearchMapperTest.kt::knownProductWithoutBars_mapsToNoBarsEmptyState` | `Automated` |

### 3.2 Requirements-to-Test Matrix

**Android entries maintained by Hojin Nam (v1.0 baseline Sections 3.3–3.5 contained no case rows).** Other components' matrix entries are maintained by their respective owners.

| Basis | Android Test Case IDs |
|---|---|
| FR4.1-AC6 / NFR-8 / API 3.10.4 | CS-08, CS-09 |
| API 3.10.1 | CS-14 |
| API 3.10.3 | CS-10, CS-11, CS-13 |
| API 3.10.5 | CS-12, CS-15 |
| API 3.9 | BD-01, BD-03, BD-05, BD-06, BD-07 |
| API 3.9.1 | BD-02 |
| API 3.9.3 | BD-04, BD-08 |
| API 3.1 / 3.1.1 / 3.1.5 / 3.2 | LG-01–LG-08 |


### 3.3 Customer Search Cases (FR 4.1, 4.2)

| ID | Title | Basis | Level | Preconditions | Steps | Expected Result | Owner | Test | Status |
|---|---|---|---|---|---|---|---|---|---|
| `CS-08` | Known product with no bars shows the no-bars empty state | `FR4.1-AC6`, `NFR-8`, `API 3.10.4` | `Unit` | One matched product has resultCount 0 and items is empty | Map the API response to search screen state | Empty(NO_BARS), distinct from unknown-product empty state | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/CustomerSearchMapperTest.kt::knownProductWithoutBars_mapsToNoBarsEmptyState` | `Automated` |
| `CS-09` | Unknown product shows the unknown-product empty state | `API 3.10.4` | `Unit` | matchType none; matchedProducts and items empty | Map the API response to search screen state | Empty(UNKNOWN_PRODUCT) | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/CustomerSearchMapperTest.kt::unknownProduct_mapsToUnknownEmptyState` | `Automated` |
| `CS-10` | Search result maps prices, nullable pour size, and timestamp | `API 3.10.3` | `Unit` | Response contains bar, product, nullable pourMl and RFC 3339 time | Map response to UI model | Success with correct bar/product IDs, nullable pourMl, options and nonblank freshness display | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/CustomerSearchMapperTest.kt::success_preservesNullablePourAndParsesFractionalTimestamp` | `Automated` |
| `CS-11` | Valid search transitions Loading to Success | `API 3.10.3` | `Unit` | Fake customer source returns one result | Search with surrounding whitespace; advance coroutine scheduler | Loading then Success; fake receives trimmed query once | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/SearchResultsViewModelTest.kt::requestUsesTrimmedQueryAndTransitionsLoadingToSuccess` | `Automated` |
| `CS-12` | Network failure preserves query for Retry | `API 3.10.5` | `Unit` | Fake customer source fails once then succeeds | Search, advance; call Retry; advance | Recoverable Error then Loading then Success; same query requested twice | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/SearchResultsViewModelTest.kt::networkErrorThenRetryKeepsQueryAndSucceeds` | `Automated` |
| `CS-13` | Stale response cannot overwrite latest search | `API 3.10.3` | `Unit` | First fake request suspended; second returns no bars | Start first query; start second; release first result | The latest query's Empty(NO_BARS) state remains | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/SearchResultsViewModelTest.kt::oldResponseCannotOverrideNewerSearch` | `Automated` |
| `CS-14` | Korean input reaches repository without client alias matching | `API 3.10.1` | `Unit` | Fake source accepts Korean whisky query | Search with spaces around a Korean name | Trimmed Korean name sent unchanged; response determines Empty(NO_BARS) | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/SearchResultsViewModelTest.kt::koreanQueryIsSentWithoutClientSideAliasMatching` | `Automated` |
| `CS-15` | Blank or too-long query rejected locally | `API 3.10.5` | `Unit` | Fake source configured without remote calls | Search blank input and then 101-character input | InvalidQuery(BLANK) and InvalidQuery(STRING_TOO_LONG) without a network request | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/SearchResultsViewModelTest.kt::inputValidationStillRunsLocally` | `Automated` |


### 3.4 Bar Detail Cases (FR 4.3)

| ID | Title | Basis | Level | Preconditions | Steps | Expected Result | Owner | Test | Status |
|---|---|---|---|---|---|---|---|---|---|
| `BD-01` | Bar detail preserves menu entries, options and coordinates | `API 3.9` | `Unit` | Fake bar detail source returns published menu | Load selected bar ID; advance scheduler | Success with same bar ID, complete ordered menu options and actual latitude/longitude | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/BarDetailViewModelTest.kt::loadsGivenBarIdAndPreservesAllPublishedEntriesAndOptions` | `Automated` |
| `BD-02` | Unpublished menu differs from published empty menu | `API 3.9.1` | `Unit` | Response either has null menuBoardId or published board with no items | Map both responses | Empty(NO_PUBLISHED_MENU) versus Empty(NO_CURRENT_ITEMS) | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/BarDetailViewModelTest.kt::emptyMenuDistinguishesNoPublicationFromEmptyPublishedBoard` | `Automated` |
| `BD-03` | Nullable option data does not fabricate price units or labels | `API 3.9` | `Unit` | Menu contains nullable optionLabel and pourMl | Format representative menu options | Price preserved; no invented label or pour size | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/BarDetailViewModelTest.kt::nullableLabelsAndPourSizesDoNotInventValues` | `Automated` |
| `BD-04` | Network error allows retry for the same selected bar | `API 3.9.3` | `Unit` | Fake menu source fails once then succeeds | Load bar, advance; Retry; advance | Error(canRetry=true) followed by Success for the same bar ID | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/BarDetailViewModelTest.kt::networkFailureThenRetryPreservesBarIdAndSucceeds` | `Automated` |
| `BD-05` | Mismatched API bar ID cannot replace the selected bar | `API 3.9` | `Unit` | First fake response belongs to a different bar | Load bar, observe error, retry | Error then Success for original requested bar ID | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/BarDetailViewModelTest.kt::mismatchedResponseCannotReplaceSelectedBarAndRetryUsesOriginalId` | `Automated` |
| `BD-06` | Missing required bar name is rejected by DTO parser | `API 3.9` | `Unit` | JSON response lacks required name field | Deserialize response using Moshi | JsonDataException; no fabricated bar name | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/BarMenuDtoContractTest.kt::missingRequiredBarNameIsRejectedRatherThanFabricated` | `Automated` |
| `BD-07` | Invalid or missing coordinates do not create map target | `API 3.9` | `Unit` | Bar model has null, nonfinite, out-of-range or zero coordinates | Call validatedBarLocation for each value | Null map target; no default or fabricated location | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/BarMapTargetTest.kt::rejectsMissingOrInvalidCoordinatesWithoutDefaultLocation` | `Automated` |
| `BD-08` | BAR_NOT_FOUND disables Retry and returns to result refresh | `API 3.9.3` | `Unit` | Fake source throws BAR_NOT_FOUND | Load absent bar; inspect state and call Retry | Error(canRetry=false, refreshResultsOnBack=true); no repeated API call | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/BarDetailViewModelTest.kt::barNotFoundShowsBackActionAndDisablesRetry` | `Automated` |


### 3.5 Login Cases

| ID | Title | Basis | Level | Preconditions | Steps | Expected Result | Owner | Test | Status |
|---|---|---|---|---|---|---|---|---|---|
| `LG-01` | Absent session restores Guest mode | `API 3.1` | `Unit` | Fake auth session emits Guest | Create ViewModel and advance scheduler | Guest state without Google login gate | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/auth/AuthViewModelTest.kt::noSessionRestoresGuestInsteadOfShowingLoginGate` | `Automated` |
| `LG-02` | Restored session synchronizes current user | `API 3.1`, `API 3.2` | `Unit` | Fake session emits Authenticated; /api/me fake returns customer | Create ViewModel and advance scheduler | SignedIn with expected user ID, userType and one profile request | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/auth/AuthViewModelTest.kt::restoredSessionSyncsBackendUserAndBecomesSignedIn` | `Automated` |
| `LG-03` | Google credential success guards duplicate sign-in | `API 3.1.1` | `Unit` | Fake gateway and Guest session | Start Google sign-in twice; pass fake credential; advance | One attempt accepted; SignedIn without external Google/Supabase calls | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/auth/AuthViewModelTest.kt::googleSuccessAndRepeatedClickGuard` | `Automated` |
| `LG-04` | Canceled credential selection returns Guest and allows retry | `API 3.1.1` | `Unit` | Guest session with fake auth gateway | Begin sign-in; cancel; begin again | Guest state and next sign-in can start | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/auth/AuthViewModelTest.kt::googleCancelKeepsGuestAndAllowsRetry` | `Automated` |
| `LG-05` | Login failure still permits Guest access | `API 3.1.5` | `Unit` | Fake Google sign-in fails | Begin sign-in; report failure; continue as guest | SignInError followed by Guest | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/auth/AuthViewModelTest.kt::googleErrorThenContinueGuestDoesNotBlockSearch` | `Automated` |
| `LG-06` | Transient profile API error allows session-preserving Retry | `API 3.1.5`, `API 3.2` | `Unit` | Authenticated fake gateway returns NETWORK_ERROR then profile | Observe initial error; retry profile | Retry-capable SignInError followed by SignedIn; no logout on transient error | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/auth/AuthViewModelTest.kt::transientNetworkErrorKeepsSessionAndAllowsProfileRetry` | `Automated` |
| `LG-07` | Logout ignores late profile response | `API 3.1`, `API 3.2` | `Unit` | Authenticated fake gateway with delayed profile response | Start profile request; logout; release delayed response | Guest remains; stale response cannot restore SignedIn | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/auth/AuthViewModelTest.kt::logoutImmediatelyHidesIdentityAndIgnoresLateUncancellableProfileResponse` | `Automated` |
| `LG-08` | Nullable user profile fields deserialize without fabrication | `API 3.2` | `Unit` | Valid /api/me JSON has nullable email and displayName | Parse CurrentUserDto | userType preserved; null fields remain null | Hojin Nam | `android/app/src/test/java/com/zerotoone/bottlemap/ui/auth/CurrentUserDtoTest.kt::readsSignedInCustomerIncludingNullableProfile` | `Automated` |


### 3.6 Owner Flow Cases

## 4. AI Module Testing (from Iteration 3)

### 4.1 Plan

#### Evaluation Set

#### Ground Truth & Evaluation Design

#### Assertion Method per Case

#### Thresholds

#### Test Settings & Command

### 4.2 Results

#### Metrics Against Thresholds

#### Failure Analysis

## 5. Acceptance Testing (from Iteration 3)

### 5.1 Plan (Iteration 3)

#### User Stories

#### Acceptance Criteria & Test Procedures

### 5.2 Results (Iteration 4)

## 6. Alpha & Beta Testing (Iteration 5)

### 6.1 Plan

#### Alpha: Participants & Setting

#### Alpha: Scenarios

#### Beta: Release

#### Beta: Participants & Schedule

#### Feedback & Bug Handling

### 6.2 Results

#### Alpha Results

#### Beta Results

#### Beta Bugs & Fixes