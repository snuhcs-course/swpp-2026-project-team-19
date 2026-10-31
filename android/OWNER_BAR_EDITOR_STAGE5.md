# I3 Owner Flow Stage 5 — editable bar information (Android Mock)

## ACTION_FIRST_v4 source reconciliation (2026-11-01)

- **Exact source inspected**: Google Drive `BottleMap_owner_flow_ACTION_FIRST_v4.html`, original Drive file ID `1rJh9r2Lkt8AHKHCQTBhMnTjd3dgitszj` (HTML, 360,007 bytes per Drive metadata; read using Drive connector). Management UI is the embedded `MANAGER_DOCUMENT`, not the outer registration sample.
- This **supersedes** the previous "HTML unavailable" note below, which describes the first PR draft only.
- **Single-screen info form** (`OwnerInfoHtmlV4Screen.kt`): basic fields, inline seven-day regular schedule, inline tag search and selection; one Save applies the draft atomically via existing `saveBar()`. Back (toolbar and system) discards the uncommitted form without a dialog. Tag suggestions include the nine HTML demo tags and saved Mock bar tags. The HTML specifies a 100-character intro, 3-digit pour entry, a Mon-to-Tue–Fri copy action, and separate 5-minute wheel selection for opening/closing with an explicit "익일" checkbox.
- **Separate 2-column photo editor** (`OwnerPhotoHtmlV4Screen.kt`): gallery-add button in header, tap photo -> contextual cover/remove menu, centered delete confirmation, left/right arrows only for non-cover slots, and Done button. Each action **commits immediately**, no separate photo Save. The last image cannot be removed (HTML's `confirmRemoveStorePhoto` behavior); a new/empty mock bar can still display 0 photos. No drag arrangement and no gallery-last add tile.
- Stored photo refs are the original picked URI. Editor thumbnails use `ContentScale.Fit` inside clipped tiles (HTML's `object-fit:contain`); home thumbnails crop; customer full-screen image also fits without cropping.
- **Status/overnight**: corrected owner status projection so today's overnight opening does not falsely mark the bar open this morning if yesterday's shift was closed. Temporary exceptions remain distinct from regular schedule, with expiry calculated against Asia/Seoul time.
- **Intentional divergence**: HTML's mock photo picker simply appends an example label, but Android uses actual `PickVisualMedia()` + persisted content URI where possible. The HTML's unimplemented map mock is represented by an explanatory placeholder; no geocoding API invented.
- **Unresolved contract**: production customer detail remains API-backed, not synchronized with local Mock. Tag catalog is Mock-only (no server vocabulary). No production schema changes.
- **Verification**: unit tests cover v4 cover-protected arrows, Mon-to-weekday copy, intro capacity and pour bounds, overnight time shift/temporary expiry. Compose UI tests updated for immediate photo Done and silent discard-on-back. Review actual emulator/Galaxy S23 results in GitHub Actions before merge.


## Scope and source

- Work branch: `feature/i3-p42-owner-bar-info-editor`; Schedule item **I3 P42** (`Started`).
- User-requested Stage 5 spans basic bar information, gallery, tags, weekly hours and temporary exceptions. Only description editing/customer detail is explicitly mapped to P42; the extras are acknowledged in the PR rather than hidden as completed Schedule tasks.
- Final referenced UI: `BottleMap_owner_flow_ACTION_FIRST_v4.html`. The actual HTML file was **not accessible** in the current Project, Google Drive search, or repository at implementation time. Existing ACTION_FIRST v4 stage 4 Compose components and user-provided screenshots were followed. Exact CSS/pixel fidelity is **not independently verified**.

## Design/implementation decisions

1. **Edit vs commit**: Basic fields, gallery order, tag selection and weekday schedule each hold a Compose screen draft. `BackHandler` and toolbar Back show a discard prompt when dirty. Only Save calls the previously shared `OwnerMockViewModel.saveBar()`, which delegates to the atomic `LocalOwnerMockRepository.saveBar()` and its Android SharedPreferences persistence.
2. **Independent nested edits**: Each editor submits only its owned fields via a fresh `bar.copy(...)`. For example, editing basic fields does not overwrite gallery/tags/hours saved by a child editor. Process restarts load the persisted snapshot; no unsaved-draft persistence is promised across force-stop.
3. **Photo identity**: Gallery is `MockBar.gallery`, where **first = cover** and the URI is the original photo source. Photo editor uses horizontally scrollable cards, arrows, tap-to-open cover/delete context menu, confirmation dialog for deletion; no drag reordering, no add button as the final carousel item. The picker requests persistable URI read permission when the provider supports it; the local Mock is not remote storage and URIs may become inaccessible if the provider revokes them.
4. **Tags**: Existing tag suggestions come from selected/other persisted mock bars. Selecting/creating/removing tags mutates only the current bar at Save; five-tag cap; draft-only 24-character recommendation. There is no cross-device tag catalog, AI tag recommendation, or server tag policy.
5. **Weekly hours**: `null`/absent weekday = not configured; `closed` = regular holiday; otherwise both 5-minute opening and closing times are required, with `closesNextDay` when end time is earlier than start. Multiple selected weekdays can copy a chosen day's setting. Existing quick exceptions remain distinct and are edited in stage 4 `OwnerOperatingQuickScreen` with optional customer note, date range, and auto expiry by epoch-day projection.
6. **Customer Mock preview**: `OwnerBarCustomerPreviewScreen` reads the **same selected `MockBar`** and menu preview from `OwnerMockViewModel.preview()`. The latest gallery first photo is used first; tapping an image opens it from its original URI. The real Customer bar detail is **API-backed and will not reflect local-only mock changes**; do not claim production synchronization.
7. **Validation and failure**: `OwnerBarEditRules.kt` validates basic fields, tag count/length, gallery reordering and overnight weekly hours. A failed SharedPreferences write throws without emitting an unpersisted snapshot. The editor displays the error and retains its draft.

## Contract gaps (Backend/PM decisions required; NOT new API fields)

- A/C/D/E: authoritative update/request/response contracts for bar description, phone, default pour, tag vocabulary/free-form creation/deletion, weekly hours and exception schedule/cancel; ownership, validation and concurrency policy.
- B: file upload/storage reference, image byte lifetime/visibility, cover and order semantics, delete audit and maximum gallery count.
- Public customer detail: how owner edits propagate to the public API and how the public menu, opening/closing status and image URLs are exposed.
- Authoritative server time, time zone, overlap priority and expiry for regular vs temporary hours.
- A save-failure simulator is currently exercised by a throwing `MockOwnerStateStore` in JVM tests; there is no new user-facing debug flag or production failure endpoint.

## Test scope / Definition of Done

- JVM: `OwnerBarEditRulesTest` (basic validation, 0-photo boundary, cover/order, tags max five, unset/closed/regular/overnight, invalid minute), `OwnerMockViewModelTest` (saved fields and preview survive repository recreation, failed save is atomic), existing owner/customer regressions.
- Android Compose UI test *source* under `androidTest` (explicit Save, discard prompt, photo editor smoke). `connectedDebugAndroidTest` requires a connected device/emulator and is **not part of default GitHub Android CI**, so do not claim it passed without running it.
- Android CI: Debug APK / JVM unit tests / Android Lint; AI CI as a regression check.
- Galaxy S23 user QA required for photo picker URI persistence, gallery ordering/cover, tags, basic data edits, 5-minute wheels, overnight, system Back, small portrait and enlarged font. Do not clear existing app data before persistence tests.

## Risks

- Pixel-level match with unavailable HTML is unverified.
- Real Customer detail is not linked to the Mock Repository because it is bound to public APIs, which must be agreed with Backend.
- SharedPreferences JSON reference storage is a demo-only local persistence mechanism, **not encrypted** and **not appropriate for real applicant PII**.
- Screens assume one selected bar from the existing owner state; no new authentication/permissions contract was invented.
