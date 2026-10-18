# I2-A7/A8 — Nearby Bars (500 m) Android Integration and Test Evidence

**Date:** 2026-10-19  
**Owner:** Android frontend  
**Status:** Android CI **passed** (run 39138175980 at `c59edcee`); Backend A9 PR #43 **merged** (`a74dccb6`) and main deploy CI **passed** (run 39137220473). The Android frontend owner **reported successful normal operation on a physical Android device** on 2026-10-19. This is a user-reported device smoke-test result, not an independently observed or scenario-by-scenario test transcript. A direct unauthenticated HTTP probe, systematic negative cases, exact active-bar completeness, and screenshots/device metadata remain unverified.

This is an English, repository-side draft for the team Testing Documentation Wiki. It follows the course **4 — Testing Documentation Guidelines** (Plan vs Results) and the previously agreed 10-column Section 3.1 test-case format. **The live Testing Documentation Wiki registry could not be retrieved**; identifiers below are provisional and must be checked for collisions before adding official Wiki cases.

## 1. Requirement, source of truth and scope

- A7: on-demand foreground precise location, filter **all eligible active bars** within 500.0 m, distance-sort, swipeable carousel; Guest and member both supported.
- A8: same selected bar ID controls card highlight, Kakao label highlight/camera focus, marker-click→card sync and Bar Detail navigation; handle denied permission, empty, network and map failures.
- Confirmed Backend contract: PR #43, `docs/frontend_backend_api_spec.md` section 3.12. `GET /api/search/nearby-bars?lat=...&lng=...&radiusMeters=500` is public, works for Guests, returns **all active bars**, no pagination or truncation. Server provides integer rounded `distanceMeters` and a nullable `menuUpdatedAt`. **PR #43 is merged and its main-branch deployment job passed; a live unauthenticated GET has not been confirmed.** Earlier routes (`/api/bars` operator-only and whisky `/api/search/bars`) must NOT be used as Nearby substitutes.
- No Backend or AI code was modified here. `BackendNearbyBarsRepository` calls the real section 3.12 public endpoint using the existing `ApiClient`; the response maps to domain bars without client Haversine filtering or resorting. If the server has not deployed PR #43, a 404 is shown as a recoverable deployment error, NOT as an empty result. No fake bars in production UI.
- Latest Figma `BottleMap-Wireframe-I2` S0/S1 (node `5:3`/`5:38`) places a `내 주변 바` carousel next to a `Nearby Map` tile on Search home. This branch now renders the real server-sourced horizontal home carousel and a map-entry tile **after the user opted in and loaded nearby results**. Before permission/data are available, the home preview is a navigation prompt, never sample bars. The full carousel + map screen lives on the Nearby route, and the two destinations share a **Customer-graph ViewModel** so selection, bars and user location do not refetch on normal navigation. Current app still lacks Figma Bottom Navigation (pre-existing gap, not an A7/A8 introduction). Human review should verify small Portrait layout and pixel-level Figma placement.
- Android stays Portrait-only. No background location permission or updates, no location storage. The Android OkHttp Debug BASIC logger bypasses the `/api/search/nearby-bars` URL so it does not log coordinates. **Server URL access logs still contain lat/lng, explicitly disclosed in Backend API spec 3.12.3; ask Backend owner to review log redaction/retention policy.**
- Personal-data principle: only a single location fix in foreground, used in memory for the request and distance calculation. Check location service access/recovery on device.

## 2. Architecture and resolved data-interface blocker (deploy CI passed)

```text
Customer Search (real carousel preview + Map tile after first user opt-in) -> Nearby Route
  -> on-demand foreground permission (NONE/APPROXIMATE/PRECISE/PERMANENTLY_DENIED)
  -> AndroidNearbyLocationSource (Fused Location, cancellable single fix)
  -> BackendNearbyBarsRepository (ApiClient, public GET /api/search/nearby-bars)
      request lat + lng + radiusMeters=500, no Authorization
      response complete items[]; server-filtered and sorted, no pagination
  -> NearbyBarsResponseDto.toNearbyBars()  // validated, dedup ID, NOT re-filtered
  -> Customer-graph-scoped NearbyBarsViewModel.StateFlow (Success/Empty/Error)
  -> Search-home LazyRow preview + Nearby-screen LazyRow + Kakao labels (same selectedBarId)
  -> selected bar Detail route
```

**Authoritative boundary:** Backend PR #43 includes bars when **rounded integer** `distanceMeters <= radiusMeters`; this includes raw 500.4m rounded down to 500m. The old pure Haversine filter in `NearbyBarsRepository.kt` remains as a unit-test utility, but is **not used on production API results**. The frontend keeps the server-provided order/distance and deduplicates IDs while rejecting malformed coordinates/distance as a response error.

**Interface resolution:** A9 PR #43 supplies the complete public contract, including active bars with unpublished/empty menus. **Merged** via PR #43 (`a74dccb6`); the main-branch Backend deployment job passed. The app's normal operation has been reported as successful on a physical device by the Android frontend owner (2026-10-19); direct guest HTTP response, complete radius catalog, and targeted location-error scenarios still need separately recorded evidence. No backend changes made in this Android PR. Dependency tracked in issue #42.

