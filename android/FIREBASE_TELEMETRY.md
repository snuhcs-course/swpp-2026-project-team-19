# I5-P17 / I5-P35 Android Firebase telemetry

Reference: the supplied `iter5_plan_v4.md`, appendix 3.2. No backend API or schema change.
Schedule: P17 and P35 are **Started**; device/Console evidence is required before completion.
Team Console access was reported complete by the user. No work-time or completion-date cells were edited.

## Build configuration

- Put the downloaded Android configuration at `android/app/google-services.json`. It is ignored by `android/.gitignore`; never put its contents in a PR, log or screenshot.
- Only when that file exists, Google Services and Crashlytics plugins are applied and Analytics/Crashlytics dependencies plus `src/firebase/java` are compiled.
- Otherwise `src/noFirebase/java` supplies `NoOpTelemetry`, without Firebase SDK runtime dependencies. `-PBOTTLEMAP_FIREBASE_ENABLED=false` explicitly tests this same path while preserving a developer's local file.
- AGP 9 uses `AndroidSourceSet.kotlin.directories` for the selected Kotlin directory. No flavors or extra APKs are introduced.
- `BOTTLEMAP_RELEASE_CHANNEL=dev|alpha|beta|release` sets the sole Analytics user property `release_channel`; default `dev`. Specify `alpha`, `beta`, or `release` explicitly for distribution builds. Exclude `dev` from tester denominators.
- Ordinary debug builds cannot collect. A verification debug APK requires `-PBOTTLEMAP_TELEMETRY_DEBUG_ENABLED=true` **and** the existing optional consent. DebugView alone does not enable collection or consent.
- CI lint/JVM tests explicitly use the no-SDK path. Debug APK jobs can read optional repository/production-environment secret `BOTTLEMAP_GOOGLE_SERVICES_JSON`, whose value is the entire JSON file. `android/ci/prepare_firebase.py` validates the package and writes it without printing its contents. Missing secret preserves NoOp CI. Fork PRs work without secrets. The secret has not been created or inspected in this task.
- A release runner can use the same environment secret and helper before building. Local release builds can use the ignored file. Existing signing configuration is preserved.

```powershell
# Verification of the no-SDK/CI mode; no need to rename the local JSON.
.\gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug "-PBOTTLEMAP_FIREBASE_ENABLED=false"

# Local signed Alpha bundle (requires the existing private signing/auth/map properties).
.\gradlew.bat :app:bundleRelease "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/" "-PBOTTLEMAP_RELEASE_CHANNEL=alpha"
```

## Requirement and event coverage

| Requirement | Android implementation / remaining evidence |
|---|---|
| P17 configuration, no-config fallback, Crashlytics | Optional source/dependency selection, lazy SDK initialization, shell-protected debug crash hook; test crash PASS reported by the Galaxy S23 tester on 2026-11-26 |
| P35 typed events and tests | `telemetry/` sealed events and enums, production Firebase sink, NoOp sink and test Fake; device events and final release_channel=dev PASS confirmed by the user on 2026-11-26; independent transport checks below |
| Consent and opt-out | Existing persisted default-off choice controls both collectors, independently of login |
| No ad ID, user ID, raw query/location/application/menu data | Manifest restrictions, enum-only event boundary, fixed endpoint/screen templates; actual device payload review remains |
| Development/Alpha/Beta/Release | Validated Gradle property and explicit debug collection gate |
| First-launch detailed notice | User explicitly chose to keep the current approved UI copy; the plan's longer sentence is not added |
| Privacy-policy Firebase disclosure | Backend-owned; live page content could not be verified in this task. Haeul must confirm actual collection, regions and retention |
| Report form event | `ReportProblemOpened` type exists; **no production emission** until P20 supplies the form and P25 implements the actual action. User confirmed P20 has not started |
| PDF import source | Typed value is reserved as specified; current Android photo picker accepts images only. No PDF UI or unsupported API is added |
| Not now | No Performance Monitoring, Remote Config, custom collection API, retention analysis, rage-click tracking, screen-frame metrics or saturation collector |

