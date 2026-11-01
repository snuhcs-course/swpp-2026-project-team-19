# Owner management home — ACTION_FIRST v4 quick actions

## Scope

- Based on `BottleMap_owner_flow_ACTION_FIRST_v4.html` (`home()` /`status()` / menu quick entry), following merged registration PR #82.
- Android only. Shared `OwnerMockRepository` and `MockBar` persist state. No production Backend API fields, endpoints, or permission rules changed.
- Home header: selected bar name, small **미리보기** action (home only).
- Equal-height management information / operating status tiles with BottleMap icons, text hierarchy, active/coming temporary schedule labels, multi-line vacation range, and schedule cancellation.
- Menu quick card: published count, distinct publish and owner-confirmation dates, **30-day age gauge** from the latest publication or owner confirmation, persistent **지금도 맞아요** action. The gauge fills left to right: day 0 = empty (0%), day 15 = half (50%), day 30 or later = full (100%).
- Existing import state is read from the selected bar's `MockMenuImport`: `PROCESSING` (disable new upload), `READY_FOR_REVIEW` (resume review entry), `FAILED` (inspect/retry destination), `APPLIED` (published). The job action opens existing skeleton routes, which **remain placeholders**, not implemented AI pipelines.
- Status screen provides today closed, changed opening/closing time (including next-day closing), and temporary vacation date range with calendar selection, optional customer note, and explicit apply. Cancelling an exception removes that ID from the shared repository.
- All screen state comes from ViewModel StateFlow, surviving Activity restart and reopening from existing persisted Mock state. The form's unsubmitted picker choices use rememberSaveable.

## Data and invariants

- `lastMenuPublishedAtEpochMs` is a **local Mock domain field** updated only by `publishAddOnly()` when a pending import becomes `APPLIED`. It is distinct from `lastVerifiedAtEpochMs`, which is updated only when the owner taps `지금도 맞아요`. Neither should overwrite the other. The 30-day age gauge uses the more recent of the two dates, counts elapsed calendar days in Asia/Seoul, and clamps at 100% from day 30 onward. It displays age, **not freshness**; confirmation resets the gauge to empty.
- `MockOperatingException` already represented today closed, custom hours and vacation. The optional `closesNextDay` field supports quick overnight exceptions. Overlapping quick exceptions are replaced by the new applied exception; unrelated future exceptions are kept.
- Date logic is explicitly Asia/Seoul, including midnight and overnight edges. No server authority is inferred from this local mock.
- Preview entry is present only on the management home header. Manager info/menu detail/edit remain next-iteration placeholders.

## Automated validation

- JUnit tests: quick menu verification persistence, publish vs verified independence, today/custom/vacation exception apply/cancel/reload, KST business state, overnight boundary, **30-day increasing age gauge** (0/15/30/45-day boundaries), active import precedence and four statuses.
- GitHub Actions: Android Debug APK, unit tests and lint; AI CI (results to be recorded in PR).
- No local Android emulator or USB device verification is claimed by the automation.

## Galaxy S23 device QA — reported PASS (2026-10-31)

The user reported the following **seven feature-level scenarios PASS** on the manager-home implementation. These are physical Galaxy S23 observations, not automated assertions:

- [x] Newly approved/existing bar management home shows the bar name, header preview, and two aligned cards.
- [x] Today closed and one-day custom hours survive leaving/reopening the screen and can be cancelled.
- [x] Temporary vacation date ranges appear without clipping.
- [x] The owner menu confirmation date persists on reopening and does not overwrite the menu publish date.
- [x] Menu job status and entry route agree.
- [x] System Back, small portrait and large fonts do not overlap the tested components.
- [x] Customer search, map and Google sign-in have no observed regressions.

**Historical QA note (2026-10-31, superseded):** This device session recorded a 45-day freshness interpretation (100% immediately after confirmation, decreasing to 0% at 45 days). That earlier interpretation is **not** the current requirement.

**Current approved gauge specification (subsequent user acceptance):** `ownerMenuFreshness()` is a **30-day age gauge**, filling **left to right**: just confirmed = **0%/empty**; 15 days elapsed = **50%**; 30 days elapsed or more = **100%/full**. The most recent of menu publication and `지금도 맞아요` confirmation determines age. Keep publication and confirmation timestamps distinct. This is the approved behavior already implemented and tested in `OwnerManagementHomeState.kt` and `OwnerManagementHomeStateTest.kt`. Exact text positions, sizing, spacing and pixel-level Galaxy S23 comparison to ACTION_FIRST v4 are **still unverified for this revision**. Do not conflate earlier 7/7 functionality PASS with visual acceptance.

### Standard device install sequence (repo root, Windows PowerShell)

```powershell
git fetch origin
git switch feature/i3-owner-management-home-quick-actions
git pull --ff-only
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

Do not clear application data or uninstall before testing saved data/draft restoration.

### Copy-and-return QA template for future revisions

Use a plain-text/Markdown block with the checks for **that revision**; the tester replaces `[ ]` with `[x]` or adds a FAIL note:

```text
[Owner manager-home device QA — revision SHA: __________]
Device: Galaxy S23 / small portrait or font scale: __________
[ ] Just confirmed menu shows an empty (0%) 30-day age gauge, with no reverse fill.
[ ] Age gauge grows from left to right: 15 days = 50%, 30 days or older = full (100%).
[ ] Text positions/sizes match ACTION_FIRST v4 layout.
[ ] Cards, 3-line vacation date and cancel button preserve spacing and alignment.
[ ] Screen exit/reentry and process restart retain confirmed/menu dates.
[ ] Customer search/map, system Back and Google sign-in unaffected.
Defects / screenshots: __________
```

**Limitations**: manager info edit, manual menu edit, production calendar schedules/permissions, actual OCR/AI import and publish are out of scope. Do not enter real applicant PII in app-private unencrypted Mock state.