**Privacy:** The HTTP GET necessarily sends coordinates in its URL, which the Backend currently logs. No Android log stores the nearby URL. This does **not** imply the coordinates are absent from server access logs; check Backend owner’s retention/redaction policy.

## 3. Unit and integration test plan — provisional Section 3.1 cases

Columns: **ID, Title, Basis, Level, Preconditions, Steps, Expected Result, Owner, Test, Status**. IDs beginning `A7A8-DRAFT-` are placeholders until reconciled with the Wiki registry.

| ID | Title | Basis | Level | Preconditions | Steps | Expected Result | Owner | Test | Status |
|---|---|---|---|---|---|---|---|---|---|
| A7A8-DRAFT-01 | 500m boundary inclusive | A7 500m | Unit | Fake coordinates | Feed 499m, 500m, 501m | First two included; last excluded | Android | `radiusIncludesInsideAndExactly500mAndExcludesOutside` | Written; passed in Android CI run 39136004949 |
| A7A8-DRAFT-02 | Distance/order/dedup | A7 distance sort | Unit | Duplicate candidate IDs | Pass unordered candidates | Sorted nearest first; one card per ID | Android | `sortsByDistanceThenIdAndRemovesDuplicateBarIds` | Written; passed in Android CI run 39136004949 |
| A7A8-DRAFT-03 | Invalid coordinates | A7 coordinate validation | Unit | Null, NaN, range errors | Filter invalid bars | Discard invalid candidates; no fabricated points | Android | `excludesMissingInvalidNonFiniteAndSwappedCoordinates` | Written; passed in Android CI run 39136004949 |
| A7A8-DRAFT-04 | Denied/approximate | A7 permission handling | Unit | Fake location/source | Reject or approximate-only | No location/network request or 500m claim | Android | `permissionDeniedAndApproximateDoNotRequestLocation` | Written; passed in Android CI run 39136004949 |
| A7A8-DRAFT-05 | Loading/Success/Empty | A7 state transitions | Unit | Fake sources | Allow precise, fetch nonempty/empty | Loading→Success or Empty | Android | `precisePermissionTransitionsThroughLocationAndBarsToSuccess`, `empty500mResultIsDistinctFromBackendFailure` | Written; passed in Android CI run 39136004949 |
| A7A8-DRAFT-06 | Network Retry | A7 error handling | Unit | First fetch fails | Trigger Retry after restoring source | One retry and Success | Android | `errorRetrySucceedsWithoutAutoPermissionPrompt` | Written; passed in Android CI run 39136004949 |
| A7A8-DRAFT-07 | API not yet deployed | A7 deployment handling | Unit | Fake HTTP 404 | Request nearby | Visible deployment error, not fake Empty | Android | `api404BeforeBackendDeploymentIsNotDisplayedAsEmpty` | Written; passed in Android CI run 39136004949 |
| A7A8-DRAFT-08 | Selection sync | A8 card/marker focus | Unit | Fake 2 bars | Select from card then marker | Same ID in SavedStateHandle; unknown ID ignored | Android | `carouselAndMarkerSelectionBothUseSameSavedBarId` | Written; passed in Android CI run 39136004949 |
| A7A8-DRAFT-09 | Resume/permission revoke | A7 lifecycle | Unit | Fake in-flight state | Revoke permission | Pending request canceled, PermissionRequired | Android | `permissionRevokedWhileLoadingIsHandled` | Written; passed in Android CI run 39136004949 |
| A7A8-DRAFT-10 | Repeat navigation refresh | A7/A8 lifecycle | Unit | Fake loaded results | Recheck precise permission | No extra location/catalog request | Android | `backgroundPermissionRecheckDoesNotRepeatSuccessfulNetworkRequest` | Written; passed in Android CI run 39136004949 |
| A7A8-DRAFT-11 | Real permission & fix | A7 location | Device | Android physical device (model not recorded) | Allow precise / deny / approximate / disable GPS | Appropriate state and no background prompt | Android | Manual scenario | General normal-operation smoke reported successful by owner, 2026-10-19; individual permission/disabled-GPS cases **not itemized** |
| A7A8-DRAFT-12 | Real carousel/map/end-to-end | A7/A8 integration | Device | **A9 merged; deploy CI passed; Android device available** | Swipe/select markers/open Detail/back | Complete 500m active bars, synced marker, no overlay | Android+Backend | Manual scenario | **User-reported general E2E smoke PASS (2026-10-19)**; individual marker/carousel/back steps and completeness not separately documented |

Additional automated contract tests: `NearbyBarsDtoContractTest` deserializes exact A9 JSON including `menuUpdatedAt: null`, confirms server-rounded 500m inclusion without local refiltering, preserves order, deduplicates IDs and rejects malformed input; `NearbyBarsViewModelTest.serverIncludedRounded500mBarIsNotLocallyRefiltered` protects the edge case. No test uses production Google/Supabase/Kakao/Location API in unit tests; use interfaces and fakes. Coverage target for this new domain logic should be reviewed with team; do not invent a numerical project threshold.

