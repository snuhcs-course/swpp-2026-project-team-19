# I3-P8 / I3-P14 / I3-P39 — Owner registration Mock flow (stage 3)

## Source and scope

This implementation is on the single Customer+Owner APK and reuses `OwnerMockRepository`,
`OwnerMockSnapshot`, `OwnerPage`, shared Compose primitives and Cocoa Charcoal tokens.

**Source verified:** `BottleMap_owner_flow_ACTION_FIRST_v4.html` was attached
during the follow-up and inspected (registration `SCREENS`, `R.*` screens,
`ACT` event transitions, CSS tokens and per-screen API notes). Its registration
flow is authoritative over previous FINAL/v1–v3 drafts. This PR adjusts the
individual business-info screens, existing-bar recognition after name entry,
4-stage progress, pending/rejected application cards, readonly application detail,
menu-photo add/remove, and completion screen to match the v4 decisions.
The embedded manager / initial photo-review v10 flow remains for later stages;
pixel-perfect Galaxy S23 comparisons have **not** yet been run.

## UI steps implemented (local Mock only)

- Customer My Page -> Owner entry: 0 bars -> registration entry; 1 bar without pending
  claim or draft -> management home; multiple bars -> selectable list. From management,
  the Owner can start another application.
- The v4 registration flow chooses **photo Mock OCR vs manual entry** first,
  then business number -> representative -> opening date -> combined check ->
  Mock verification result -> bar name. At the bar-name step, equal-name candidates
  can be marked "우리 매장예요" (existing-bar claim), skipping photo/address/shop-phone.
  Candidates remain separate from owned bars and are Debug-fixture-only until search
  contract integration. New bars continue through photo -> address -> shop phone.
- Business-number check digit and date validation run locally; they are not
  business-identity/NTS verification. Four outcome screens (match, mismatch,
  unavailable, rate-limited) are Debug Mock scenarios, not API responses.
- The 4-stage progress indicator, one-question-per-screen layout, review details,
  completion state, and managed-store/application cards now follow v4.
  Pending cards provide view-only application details and a cancellation dialog.
  Rejected cards show a local Mock reason, reapply action and confirmed local-only
  dismissal. Local hidden IDs do not delete underlying applications.
- Pick a business certificate using the Android Photo Picker, retain its URI as
  `certificatePhoto`, and then manually enter/verify a business number, representative
  and opening date. A clearly labeled **Mock sample fill** is available. **No OCR** or
  public-data business validation occurs; it is not presented as real recognition.
- Enter business name/address, choose cover photo, enter public store phone, select
  ordered menu photos (up to 15), enter private contact phone independently, review and
  submit to the local Mock repository.
- Shop-phone screen has `손님에게 보여요` and `가게 전화가 없어요`, private-contact
  screen has `운영팀만 봐요` and `매장 번호와 같아요`.
  Both are **system Phone keyboard** fields; no embedded numeric pad.
  Mobile, area-code and 0507 prefixes are accepted by local mock range check; no
  mobile-only prefix constraint.
- Pending, canceled, rejected and approved Mock states. For Debug testing only,
  clearly labeled operator Fixture buttons can approve/reject locally. This is not
  operator authorization or Backend approval.
- Approval creates or links the bar, then connects **the exact selected ordered
  MENU_CAPTURE references** to `MockMenuImport` through an empty per-URI fixture.
  No extraction lines are invented. Imported photos are visible on the first-review
  placeholder screen, where actual AI correction/publication is explicitly unimplemented.
- A bar is never published from approval alone. `menuItems` remains empty, so its
  display state is `메뉴 확인 필요`. The local Owner home derives `정상 영업` only
  from existing published menu entries. **This is not Backend active/inactive.**

## State and lifecycle

`MockRegistrationDraft` is saved through the existing `AndroidOwnerMockStateStore`.
The draft keeps certificate URI, cover/gallery references, selected menu URIs and order,
public store phone and private contact phone independently. The current form step uses
`rememberSaveable` across Activity recreation. The existing app-private snapshot store
restores data across process restarts. A picker URI may become unreadable if the platform
does not provide persistable access; the thumbnail shows a fallback rather than inventing
an image. Never use real personal/business data with unencrypted Mock preferences.

`submitRegistrationDraftForFixture` consumes and clears the draft atomically; a second
submit without a draft fails. Operator Fixture approval and cancellation are separate
from actual Owner actions and remain non-production.

## Follow-up contract gaps / not done

- Pixel-perfect v4 visual fidelity has not been verified on a Galaxy S23;
  visual tokens are reused from existing design system. HTML-embedded manager v10
  and subsequent AI-review designs are outside this registration-stage scope.
