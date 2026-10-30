# I3 Owner Mock State Contract (Android only)

Status: local Mock infrastructure. **Not an HTTP contract; nothing here changes API schemas.**
Sources: final Owner HTML (2026-10-30), `BottleMap_Owner_Backend_API_Contract_Gap_Review.md`,
`docs/frontend_backend_api_spec.md` on main. API agreement pending.

## Architecture / replacement boundary

- `data/owner/OwnerMockModels.kt`: local-only domain; names prefixed `Mock`, no Retrofit annotations.
- `OwnerMockRepository`: reads/writes one `StateFlow<MockOwnerLoadState>` and offers explicit methods.
- `LocalOwnerMockRepository`: pure Kotlin, deterministic business simulation with transactional
  replace-on-write snapshots. The same snapshot drives registration/application, store, published
  menu, import/review and mock customer preview. **Not a remote source of truth.**
- `MockOwnerStateStore`: `read/write` persistence boundary; `InMemoryMockOwnerStateStore`
  for JVM unit tests; `AndroidOwnerMockStateStore` stores JSON in app-private SharedPreferences
  under one key for Activity recreation and process restart.
- `OwnerMockRuntime.repository(context)`: one manual-DI singleton shared by all Owner routes.
  `OwnerMockViewModel.Factory(repository)` injects the interface, exposing a `StateFlow`.
  A future real adapter must not reuse mock-only fields without an agreed API.
- Local mock service operations are synchronous and storage writes precede emission.
  Disk failure preserves the last emitted state; explicit `retryLoad()` retries a failed read.
- Android process death: a fresh runtime instance loads the last persisted snapshot. Selection,
  menus, per-photo extraction lines, review decisions and import status persist.
  Real photo picker URI permissions must additionally be persisted by the future actual screen.
  App uninstall / Clear Storage resets the Mock; backup/restore and cross-device sync are not promised.
- **No production personal data**: local mock storage is neither encrypted nor server-backed.
  Do not use real applicant business numbers/representative data in testing. Images are URI references,
  not image bytes. Never log sensitive registration data.

## Proven data identity

- `MockCatalogProduct.productId` is a unique canonical catalog product (different age/edition
  must have different product IDs). Brand uses `brandId`.
- `MockBarMenuItem.barMenuItemId` is a unique *bar/product listing*, separate from productId.
  Within one bar the same productId may have **one** row only, with several `MockMenuOption`s.
- `MockMenuOption.optionId` is a separate row; duplicates of `(label, pourMl)` are rejected.
  Missing pourMl is valid for a Bottle/label-only option.
- In-memory discount is attached per option with `[start,end)` millis, and stock is per menu
  item (a mock policy, **not** confirmed API scope). Customer mock preview filters soldOut rows
  while Owner retains the row; menu data is never copied into a separate preview fixture.
- `MockBar.gallery/tags/weeklyHours/exceptions/description/defaultPourMl/lastVerifiedAtEpochMs`
  are **unagreed local UX fields**. Tags max five; 1–7 day/time and date intervals validated.
- Registration applications and ownership fixture approval are separate; `approveForFixture`
  is a TEST DRIVER ONLY, not an Owner screen action and not an operator API substitute.
- Initial snapshot is empty: 0 bars, applications, menu entries, products and imports. Explicit
  `OwnerMockFixtures.registeredBar()` is only used in tests and never seeded on app launch.

## Photo-specific import and add-only review (local simulation)

```
selected content URI (per photo)
  -> MockPhotoExtraction(imageId, sourceUri, order, lines)
  -> MockExtractedLine(extractedItemId, rawText, candidateProductIds, options)
  -> MockReviewDecision(kind, productId?, correctedOptions?)
  -> publishAddOnly(importId, reviewVersion)
  -> MockBarMenuItem(productId + multiple options)
  -> same MockPreview and Owner menu StateFlow
```

`MockPhotoExtractionSource` is injected and looks up **that exact selected photo URI**.
An unrecognized photo returns an empty extraction; it never invents seven whisky rows.
The import assigns unique stable local IDs to source lines and options; no string-name matching.
Review version is checked on every decision and publish. Every extracted line must have a
decision; duplicate option values with conflicting prices fail atomically. Existing posted products
are ignored in add-only publishing (no price/stock/options mutations). Publish error leaves the
draft and existing menu intact; second publish is rejected. An empty extraction may publish zero
new items without fabricating a normal operating status.

Mock processing currently returns `READY_FOR_REVIEW` synchronously for injected fixtures.
`PROCESSING`, `FAILED` and `APPLIED` are model states for future staged operations, not
an emulation of actual AI latency. UI should not claim real OCR or Backend publishing.

## API DTO and unagreed gap mapping

| Model or behavior | Existing approved API | Local-only / decision needed |
|---|---|---|
| Applicant/owner | spec 3.11 applications, me/bars | C04 approval-triggered extraction; C05 photo attachments |
| Public store info | spec 3.5-3.7, 3.9 basic fields | C06 readiness; C07 hours; C11 verified timestamp; C38/39/40 description/gallery/tags |
| Published menu & catalog IDs | spec 3.9, 6-8 item/product/option IDs | C08 direct CRUD; C09 stock; C10 discounts; C12 manual link |
| Menu import ID, reviewVersion, candidates | spec 4-8 | C01 15 vs 5 photos; C02 add-only; C03 payload decisions |
| Open/closed schedule, preview discounts | None | hours and promotions need agreed backend semantics |

Do not invent HTTP endpoints or DTO fields. When Backend contracts are approved:
1. Implement a new `OwnerMockRepository`-equivalent production interface or split interfaces
   by capability if necessary. Map only documented DTOs; leave unagreed screens on Mock.
2. Convert access-token/401/403/404 and stale reviewVersion into UI state, preserving draft
   and login ownership boundaries. Server must enforce add-only, do not rely on UI hiding actions.
3. Reconcile local draft keyed by server-issued `barId/productId/menuImportId`, never
   upload `local-*` IDs. Only after an integration test swap the runtime DI binding.
4. Review SharedPreferences protection before storing real registration/identity data;
   replace with appropriate secure storage, scope, expiry or server-owned draft strategy.

## Tests / Definition of Done

`LocalOwnerMockRepositoryTest`: empty load, read error and retry, fixture registration and
persistence recovery, canonical product vs serving option uniqueness, stock/discount preview,
photo-specific extraction, stale version, review persistence, successful add-only publication,
duplicate conflict rollback and persisted-write failure. Navigation tests assert Customer initial
screen and Owner group routes. Actual physical-device and backend verification remain separate.

Use `./gradlew :app:testDebugUnitTest :app:assembleDebug :app:lintDebug`.
