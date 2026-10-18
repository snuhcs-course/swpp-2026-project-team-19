# I2-A7/A8 — Nearby Bars (500 m) Android Integration and Test Evidence

**Date:** 2026-10-18  
**Owner:** Android frontend  
**Status:** FRONTEND PROTOTYPE ONLY — publicly accessible complete Nearby-bar API is **not agreed**. Do not mark either task Done or this PR ready to merge as a complete feature.

This is an English, repository-side draft for the team Testing Documentation Wiki. It follows the course **4 — Testing Documentation Guidelines** (Plan vs Results) and the previously agreed 10-column Section 3.1 test-case format. **The live Testing Documentation Wiki registry could not be retrieved**; identifiers below are provisional and must be checked for collisions before adding official Wiki cases.

## 1. Requirement, source of truth and scope

- A7: on-demand foreground precise location, filter **all eligible active bars** within 500.0 m, distance-sort, swipeable carousel; Guest and member both supported.
- A8: same selected bar ID controls card highlight, Kakao label highlight/camera focus, marker-click→card sync and Bar Detail navigation; handle denied permission, empty, network and map failures.
- Latest Backend contract: `docs/frontend_backend_api_spec.md`, merged PR #39. `GET /api/bars` is **operator-only**. `GET /api/search/bars` only returns matches for a particular whisky query and may truncate at `limit`; `GET /api/search/bar-names` is a query-dependent public owner-application search. None is a complete Guest-accessible Nearby catalog.
- No Backend or AI code was modified. No fake locations/bars are shown in the real UI. `AwaitingPublicNearbyApi` returns an **explicit contract-unavailable Error**, not an empty result or partial nearby list.
- Latest Figma design `BottleMap-Wireframe-I2` page `00 — I2 Requirements Wireflows`, S0/S1 (node `5:3`/`5:38`): the Search screen **already contains** a `내 주변 바` Carousel (x=16, y=520, 204x150 in 360dp) next to a `Nearby Map` tile (x=228, y=520). It also depicts Bottom Navigation. Current Android Search does **not** implement that Bottom Navigation. As an **explicit temporary deviation**, this branch adds the `내 주변 바` heading and a `500m 내 주변 바 · 지도에서 보기` action below the search box; the Carousel + full map are on a separate Nearby route. Populating a home-screen carousel with real bars and confirming final Figma placement requires a complete public Backend Nearby API. No sample bar or fictitious bar card is rendered in production.
- Android stays Portrait-only. No background location permission or updates, no location storage/logging.
- Personal-data principle: only a single location fix in foreground, used in memory for the request and distance calculation. Check location service access/recovery on device.

## 2. Architecture and interface blocker

```text
Customer Search -> Nearby Route
  -> Runtime location permissions (NONE/APPROXIMATE/PRECISE/PERMANENTLY_DENIED)
  -> AndroidNearbyLocationSource (Fused Location, single cancellable fix)
  -> NearbyBarsSource.listNearbyCandidates(origin)
  -> filterNearbyBars(origin, completeActiveBarCatalog)  // <= 500.0 m inclusive
  -> NearbyBarsViewModel.StateFlow (Success/Empty/Error)
  -> LazyRow carousel + Kakao native label layer (selectedBarId only)
  -> selected bar Detail route
```

The production source remains `AwaitingPublicNearbyApi` until Backend owner agrees a **public contract** that provides complete active-bar data covering all 500 m candidates (either a radius-filtered endpoint with explicit completeness semantics or a fully paginated list available to Guest). The interface **must** specify:

1. Access for Guest and authenticated customer; no operator token.
2. Geometry: WGS84 latitude/longitude, center latitude/longitude and 500 m radius, radius semantics (straight line), boundary inclusion, precision.
3. Response: existing ID/name/address/lat/lng fields (map existing `BarDto` contract where applicable), active/inactive visibility, explicit missing-coordinate behavior.
4. Pagination/completeness: total rows or `nextCursor` and when there are no more pages. Never claim full nearby results from one truncated `GET /api/search/bars` page.
5. Empty/network/429/503 and rate limits. Preserve Guest access; avoid long-term location storage.
6. Confirm whether distance is server-calculated or frontend-calculated; **do not double-filter differently**. This branch has frontend Haversine filtering from a complete catalog.

**Blocking dependency owner:** Backend. **Frontend follow-up:** replace only `AwaitingPublicNearbyApi` with an adapter to the agreed Retrofit contract, add contract tests and on-device data completeness checks. No guessed Retrofit endpoint or DTO committed.

## 3. Unit and integration test plan — provisional Section 3.1 cases

Columns: **ID, Title, Basis, Level, Preconditions, Steps, Expected Result, Owner, Test, Status**. IDs beginning `A7A8-DRAFT-` are placeholders until reconciled with the Wiki registry.