| Event | Trigger and interpretation |
|---|---|
| `search_completed` | Latest successful explicit product/brand or registered-bar-name search response. `has_results` counts available bar results (brand candidates require positive resultCount). Empty responses count false. Stale/cancelled/failed requests, GPS/sort refreshes and brand-product follow-ups do not inflate P18 search counts. Popular navigation is measured as popular detail discovery, outside typed-search denominators |
| `bar_detail_opened` | First acknowledged correct-bar response in the detail ViewModel, including an empty menu. Retry after an initial failure can produce the first open; normal back/recomposition does not. Source is search/popular or map/nearby discovery. Duration bucket is omitted for non-search sources and unavailable process-local timing |
| `menu_import_started` | Explicit nonempty upload attempt, with photo-count bucket. Mixed photo selections use the first selected photo's source. Picker/camera provenance survives saved picker state; pre-existing legacy entries fall back to gallery |
| `menu_import_failed` | Upload exception, or terminal failed extraction status (once per import per ViewModel). Polling connectivity errors use `api_error` instead of claiming extraction failure. Only allowlisted codes cross the boundary |
| `menu_review_opened` | First successful review load per ViewModel; reloads preserve the attempt |
| `menu_published` | Confirmed publish or acknowledged applied status after a lost response, once. Initial pending-card bucket is retained; monotonic time starts at the first successful review load |
| `menu_publish_failed` | Failed publication attempt, including draft/version conflict; no optimistic success |
| `owner_application_started` | First checkpoint after registration type selection, or resuming/submitting a draft; type claim/new |
| `owner_application_submitted` | Registration flow has completed its server-acknowledged submission and required uploads. This is client task completion, not the server's raw POST count |
| `owner_application_failed` | Submission/required-upload failure. DB aggregate remains authoritative if the POST committed before a later upload failed |
| `nearby_opened` | Discovery entry/changed permission state. Repeated identical callbacks in the same ViewModel are deduplicated |
| `sign_in_result` | Explicit sign-in attempt ends in success/cancel/error, with welcome/account origin. Restored sessions and duplicate callbacks do not add attempts |
| `report_problem_opened` | Pending P20/P25; never emitted for the current preparation dialog |
| `api_error` | `ApiClient.call`; fixed contract endpoint template, status enum, allowlisted code. Queries, UUIDs, server messages/bodies and exception prose are excluded. I/O failures retain the sanitized endpoint when available; coroutine cancellation is not an API failure |
| Automatic Analytics / Crashlytics | `first_open`, sessions, exposure, device/app distribution and crash/ANR reports after consent. Delivery and automatic SDK contents require manual observation |

Times are bucketed at 30/60/180 seconds and 3/10/30 minutes. They are never persisted. A process death drops an unfinished timing attempt. Ratios inferred from independent client events are task indicators, not exact server conversion or unique-search joins. Use the server read-only aggregates for cross-platform import/application/publication totals. User-day is the sum of each day's active app instances, with `dev` excluded; no account ID is set. Automatic IP-derived approximate geography, device information and app-instance IDs still require disclosure. Firebase device/session counts must not be presented as identified people.

Analysis targets from the plan: observed task completion at least 90% (state the interval/sample), SUS at least 68 from the survey, and cold start under 1.5 s. Report crash **counts with user-day exposure**, rather than claiming a reliable 99.5% crash-free rate for a small cohort. Search empty-result proportion is false / all `search_completed`; sign-in success is success / all `sign_in_result`; application/review funnels use their started and acknowledged completion events. The defined Android events do not include extraction-completed, so exact extraction success requires the server aggregate; do not invent a new event or equate review openings with all successful extractions.

## Privacy controls

`TelemetryEvent` accepts only enums/Boolean/count/time buckets, with no arbitrary name, string or parameter map exposed to callers. `ApiEndpoint` accepts runtime paths only to resolve a fixed allowlist. Unknown paths/codes become `unknown`/`UNKNOWN`. `setScreen` accepts an enum; Crashlytics receives only the `screen_route` template custom key. No raw exceptions are recorded as nonfatal telemetry.

Both SDKs start disabled in the merged manifest. The Firebase initialization provider is removed, and Firebase initializes lazily only after consent and build permission. Analytics opt-out disables collection and resets local Analytics data; unsent crashes are deleted on opt-out. Classic AD_ID and SDK-added AdServices AD_ID/attribution permissions are removed; ad ID collection and ad personalization are disabled; automatic screen reporting is disabled. Existing server/search/map networking is separate from telemetry and is not redesigned here.