- Backend approval/rejection, operator review, initial photo uploads, public-data/OCR
  results, permission/ownership and real bar API calls are **not connected**.
- AI extraction, corrections, review decisions and publication are next-stage UI work.
  The first-review destination is a clearly labeled placeholder with preserved photo
  references. No menu becomes publicly available just by submitting or approving.
- My Page's Owner entry now follows the v4 guest rule: guests first open the
  existing Google sign-in flow; signed-in users enter Owner. This is UI routing,
  not Backend Owner authorization. Customer Guest search/map/login remain intact.
  The Mock Owner repository itself is not scoped by server identity (not a security boundary).
- Android Photo Picker supports album selection; the v4 "바로 찍기" camera sheet
  action is still out of scope (requires camera lifecycle/permission work).
  v4 address search is demo-only two canned examples; external postal search
  provider is unagreed and not integrated.
- Android Photo Picker is used instead of custom gallery/camera permission requests.
  Persisted URI permissions and process-death behavior require physical Galaxy S23 QA.

## Galaxy S23 post-test corrections: persisted registration progress and phone copy

- First real-device run reported that selected menu photo URIs/order were saved but
  after force-stop/reopen the UI jumped from \`MENUS\` to \`CONTACT\`, and header Back
  returned to My Page. Root cause: the old process-restart field heuristic mapped
  nonempty initial menu photos directly to CONTACT, without reconstructing the in-form
  Back history.
- The local-only \`MockRegistrationDraft.resumePageKey\` checkpoint now persists the
  *visible registration step* alongside existing fields, without any API field.
  Advancing, navigating back and editing review checkpoint stable screens. Fresh-process
  restoration uses the checkpoint, rebuilds form navigation history, and supports
  pre-migration drafts: photos present but no checkpoint resume at MENUS.
  Photo selections/removals preserve checkpoint and selected order.
- On contact screen, `매장 번호와 같아요` appears only when a shop phone exists.
  Valid shop numbers can be copied; an invalid nonempty number disables copying.
  After `가게 전화가 없어요`, the action is hidden while the private contact
  remains independently editable.
- JVM tests cover restart persisted checkpoint, legacy migration, new/claimed-bar
  Back predecessor, photo list mutation, and 02/0507 copy availability. Actual
  force-stop / Photo Picker / 320dp / IME behavior remains for Galaxy S23 rerun.
- No real applicant data should be entered in unencrypted local Mock state.

## PR #82 Codex review follow-up (2026-10-31)

- Editing the name after selecting an existing-bar candidate clears the old
  `EXISTING_BAR` selection and candidate ID if the chosen name changes.
- Pending new-bar duplicates follow API contract §3.11.2: compare the normalized
  business registration number, not the display name.
- Existing owners can return to the Owner dashboard at any registration step
  without clearing their saved add-bar draft. Returning to registration resumes
  the saved step rather than resetting the draft.
- New JVM regressions cover stale bar IDs, name changes, duplicate business
  numbers, same-name distinct businesses, and owned-bar draft persistence.
- Authentication/permission findings require a human review checkpoint:
  AccountScreen gates Owner entry on `SignedIn`, and AuthViewModel invalidates
  identity immediately on logout. The local Mock snapshot is not scoped to a
  particular Google account, does not grant backend permissions, and must not
  hold real applicant personal information. Review logout/account switching
  before treating the prototype as production owner authorization.

Galaxy S23 user verification passed all seven follow-up scenarios on the prior
QA-fix build. The small subsequent hide-copy-action change was explicitly exempted
from a separate device test. These Codex follow-up changes have not been
reverified on a physical device; CI and JVM verification are tracked separately.

## CI and manual verification

```powershell
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

Manual Galaxy S23 checklist:
- App launch still opens Customer search, no role selector; search/map/login unaffected.
- Guest taps the Owner CTA -> existing Google sign-in screen; signed-in user -> Owner.
- 0 stores: onboarding; 1 store: direct management; 2+ stores: correct list and selection.
- New/existing registration, Mock business info verification, input restoration via Back.
- Android Photo Picker: certificate, representative cover, ordered menu images;
  preview and restoration after Activity restart; Back/Cancel.
- `가게 전화가 없어요`, `매장 번호와 같아요`, 02/031/0507/010 input,
  keyboard focus/IME scrolling and Next button, 320dp width and large fonts.
- Repeated submit cannot produce multiple pending applications.
- Pending -> Mock reject/cancel/approve; menu not public before approval;
  after approval `메뉴 확인 필요` -> first review with ordered photos and no AI claims.
- Portrait-only, system bars and gesture back.

**Do not treat CI as physical-device verification.**
