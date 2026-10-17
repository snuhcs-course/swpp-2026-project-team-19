# BottleMap I2 P31/P32 — Portrait-only UI State & Lifecycle Stabilization

Date: 2026-10-18
Scope: Android frontend only. Source: latest `main` after merged PR #35, existing I2 navigation/API contracts, Task 4 requirements.

## Design decision (P32 scope adjustment)

**Decision (user-confirmed):** BottleMap is **Portrait-only**. The existing `android/app/src/main/AndroidManifest.xml` already declares `android:screenOrientation="portrait"` on `.MainActivity`; this branch does **not** change/add any manifest orientation rule.

**Deviation from original course task I2-16B:** the original P32 mentions verifying screen rotation. Under the project’s Portrait-only decision, landscape layouts, orientation-change UI implementation and rotate-to-landscape acceptance tests are deliberately omitted. This is a **test-scope adjustment**, not a claim that Activity recreation or process recreation is unsupported.

**Still required:** background/foreground transitions, Activity recreation (e.g., Developer options > Don't keep activities), minimum state after process recreation, IME/system bars, small **portrait** screens, font scale, navigation and authentication session restoration. Review this adjustment when filling out the course iteration report.

## Pre-change inventory and ownership

| Screen | State owner | Existing behavior | P31/P32 stabilization |
| --- | --- | --- | --- |
| Customer Search | `rememberSaveable` query and navigation guard in `SearchScreen.kt` | Query retained on normal Back and Activity recreation; blank/too-long validation | Root `safeDrawingPadding()` and `imePadding()` protect content against bars/IME |
| Search Results | `SearchResultsViewModel` and query navigation argument | Loading/Success/Empty/Error/Retry and request-version protection already exist; response list held by ViewModel | Invalid new query now also cancels/invalidates stale request; errors/empty/loading panels scroll on narrow or font-scaled portrait |
| Bar Detail | `BarDetailViewModel` and barId navigation argument | Loading/Success/Empty/Error/Retry already exist; same barId avoids re-fetch, stale request version guarded | Reject response with another barId as recoverable Error; status panel scrolls |
| Kakao Map | `BarLocationMapScreen`, destination-scoped detail VM and native SDK | SDK lifecycle `start/pause/resume/finish`, retry, coordinate validation, pinned geo marker already exist | On short portrait height omit only redundant second address card; avoid a hard minimum height that could crowd out the map; let error+retry scroll |
| Google/Supabase Auth | Activity-level `AuthViewModel`, SDK-persisted sessions | Guest/SignedIn and session restore/logout; stale auth generations handled by merged PR #35 | Regression review only; auth design unchanged |
| Navigation | `rememberNavController`, route args (`query`, `barId`) and back stack `savedStateHandle` flags | Back retains prior destinations; invalid query and BAR_NOT_FOUND are one-shot flags | No new large response saved in `SavedStateHandle` or Bundle |

**Data restoration policy:** persist small inputs (search text, route query, selected barId) with existing Compose saveable state/navigation arguments. On new ViewModel/process restoration, re-fetch API results from those route arguments, rather than storing large result DTO lists in `SavedStateHandle`. Auth session is restored by Supabase SDK. A hard `force-stop` is not assumed to restore the identical back stack.

## Automated test coverage

**Existing tests (reused):**
- `SearchResultsViewModelTest`: search success/empty/error/retry, query validation, stale response, BAR_NOT_FOUND refresh; request-version guard.
- `BarDetailViewModelTest`: menu states, nullable option fields, empty menu distinction, retry with preserved barId, no re-fetch for same barId, stale response.
- `BarMapTargetTest`: missing/out-of-range/nonfinite coordinates, distinct selected bar targets.
- `AuthViewModelTest`: Guest/SignedIn/restore/logout and session failure flow.

**New P31/P32 cases:**
- Invalid/blank new query invalidates even an uncancellable older search response.
- Repeated identical search while Loading triggers only one request.
- New results ViewModel can re-fetch a saved navigation query after recreation.
- Bar Detail refuses a response carrying a different barId and retries the original selected ID.
- New Bar Detail ViewModel can re-fetch the saved navigation barId after recreation.

Unit tests establish ViewModel transitions and restoration primitives; they **do not** replace actual Compose, Kakao native SDK, keyboard or Activity recreation tests.

## Manual validation matrix (portrait only)

Log device model, OS, viewport/density, font scale, Git commit and pass/fail; store screenshots outside Git if they contain account data.

| Area | Steps | Expected |
| --- | --- | --- |
| Search Loading→Success/Empty | Guest → Search known and unmatched terms | Appropriate state; entered text retained |
| Search Error→Retry | Disable network, Search, re-enable network, Retry | Same query and one new request; no blocked search |
| Duplicate/stale search | Rapid taps/back/query change, slow or mocked response | Latest search wins; no old results overriding new state |
| Detail Empty/Error→Retry | Select bar with no menu; disable network/retry | Same barId; empty/error messages and Retry accessible |
| Back stack | Search → Results → Detail → Map → Detail → Results → Search | Query intact, selected bar intact, normal Back doesn't refetch results |
| Invalid/missing coordinates | Use defensive unit fixtures or a deliberately invalid test fixture (do not change production API) | No fake default location or SDK crash |
| Map lifecycle | Enter and leave before SDK readiness; background/foreground; repeat map visits | No crash, duplicate pin, wrong pin, or permanent stale MapView |
| Auth lifecycle | Guest; signed-in account; background; logout; invalid session | Public features remain open and old token/account not reintroduced |
| Small portrait | S22/S23, narrow ~320–360 dp viewport, large font (1.3× and above) | Back/Retry accessible, result and menu scroll, map interactive |
| IME/system bars | Tap Search, open keyboard, enter long input, hide keyboard | Input and submit accessible; no navigation/system-bar overlap |
| Activity recreation | Developer options → Don't keep activities; background and return from Search, Results, Detail and Map | Query/barId and destination recover or safely refetch; no crash |
| Process recreation | Open Results/Detail then background and kill *background process only*, restart from system task | Minimum route and session consistent; safe refetch; not expected after force-stop |

Do not change device orientation to test landscape; orientation lock is an explicit feature decision.

### Windows / Android Studio commands

Run from repository root (directory containing `gradlew.bat`):

```powershell
git fetch origin
git switch --track origin/feature/i2-p31-p32-ui-state-lifecycle
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

If the local branch already exists, use `git switch feature/i2-p31-p32-ui-state-lifecycle` and `git pull --ff-only`. No production configuration values or auth tokens should appear in shared logs.

Examples of lifecycle checks after device installation:

```powershell
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $adb devices
& $adb shell am force-stop com.zerotoone.bottlemap
& $adb shell am start -n com.zerotoone.bottlemap/.MainActivity
```

Note: `force-stop` demonstrates clean app restart, **not** guaranteed same-screen back-stack restoration. For Activity recreation use **Developer options > Don't keep activities**, return via Recents. For system-initiated process restoration, background the app first and use `adb shell am kill com.zerotoone.bottlemap` (may be ignored by Android if not eligible); verify actual behavior on device.

## Definition of Done and evidence status

P31: implementation + new unit cases added. DoD requires `testDebugUnitTest` PASS and physical-device search/detail/back regressions.

P32: orientation policy retained/documented; small-screen/IME layout code added. DoD requires physical-device small portrait, Activity recreation, background/map lifecycle, auth/guest regression and debug build PASS.

**This document is not evidence that those tests ran.** Confirm and date the results after human device verification.

## Course traceability

- Task: I2-P31 + I2-P32, planned 5 human hours (estimate, not recorded actual).
- Decision: Portrait-only removes landscape rotation tests, not Activity/process recreation tests.
- AI support: existing code/contract review, minimal frontend fixes, tests, test/decision documentation.
- Human to verify: Gradle success logs, S22/S23 behavior, small viewport/font/keyboard, Android lifecycle and Google/Supabase + Kakao SDK interactions.