## 4. Exact reproduction and CI

Run from repo root:

```powershell
.\gradlew.bat :app:lintDebug :app:testDebugUnitTest :app:assembleDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

New Android source and tests are under `android/**`, which the merged `.github/workflows/android-ci.yml` `dorny/paths-filter` explicitly matches. Draft PRs trigger Android CI on `opened`/updates. Expected job names:
- `Android / changes`
- `Android / lint`
- `Android / unit tests`
- `Android / debug APK`

CI can confirm compilation, JVM state tests, and APK packaging. CI **cannot** validate actual location permissions, live catalog, complete Nearby radius results, or native Kakao GL behavior. Do not bypass failing tests or conflate a green CI with feature DoD.

## 5. Results and evidence (update only after execution)

| Component | Framework | Planned goal | Actual | Date | Command / Report |
|---|---|---|---|---|---|
| Distance + selection + A9 DTO contract | JUnit 4 / Moshi | 500m, rounded-server edge, invalid/dedup, state/selection and JSON fixture checks pass | **Pass: Android unit test job** | 2026-10-18 | Android CI run 39136004949 (`:app:testDebugUnitTest`), unit report artifact |
| Location/permissions | Manual S22/S23 | Precise/approximate/deny/timeout/disabled covered | Owner reports normal operation PASS; negative-case matrix not itemized | 2026-10-19 | Owner's chat report; no model/OS/screenshots supplied |
| Multi-marker and carousel | Kakao Maps SDK device | Swipe, marker focus, return/back, no duplicate | Owner reports normal A7/A8 device operation PASS; individual interactions not itemized | 2026-10-19 | Owner's chat report; no recording supplied |
| Android Lint | Gradle/GitHub Actions | Pass | **Passed** | 2026-10-18 | Run 39136004949, `Android / lint` artifact |
| Debug APK | Gradle/GitHub Actions | Pass | **Passed** | 2026-10-18 | Run 39136004949, `Android / debug APK` artifact |

**Observed verification:** GitHub Actions Android CI [run #39136004949](https://github.com/snuhcs-course/swpp-2026-project-team-19/actions/runs/39136004949), PR #41 commit `afacf946d4d4a9665c03592770fa7665a64d65a7`: `Android / changes`, `Android / lint`, `Android / unit tests`, `Android / debug APK` all **success**. The preceding run #39135192059 had 73 executed unit tests and **1 failure**, `missingRequiredFieldIsNotSilentlyInvented`, because the nullable `menuUpdatedAt` can decode to null when omitted by Moshi. We corrected the test to assert the required `distanceMeters` field is present; the subsequent run is green, without skipping any tests. CI ran locally isolated JUnit tests; no production location/Kakao services were exercised. Backend A9 PR #43 is **merged** (`a74dccb6`). Main Backend CI/CD run [39137220473](https://github.com/snuhcs-course/swpp-2026-project-team-19/actions/runs/39137220473) passed both `backend-tests` and `deploy`, including the server version check. **No direct live guest HTTP GET was verified** from this execution environment (the configured host did not resolve here); this is not evidence of a live API response or physical-device success. **Only a user-reported, general physical-device smoke has passed; do not claim individual negative cases or exhaustive physical-device coverage.**

Test counts, pass/fail, dated commit SHA and coverage **must be copied from actual runs**. The project course guideline requires English Testing Documentation on the **team GitHub Wiki** and a PDF submission at iteration close; this repository draft is not a substitute for publishing/updating that Wiki.

## 6. Physical-device smoke result and evidence provenance (2026-10-19)

- **Reported by:** Android frontend owner, in the ongoing implementation chat.
- **Report (Korean):** "실기기 테스트 완료. 정상 작동 확인" ("Physical-device testing completed; confirmed normal operation").
- **Recorded result:** A7/A8 normal-operation device smoke **PASS (user reported)**. This confirms the owner's overall observation, but does **not** separately establish device model/OS, guest-vs-member mode, exact location accuracy, every carousel/marker interaction, or negative scenarios (deny/permanent deny/approximate location, GPS off, network error, map SDK failure).
- **Independent verification:** Android CI #49 passed at prior documentation commit `c59edcee`; Backend deploy job passed. No direct guest HTTP GET was accessible from the assistant's environment. No video/screenshots or device log attached.
- **Remaining evidence:** Record device model/Android version, mode/permission choices, scenario-level observed results and any screenshots/video before claiming the entire manual matrix is passed. Backend location access-log retention review and official Testing Documentation Wiki publication are separate follow-ups.

## 7. AI-assisted development trace

- AI role: audited source of truth and current API rights; wrote Android-only location, filtering, ViewModel, screen, native map, tests and this draft.
- Human role: reported normal physical-device operation on 2026-10-19; still needs to record device/OS and specific steps/evidence, verify direct guest HTTP GET and negative permission/map/network cases where required, review server URL access-log retention, visually check Figma/home layout and existing Bottom Navigation gap, and publish official testing evidence in the Wiki.
- **Human elapsed / Agent elapsed:** not instrumented; 3.5h + 2.5h are estimates, not measured work time.