| ID | Title | Basis | Level | Preconditions | Steps | Expected Result | Owner | Test | Status |
|---|---|---|---|---|---|---|---|---|---|
| A7A8-DRAFT-01 | 500m boundary inclusive | A7 500m | Unit | Fake coordinates | Feed 499m, 500m, 501m | First two included; last excluded | Android | `radiusIncludesInsideAndExactly500mAndExcludesOutside` | Written; run pending |
| A7A8-DRAFT-02 | Distance/order/dedup | A7 distance sort | Unit | Duplicate candidate IDs | Pass unordered candidates | Sorted nearest first; one card per ID | Android | `sortsByDistanceThenIdAndRemovesDuplicateBarIds` | Written; run pending |
| A7A8-DRAFT-03 | Invalid coordinates | A7 coordinate validation | Unit | Null, NaN, range errors | Filter invalid bars | Discard invalid candidates; no fabricated points | Android | `excludesMissingInvalidNonFiniteAndSwappedCoordinates` | Written; run pending |
| A7A8-DRAFT-04 | Denied/approximate | A7 permission handling | Unit | Fake location/source | Reject or approximate-only | No location/network request or 500m claim | Android | `permissionDeniedAndApproximateDoNotRequestLocation` | Written; run pending |
| A7A8-DRAFT-05 | Loading/Success/Empty | A7 state transitions | Unit | Fake sources | Allow precise, fetch nonempty/empty | Loading→Success or Empty | Android | `precisePermissionTransitionsThroughLocationAndBarsToSuccess`, `empty500mResultIsDistinctFromBackendFailure` | Written; run pending |
| A7A8-DRAFT-06 | Network Retry | A7 error handling | Unit | First fetch fails | Trigger Retry after restoring source | One retry and Success | Android | `errorRetrySucceedsWithoutAutoPermissionPrompt` | Written; run pending |
| A7A8-DRAFT-07 | Contract incomplete | A7 data completeness | Unit | Production source unavailable | Request complete Nearby catalog | Honest non-retryable Error; never fake Empty | Android | `catalogUnavailableNeverPretendsToBeEmpty` | Written; run pending |
| A7A8-DRAFT-08 | Selection sync | A8 card/marker focus | Unit | Fake 2 bars | Select from card then marker | Same ID in SavedStateHandle; unknown ID ignored | Android | `carouselAndMarkerSelectionBothUseSameSavedBarId` | Written; run pending |
| A7A8-DRAFT-09 | Resume/permission revoke | A7 lifecycle | Unit | Fake in-flight state | Revoke permission | Pending request canceled, PermissionRequired | Android | `permissionRevokedWhileLoadingIsHandled` | Written; run pending |
| A7A8-DRAFT-10 | Repeat navigation refresh | A7/A8 lifecycle | Unit | Fake loaded results | Recheck precise permission | No extra location/catalog request | Android | `backgroundPermissionRecheckDoesNotRepeatSuccessfulNetworkRequest` | Written; run pending |
| A7A8-DRAFT-11 | Real permission & fix | A7 location | Device | Samsung device | Allow precise / deny / approximate / disable GPS | Appropriate state and no background prompt | Android | Manual scenario | Not run |
| A7A8-DRAFT-12 | Real carousel/map/end-to-end | A7/A8 integration | Device | **Public backend Nearby contract available** | Swipe/select markers/open Detail/back | Complete 500m active bars, synced marker, no overlay | Android+Backend | Manual scenario | **Blocked: API** |

No test uses production Google/Supabase/Kakao/Location API in unit tests; use interfaces and fakes. Coverage target for this new domain logic should be reviewed with team; do not invent a numerical project threshold.

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
| Distance + selection | JUnit 4 | 500m/sort/invalid/dedup/selection checks pass | Pending | — | Android CI unit-test artifact |
| Location/permissions | Manual S22/S23 | Precise/approximate/deny/timeout/disabled covered | Pending | — | Device notes and screenshots |
| Multi-marker and carousel | Kakao Maps SDK device | Swipe, marker focus, return/back, no duplicate | Blocked on complete API | — | Device recording |
| Android Lint | Gradle/GitHub Actions | Pass | Pending | — | `Android / lint` |
| Debug APK | Gradle/GitHub Actions | Pass | Pending | — | `Android / debug APK` |

Test counts, pass/fail, dated commit SHA and coverage **must be copied from actual runs**. The project course guideline requires English Testing Documentation on the **team GitHub Wiki** and a PDF submission at iteration close; this repository draft is not a substitute for publishing/updating that Wiki.

## 6. AI-assisted development trace

- AI role: audited source of truth and current API rights; wrote Android-only location, filtering, ViewModel, screen, native map, tests and this draft.
- Human role: resolve public Nearby catalog with Backend owner, review exact Figma placement and accuracy policy, run Gradle/CI and physical-device location/Kakao regression, record results in the Wiki.
- **Human elapsed / Agent elapsed:** not instrumented; 3.5h + 2.5h are estimates, not measured work time.