Crashlytics automatic uploading stays disabled persistently to avoid uploading before the next launch's consent check. A launch with stored consent explicitly sends previous consented-session reports. An in-process first opt-in deletes old pending reports; it does not backfill an off period. A crash is therefore expected after reopening with consent still on. Opt-out does not recall reports already sent or an upload already in flight. Crashlytics can retain crash information locally while its handler is installed, so a later opt-in discards off-period reports. Fatal exception stack/message contents are SDK-managed, not scrubbed by the typed custom-event boundary; review an actual report and keep PII out of thrown/logged exception text. Do not assert that arbitrary crash payloads are PII-free solely from these event tests.

Official implementation references: [Firebase setup](https://firebase.google.com/docs/android/setup), [Analytics collection controls](https://firebase.google.com/docs/analytics/android/configure-data-collection), [Crashlytics opt-in reporting](https://firebase.google.com/docs/crashlytics/android/customize-crash-reports), [AGP built-in Kotlin source configuration](https://developer.android.com/build/migrate-to-built-in-kotlin).

## Galaxy S23 and Firebase Console verification

Work continues on `feature/i5-p17-p35-firebase-telemetry` in a Draft PR, as requested by the user. Use the standard sequence below after the branch has been pushed. Preserve local changes and app data; do not discard drafts or clear app data. The user requested that comprehensive CI/test review be deferred until before merge.

```powershell
git fetch origin
git switch feature/i5-p17-p35-firebase-telemetry
git pull --ff-only
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/" "-PBOTTLEMAP_RELEASE_CHANNEL=dev" "-PBOTTLEMAP_TELEMETRY_DEBUG_ENABLED=true"
```

1. Confirm `adb devices -l` shows the Galaxy S23 as `device`. Keep existing app data/drafts/login. Add platform-tools to PATH locally if needed.
2. In Firebase Console, select the project matching the **local file**, verify the Android package `com.zerotoone.bottlemap`, Analytics and Crashlytics. Team access is already reported complete. Link Analytics if not yet linked. In Analytics Admin, set event-data retention to **2 months** and register `release_channel` as a user-scoped custom dimension for reports. Keep advertising integrations/personalization off. Enable Crashlytics new-issue email alerts for the team. These Console settings are manual, not code verification.
3. Enable DebugView routing:

```powershell
adb shell setprop debug.firebase.analytics.app com.zerotoone.bottlemap
```

4. With usage consent off, use the app: no custom events should arrive. Turn on the existing ‘사용 기록 보내기’ choice. Background/reopen the app, select this device in Analytics DebugView, and perform each nonblocked event scenario below. Inspect every parameter and the `release_channel=dev` property; save sanitized screenshots and timestamps. Record empty search and failure cases separately. Use a development server/fixtures to produce extraction/publish failures; do not damage production state or use real applicants for test failures.
5. Visit a known detail screen, then force exactly one test crash, without an attached debugger:

```powershell
adb shell am broadcast -n com.zerotoone.bottlemap/.telemetry.DebugCrashReceiver -a com.zerotoone.bottlemap.DEBUG_TELEMETRY_CRASH
```

The debug-only receiver requires the shell's system `DUMP` permission, Firebase-enabled verification build and consent. It has no release entry point. Reopen the app **with consent still on**, then inspect Crashlytics for the fixed ‘BottleMap telemetry verification crash’, correct version/device and `screen_route`. Confirm only the intended custom key/breadcrumb parameters are present. Console delivery, ANR reporting and server-side processing are not established by local unit tests.
6. Disable usage records, navigate/search again, restart, and check that new events/reports stop. Already-sent or in-flight records may still appear. Re-enable and verify only new events; no replay of disabled-period application events. Test a fresh install separately on a spare/test device if first-open evidence is needed; do not clear the S23's stored drafts.
7. Disable DebugView afterwards:

```powershell
adb shell setprop debug.firebase.analytics.app .none.
```

Rebuild ordinary debug without the verification flag to verify default-off behavior, even if the saved optional choice is on. DebugView events are validation evidence, not the Alpha/Beta reporting dataset. A distribution build must use the correct release channel and optional consent; validate the ONE store build separately.

Copy/paste checklist (Markdown fallback; each status can be edited before sending back):

```text
Galaxy S23 / Firebase verification — branch feature/i5-p17-p35-firebase-telemetry
[ ] Existing customer search, map, detail, login and owner drafts still work.
[ ] No telemetry before optional consent; ordinary debug remains off even with stored consent.
[ ] search_completed: product / brand / bar_name and empty-results case; no query or coordinates.
[ ] bar_detail_opened: search / nearby / map / popular; only search has an available time bucket.
[ ] menu_import_started: camera / gallery, photo-count bucket; mixed source interpretation checked.
[ ] menu_import_failed: upload and terminal extraction; polling does not duplicate the terminal event.
[ ] menu_review_opened and menu_published: reload/duplicate tap does not duplicate, initial needed_check retained.
[ ] menu_publish_failed: code only; retry/status recovery does not report success before acknowledgement.
[ ] owner_application_started/submitted/failed: claim and new, no business/contact/form fields.
[ ] nearby_opened and sign_in_result: granted/denied, welcome/account success/cancel/error.
[ ] api_error: fixed endpoint, status, code only; no UUID, query, body or server prose.
[ ] Crash test visible after reopening; version/device/screen template correct; actual SDK payload reviewed.
[ ] Opt-out survives restart, blocks new custom events/reports and does not replay the off period on re-enable.
[ ] release_channel=dev confirmed; retention=2 months and alerts configured; privacy disclosure confirmed with Haeul.
[ ] Firebase-configured Alpha/ONE store build checked separately; upgraded install retains consent/drafts.
[ ] Cold start recorded separately (commands below); target <1.5 s, no Firebase Performance SDK.
[ ] P20/P25 report form and PDF source marked pending rather than claimed tested.
Screenshots / timestamps / failures / notes:
```

Cold-start measurement (repeat several times, record `TotalTime` in milliseconds with build/device details; force-stop preserves app data):

```powershell
adb shell am force-stop com.zerotoone.bottlemap
adb shell am start -W -n com.zerotoone.bottlemap/.MainActivity
```

## Validation results and remaining work

Executed locally:

- Firebase default Debug: `:app:assembleDebug :app:testDebugUnitTest :app:lintDebug --max-workers=2 --continue` passed; 756 JVM tests, zero failures/errors/skips. The JVM inventory/skip policy passed.
- Final Firebase verification Debug: `:app:testDebugUnitTest --tests "com.zerotoone.bottlemap.telemetry.*" --tests "com.zerotoone.bottlemap.ui.auth.UserPrivacySettingsTest" :app:assembleDebug :app:processReleaseMainManifest -PBOTTLEMAP_TELEMETRY_DEBUG_ENABLED=true -PBOTTLEMAP_RELEASE_CHANNEL=dev` passed. This follow-up includes the final ad-services permission removal and endpoint-specificity regression.
- Firebase Alpha Release: `:app:compileReleaseKotlin :app:checkReleaseDuplicateClasses -x :app:validateReleaseSigning -PBOTTLEMAP_RELEASE_CHANNEL=alpha -PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/` passed. This verifies compilation/dependencies, not signing or store installation.
- Python Android CI helper tests: 19 passed. Android workflow YAML parsed; `git diff --check` passed. One unified SDK-configured Debug APK was inspected for Analytics, Crashlytics, the debug crash hook and both customer/owner code.
- No-SDK build/test/lint passed at ad261897 (759 tests, zero failures/errors/skips; recorded in PR #216). Latest-head full GitHub CI/human review remains a merge gate, per the user's instruction. No new broad verification run was needed for the focused SDK-order fix or final device diagnosis.

GitHub CI status must be checked on the pushed PR; local results do not establish CI success. Device QA is now PASS by user report, including the final release_channel=dev Console check. The agent independently inspected current-device SDK upload evidence, as recorded below; this is distinct from Console observation. No signed release/ONE store upload is claimed. P17/P35 remain Started pending the separate review and final PR disposition gates. Human review must cover Privacy, Auth/permissions (debug shell hook and sign-in/consent instrumentation), and Android CI. No backend, AI, owner web, API or schema is changed.

## 2026-11-26 Galaxy S23 QA follow-up: release_channel

The initial user report was a conditional pass on a Firebase-enabled Debug/dev build: customer/auth/owner/import/review events, consent controls, existing flows and Crashlytics passed. Cold start was 1,110 ms in one recorded COLD run (not a multi-run benchmark). The supplied screenshots independently show bar_detail_opened / owner_application_started delivery and a correctly registered user-scoped Release Channel dimension mapped to release_channel. They do not show release_channel among the selected event's user properties. Detailed events and Crashlytics remain user-reported evidence, rather than independently reviewed Console screenshots for every item.

**Root cause and fix:** FirebaseTelemetry previously assigned release_channel before enabling Analytics collection. This app deliberately defaults collection to false and disables/resets it on opt-out. The resolved Google measurement SDK (24.0.0) explicitly drops user-property writes in that state (its diagnostic is `User property not set since app measurement is disabled`). Consent is now applied first, then collection is enabled, then the build's release_channel is assigned. The shared SDK-call sequence has regressions using a fake that rejects disabled-state property writes, covering first opt-in, reset/re-enable and startup/channel replacement. Advertising remains denied and the existing consent/build gate is unchanged.

Local focused validation: `:app:testDebugUnitTest --tests "com.zerotoone.bottlemap.telemetry.AnalyticsCollectionTest" --tests "com.zerotoone.bottlemap.telemetry.TelemetryTest" -PBOTTLEMAP_TELEMETRY_DEBUG_ENABLED=true -PBOTTLEMAP_RELEASE_CHANNEL=dev` passed: 10 tests, zero failures/errors/skips. This compiles the Firebase-enabled Debug code and checks the regression; it does not establish delivery to the S23 Console session. Full CI review remains a merge gate.

This is not a requirement to install a Release build: the Gradle channel and build type are independent, and dev is intentional for a team verification Debug APK. Keep the existing Console dimension; do not rename it or change its user scope. Custom-dimension registration enables reporting of a property; it does not assign the value on the device. DebugView is for live SDK validation. The reported `.none.` device setting separately disables DebugView routing; it does not explain away the SDK call-order defect or clear a previously stored user property.

[Firebase DebugView documentation](https://firebase.google.com/docs/analytics/debugview) and [Android user properties](https://firebase.google.com/docs/analytics/android/user-properties).

After fetching the fix, use the existing branch and preserve app data:

```powershell
git fetch origin
git switch feature/i5-p17-p35-firebase-telemetry
git pull --ff-only
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/" "-PBOTTLEMAP_RELEASE_CHANNEL=dev" "-PBOTTLEMAP_TELEMETRY_DEBUG_ENABLED=true"

adb shell setprop debug.firebase.analytics.app com.zerotoone.bottlemap
adb shell getprop debug.firebase.analytics.app
adb shell am force-stop com.zerotoone.bottlemap
adb shell am start -n com.zerotoone.bottlemap/.MainActivity
```

The getprop output must be com.zerotoone.bottlemap, not .none. With usage records enabled, create a new search/detail event. In DebugView select the S23 and inspect that **new** event's User properties tab and Current User Properties panel for release_channel = dev. Do not inspect a historical event from before the fix. Then turn usage records off/on, create another new event, and confirm dev again. Reopen with consent still on and confirm it remains dev. No app-data reset, new dimension, forced crash or repeat of the full QA suite is required for this focused retest.

```text
Galaxy S23 — release_channel focused retest
[ ] DebugView getprop is com.zerotoone.bottlemap.
[ ] New event after launch with usage consent enabled contains release_channel = dev.
[ ] New event after opt-out/reset and opt-in again contains release_channel = dev.
[ ] New event after app restart still contains release_channel = dev.
Notes / new-event timestamp:
```

When finished, disable DebugView routing with `adb shell setprop debug.firebase.analytics.app .none.`. The user subsequently confirmed release_channel=dev in Firebase Console; the device QA is now PASS (see final verification below). CI/human-review and ONE store distribution verification are separate gates; schedule completion/time fields are not changed by this report.

## 2026-11-26 final device diagnosis and QA acceptance

**Device QA result: PASS, user-confirmed.** The tester explicitly confirmed both Firebase Console event output and release_channel=dev after the earlier conditional report. The original customer/auth/owner/import/review/consent/regression and Crashlytics checks remain PASS by user report. The 1,110 ms cold start is still a single recorded run, not a statistical performance claim.

Before that final Console confirmation, the agent inspected the currently USB-connected device without clearing application data, reinstalling, or changing collection consent:

- Installed APK matched the local Debug APK; real Firebase Analytics/FirebaseTelemetry code was present. The Firebase app resource matched the ignored local configuration. No project API keys or app-instance values were printed or committed.
- DebugView routing targeted the application package, stored optional consent was true, SDK measurement was enabled, and the installed manifest's permanent deactivation flag was false. Device and host clocks agreed.
- The app was initially stopped. After the user opened it and generated search/detail activity, SDK initialization, fast Debug mode and the remote measurement-service connection were observed.
- Fresh upload bundles attributed to this app contained search_completed / bar_detail_opened, the exact release_channel=dev property, debug flag _dbg=1 and an app-instance field. Matching upload requests received HTTP 204. Raw payloads and identifiers were not saved or published. HTTP 204 establishes transport acceptance, not by itself visibility in DebugView; the subsequent Console confirmation is the user's evidence for that final step.
- No additional code change was justified after these transport checks. Console visibility was confirmed while the app remained open. Rebuilding or recreating Analytics definitions was not needed for that confirmation.
- FA / FA-SVC verbosity was enabled temporarily for diagnosis, then restored to its previous values. The user's original DebugView routing and collection choice were preserved.

Final recorded checklist:

```text
2026-11-26 Firebase device QA
[x] Previously reported customer/auth/owner/import/review/consent/regression checks — user report.
[x] Crashlytics test crash — user report.
[x] release_channel=dev displayed in Firebase Console — explicit final user confirmation.
[x] Fresh search/detail payloads include dev and _dbg=1; matched HTTP 204 uploads — agent runtime inspection.
[x] Debug/consent/deactivation/configuration and clock checks — agent runtime inspection.
[x] Temporary SDK diagnostic logging restored.
[ ] Latest-head CI/human-review/final PR disposition — separate merge gate, not rerun here.
[ ] ONE store distribution-build verification — separate release gate.
```

No merge, schedule completion, or work-time/completion-date update was performed as part of this QA acceptance.

## Changed-file purpose map

| File | Purpose |
|---|---|
| `.github/workflows/android-ci.yml` | Optionally inject the Firebase secret for APK jobs; explicitly run lint/JVM CI without SDKs. |
| `android/.gitignore` | Exclude injected Firebase JSON and the local verification log. |
| `android/FIREBASE_TELEMETRY.md` | Record requirement coverage, implementation boundaries, validation and manual QA. |
| `android/app/build.gradle.kts` | Select Firebase/no-SDK sources, plugins and SDKs; validate channel; gate debug collection. |
| `android/app/src/debug/AndroidManifest.xml` | Register the debug-only, shell-permission-protected crash receiver. |
| `android/app/src/debug/java/com/zerotoone/bottlemap/telemetry/DebugCrashReceiver.kt` | Provide an explicit, protected test crash only in a consented verification Debug build. |
| `android/app/src/firebase/java/com/zerotoone/bottlemap/telemetry/PlatformTelemetry.kt` | Lazy real Analytics/Crashlytics implementation with opt-in upload control. |
| `android/app/src/main/AndroidManifest.xml` | Disable initial collection, advertising identifiers/signals and automatic screens; remove early Firebase provider. |
| `android/app/src/main/java/com/zerotoone/bottlemap/BottleMapApplication.kt` | Install the selected telemetry implementation using persisted consent. |
| `android/app/src/main/java/com/zerotoone/bottlemap/data/owner/LiveOwnerScreenRepository.kt` | Retain the terminal extraction failure code as a typed local value. |
| `android/app/src/main/java/com/zerotoone/bottlemap/data/owner/OwnerMockModels.kt` | Carry typed local photo provenance and allowlisted extraction failure code; no DTO change. |
| `android/app/src/main/java/com/zerotoone/bottlemap/navigation/BottleMapNavHost.kt` | Supply sanitized screen templates and sign-in origin without changing navigation. |
| `android/app/src/main/java/com/zerotoone/bottlemap/network/ApiClient.kt` | Emit sanitized HTTP/I/O errors once at the API boundary; preserve cancellation. |
| `android/app/src/main/java/com/zerotoone/bottlemap/telemetry/ApiEndpoint.kt` | Resolve runtime paths to an allowlist of contract templates with {id} placeholders. |
| `android/app/src/main/java/com/zerotoone/bottlemap/telemetry/ConsentTelemetry.kt` | Gate custom events/screens with both consent and build policy. |
| `android/app/src/main/java/com/zerotoone/bottlemap/telemetry/Telemetry.kt` | Define the event interface, sealed enum-only events, buckets, codes, routes and ephemeral timing. |
| `android/app/src/main/java/com/zerotoone/bottlemap/telemetry/TelemetryPayload.kt` | Map the closed event model to the specified Firebase event names/parameters. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/auth/AuthViewModel.kt` | Measure explicit sign-in success/cancel/error without counting restored sessions. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/auth/GoogleSignInButton.kt` | Pass welcome/account context into the existing sign-in ViewModel attempt. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/auth/UserPrivacySettings.kt` | Persist and immediately apply the existing optional collection choice. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/customer/BarDetailViewModel.kt` | Count only the first acknowledged current-bar detail per destination. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/customer/CustomerP18Explore.kt` | Measure discovery permission and selected detail source through its ViewModel. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/customer/CustomerP18Results.kt` | Measure logical searches and monotonic search-to-detail time; deduplicate refinements. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/customer/MapPlaceSearchViewModel.kt` | Measure registered-bar-name search completion, excluding generic place matches. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/customer/SearchResultsViewModel.kt` | Keep telemetry consistent for the legacy search ViewModel. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/owner/OwnerMenuPhotoStage7Screen.kt` | Preserve typed provenance in saved picker entries with backward-compatible reading. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/owner/OwnerMenuPhotoStore.kt` | Record camera/gallery provenance while making the existing private copy. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/owner/OwnerMockViewModel.kt` | Measure application and import/upload/extraction state transitions. |
| `android/app/src/main/java/com/zerotoone/bottlemap/ui/owner/review/PhotoReviewViewModel.kt` | Measure review start, initial pending bucket, failures and confirmed publication once. |
| `android/app/src/noFirebase/java/com/zerotoone/bottlemap/telemetry/PlatformTelemetry.kt` | Compile a no-SDK NoOp factory when configuration is absent/disabled. |
| `android/app/src/test/java/com/zerotoone/bottlemap/telemetry/ApiErrorTelemetryTest.kt` | Verify HTTP/I/O failures preserve client behavior and exclude private data/cancellation. |
| `android/app/src/test/java/com/zerotoone/bottlemap/telemetry/FakeTelemetry.kt` | Capture event, screen and enabled calls for tests without external SDK traffic. |
| `android/app/src/test/java/com/zerotoone/bottlemap/telemetry/OwnerTelemetryTest.kt` | Verify application, upload and publication outcomes, status recovery and autosave boundaries. |
| `android/app/src/test/java/com/zerotoone/bottlemap/telemetry/TelemetryManifestTest.kt` | Verify merged manifest collection/advertising/provider restrictions. |
| `android/app/src/test/java/com/zerotoone/bottlemap/telemetry/TelemetryTest.kt` | Verify consent/build gates, sanitized templates, payloads and timing/count boundaries. |
| `android/app/src/test/java/com/zerotoone/bottlemap/telemetry/TelemetryViewModelTest.kt` | Verify search deduplication, stale/error results, bar-name matches and discovery permissions. |
| `android/app/src/test/java/com/zerotoone/bottlemap/ui/auth/AuthViewModelTest.kt` | Add explicit-attempt telemetry assertions using the existing fake auth gateway. |
| `android/app/src/test/java/com/zerotoone/bottlemap/ui/auth/UserPrivacySettingsTest.kt` | Verify persisted opt-in/out reaches one gate; isolate per-test Robolectric applications. |
| `android/app/src/test/java/com/zerotoone/bottlemap/ui/customer/BarDetailViewModelTest.kt` | Verify failed/retried/repeated detail loading does not inflate successful opens. |
| `android/ci/prepare_firebase.py` | Validate and materialize optional injected configuration without logging sensitive values. |
| `android/ci/test_prepare_firebase.py` | Test absent/valid/invalid/wrong-package config handling and safe failure text. |
| `android/app/src/main/java/com/zerotoone/bottlemap/telemetry/AnalyticsCollection.kt` | Order consent, collection activation and channel assignment so SDK writes are retained. |
| `android/app/src/test/java/com/zerotoone/bottlemap/telemetry/AnalyticsCollectionTest.kt` | Reproduce disabled-property rejection and guard first opt-in, reset/re-enable and channel replacement. |
