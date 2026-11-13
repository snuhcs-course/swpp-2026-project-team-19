# BottleMap Android — Iteration 4 Integration

The Gradle root is the **repository root** (`:app` maps to `android/app`). Android
owns Compose UI, state, Retrofit DTOs and integration tests only. Backend, AI,
DB, admin web and shared specifications are outside this scope.

The source of truth for API request/response fields is
`docs/frontend_backend_api_spec.md` (not a previous chat or mock fixture).
This branch follows the **merged** #153 specification and #164 Backend
implementation. No owner action is allowed to create a shared catalog brand,
product or alias.

## Build / install

Debug uses `http://10.0.2.2:8000/` when no URL is supplied. For the deployed
server, run from the **repository root**, on Windows:

```powershell
git fetch origin
git switch feature/i4-p14-p32-p33-android-integration
git pull --ff-only
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

Do not hardcode the server URL. For an emulator, use `10.0.2.2` only if a
compatible development Backend is already running. Production authentication
uses Google/Supabase; `/api/auth/temp-login` is development-only and disabled
on the deployed server.

## Menu contract (#164)

- **Direct add:** a confirmed canonical whisky sends `productId`; an unmatched
  whisky sends `kind: "whisky"`; cocktails/beer/other non-whisky menus send
  `kind: "other"`. Send exactly one; never `newProduct` from Owner. Unlinked
  items are bar-only and their fake UI IDs must never be sent as catalog IDs.
- **Edit:** the published API permits `displayName` and 1–3 `options`
  (full replacement). It does not permit changing `kind` or per-bar detailed
  categories. A category change is rejected visibly, not reported as saved.
  Photo-imported menu items with 4–10 options are **read-only** in the direct
  edit screen until the server offers a safe edit contract; do not truncate
  options or send an invalid 4–10-option PUT.
- **Photo review:** send exactly one decision per OCR line and per proposed
  change to `POST /api/menu-imports/{id}/review-and-apply`. Unmatched lines
  use `publish_without_product` and `kind`. Every published decision sends its
  entire **final** `options[]` (1–10 per server), retaining the original
  `extractedOptionId` where applicable and using null only for reviewer-added
  options. Do **not** send `optionDecisions`, `addedOptions`,
  `excludedOptionIds`, or Owner `create_product`. Photo review can edit all
  1–10 whisky and non-whisky price options. Since merged Backend #164
  keeps only the first proposal when multiple OCR lines select one canonical
  whisky, **any duplicate linked whisky lines block Publish**, even if their
  prices agree. The owner must manually copy unique serving prices into the
  retained card and explicitly exclude the redundant OCR line; inconsistent
  serving prices are also highlighted. This is a safe Android-only workaround
  until Backend A4 supplies an agreed atomic merge contract.
- **Read:** `GET /api/bars/{barId}/menu` can return `productId: null`,
  `category: null`, `kind: "whisky" | "other"`. Show these items in Owner
  and Customer bar menus without inventing catalog identity. Unlinked whiskies
  are absent from product search until an operator links them.
- **Failure:** HTTP 422 on `kind: EXTRA_FORBIDDEN` identifies an outdated
  deployed API; never silently retry by omitting `kind`. HTTP 409
  `MENU_OUTDATED` / `REVIEW_OUTDATED` must preserve drafts and prompt
  refresh/review. Do not announce success until the server commits.

## Bottle display and debug-only fixture boundary

- Android considers the OCR labels `병` and `Bottle` one bottle serving,
  and displays **Bottle** even for a legacy row whose saved bottle has
  `pourMl`. New reviewed bottle options submit `optionLabel: "Bottle"`,
  retaining the original `extractedOptionId`.
- A same-size glass `잔 30ml` **is the same serving** as `샷 30ml`.
  Only `pourMl` distinguishes non-bottle options: prices for the same ml
  must be reconciled before publishing. Bottle is one separate serving.
  Newly reviewed sized glasses send `optionLabel=null` with the actual
  `pourMl` so the existing server receives a stable representation.
- The merged Backend #164 persists literal option labels. Android does not
  retroactively rename existing database rows or claim a server migration.
- v18 OCR mock scenarios, preview-only repositories, demo shared preferences,
  and fixture builders now live in `android/app/src/debug`. No release Owner
  route can substitute mock OCR data.
- Some `MockOwner*` model/interface names and `LocalOwnerMockRepository`
  still act as an in-memory state adapter behind `LiveOwnerScreenRepository`.
  They **are not a mock Backend implementation in the production navigation**.
  Removing the shared state model requires a separate incremental migration,
  not deleting files before live device QA.
- See `android/QA_PR168.md` for Galaxy S23 cases and synthetic A/B/C photo
  data supplied with this work.

## CI / verification

From the repository root:

```powershell
.\gradlew.bat :app:testDebugUnitTest
.\gradlew.bat :app:lintDebug
.\gradlew.bat :app:assembleDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

Owner Compose instrumentation runs through the GitHub Owner Compose UI CI
workflow (emulator). A green CI does **not** substitute for Galaxy S23 QA.
Recheck: Customer search/map/details, new whisky and beer direct adds,
existing whisky price edit, duplicate names, photo review of other/whisky,
all OCR serving edits, publish notice, stale versions, draft restore,
and narrow-screen/font scaling. Keep app data across update/reinstall.

## Backend dependencies (not Android work)

The merged #164 stores only `whisky` versus `other`, not beer/cocktail subtypes.
Follow-up I4-A3 operator-check resolution, I4-A4 advanced rematching/merge,
and I4-A5 server review drafts remain Backend/AI-owned where applicable.
Local review draft persistence already lives on-device and must not be
misrepresented as a server draft.
