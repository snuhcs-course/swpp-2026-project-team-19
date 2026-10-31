# Owner management home — ACTION_FIRST v4 quick actions

## Scope

- Based on `BottleMap_owner_flow_ACTION_FIRST_v4.html` (`home()` /`status()` / menu quick entry), following merged registration PR #82.
- Android only. Shared `OwnerMockRepository` and `MockBar` persist state. No production Backend API fields, endpoints, or permission rules changed.
- Home header: selected bar name, small **미리보기** action (home only).
- Equal-height management information / operating status tiles with BottleMap icons, text hierarchy, active/coming temporary schedule labels, multi-line vacation range, and schedule cancellation.
- Menu quick card: published count, distinct publish and owner-confirmation dates, 45-day age gauge from latest publication or owner confirmation, persistent **지금도 맞아요** action.
- Existing import state is read from the selected bar's `MockMenuImport`: `PROCESSING` (disable new upload), `READY_FOR_REVIEW` (resume review entry), `FAILED` (inspect/retry destination), `APPLIED` (published). The job action opens existing skeleton routes, which **remain placeholders**, not implemented AI pipelines.
- Status screen provides today closed, changed opening/closing time (including next-day closing), and temporary vacation date range with calendar selection, optional customer note, and explicit apply. Cancelling an exception removes that ID from the shared repository.
- All screen state comes from ViewModel StateFlow, surviving Activity restart and reopening from existing persisted Mock state. The form's unsubmitted picker choices use rememberSaveable.

## Data and invariants

- `lastMenuPublishedAtEpochMs` is a **local Mock domain field** updated only by `publishAddOnly()` when a pending import becomes `APPLIED`. It is distinct from `lastVerifiedAtEpochMs`, which is updated only when the owner taps `지금도 맞아요`. Neither should overwrite the other.
- `MockOperatingException` already represented today closed, custom hours and vacation. The optional `closesNextDay` field supports quick overnight exceptions. Overlapping quick exceptions are replaced by the new applied exception; unrelated future exceptions are kept.
- Date logic is explicitly Asia/Seoul, including midnight and overnight edges. No server authority is inferred from this local mock.
- Preview entry is present only on the management home header. Manager info/menu detail/edit remain next-iteration placeholders.

## Automated validation

- JUnit tests: quick menu verification persistence, publish vs verified independence, today/custom/vacation exception apply/cancel/reload, KST business state, overnight boundary, freshness, active import precedence and four statuses.
- GitHub Actions: Android Debug APK, unit tests and lint; AI CI (results to be recorded in PR).
- No local Android emulator or USB device verification is claimed by the automation.

## Galaxy S23 manual QA — user reported 7/7 PASS; detailed visual polish remains pending

Install without resetting app data:

```powershell
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

1. Approved new and existing Mock bars show the same management home; selected bar name, top-only preview action, two equal-height cards and menu card.
2. At 320dp portrait and enlarged system fonts, the two tiles remain aligned and a 3-line vacation date range and cancel control do not overlap.
3. Apply today closed; reopen app and confirm today's status and cancellation. Cancel and verify the regular state is restored.
4. Apply custom hours, including next-day closing; reopen and verify the times and return navigation. Test invalid times do not silently apply.
5. Apply a future date range; reopen and verify start/end, pending label, and cancellation without changing unrelated schedules.
6. Tap **지금도 맞아요**; confirm menu freshness/verification date changes and survives force-stop; last published date must **not** change.
7. With Mock `PROCESSING`, `READY_FOR_REVIEW`, `FAILED` and `APPLIED` import states, confirm the correct status label and job continuation destination. Processing disables new image registration.
8. Navigate home → information placeholder, status, menu, preview and back; verify system Back/gesture and Customer search/map/login unaffected.

**Limitations**: manager info edit, manual menu edit, production calendar schedules/permissions, actual OCR/AI import and publish are out of scope. Do not enter real applicant PII in app-private unencrypted Mock state.
