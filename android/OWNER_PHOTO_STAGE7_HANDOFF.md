# BottleMap Owner Flow — Stage 7 Android handoff (2026-11-02)

**Status:** PR #96 (Open), Android local Mock implementation through Stage 7-8 review and Mock publish UI (PDF 92-97). Real OCR/AI, backend review-and-apply integration, and production publishing are NOT implemented; Mock publication changes only the local Mock repository.

## Sources and UI

- Source baseline: `BottleMap_owner_flow_ACTION_FIRST_v4.html` and `BottleMap_Owner_Flow_All_Screens_v4.pdf` (97 pages), specifically pages 43–44, 52–54, 81–83 and 90. The local files were opened and rendered; they are not added to Git. `DESIGN.md` is the design-system baseline.
- New navigation: `OwnerPage.MGR_PHOTO` (picker) and `OwnerPage.MGR_JOB` (process, ready, failed, canceled). The existing management-home status card resumes the *same persisted import ID*. `OwnerPage.MGR_REVIEW` implements local Stage 8 summary, line review, catalog search, new-product draft, price entry, resume and Mock publish/result flow; these are not HTTP API calls.
- Owner and customer menu section labels: local `otherAlcohol` items with nonblank `otherAlcoholKind` are grouped under the exact subtype text, e.g. 맥주/사케; missing subtype falls back to 기타 주류. This changes presentation, **not** canonical `category` or server DTO fields.
- Owner price rows adapt their width to measured formatted text for **legacy** high prices and font scaling; regular v4 price slots retain a minimum 129dp. There is no forced truncation.

## Photo validation and persistence

- Android Photo Picker, JPEG/PNG signature and sampled full-image decode, HEIC/HEIF input re-encoded to JPEG, EXIF orientation normalized for stored photos, 1–15 images, 10 MiB each, 60 MiB total. The UI shows real ordered count, not the 0/5 design mock.
- Files are streamed on `Dispatchers.IO` into `noBackupFilesDir/owner-menu-photo-drafts/`. Nothing puts a full bitmap in ViewModel/SavedState. Each image has a stable `photoId`; the selected list is saved as string tokens and submitted `MockPhotoExtraction` references `photoId`, private URI, and 1-based `imageOrder`. The repository snapshot is persisted across process recreation.
- Read failure, lost access, unsupported type, corrupt image, count/byte limit or low memory must show an error and allow re-selection. A failed multi-photo batch deletes its newly copied files atomically rather than silently admitting a subset.
- Picker image ordering follows the Photo Picker result order. No fabricated OCR results, JPEG data, real business photos or secrets are committed to Git.

## Mock import and contract differences

- `queuePhotoImport` commits `PROCESSING` without changing the published `menuItems`, then the job screen calls `finishPhotoImport` asynchronously. It only returns `READY_FOR_REVIEW` for deliberately injected URI-keyed extraction Fixtures; when there is no Fixture it returns `FAILED` with a neutral explanation. Production uploads/AI are not connected.
- `UPLOADED` is part of the server's state machine and an accepted Mock state, but the normal Mock queue goes directly to `PROCESSING`; neither backend transport nor a real upload progress percentage is simulated.
- Each source URI stays associated with its own lines, options and candidate IDs; no shared seven-row HTML Fixture is cloned.
- For a fixture price outside 1–99,999,999 KRW, the local extraction records `priceKrw = 0` and `needsPriceEntry = true`. Zero is a **missing-price placeholder**, never a free item, and cannot pass publish option validation. Stage 8 implements the PDF p90 Mock price entry form, retains source photo and line IDs, and refuses to publish until all decisions are complete. Stage 7 does not publish; Stage 8 Mock publish updates only local posted menu state.
- `cancelPhotoImport` supports `UPLOADED`, `PROCESSING`, `READY_FOR_REVIEW`; repeating cancel for `CANCELED` is a no-op. `APPLIED` and `FAILED` reject cancellation. The published menu is unchanged. Failed uploads can start a **new import ID** with the same retained photo IDs (`retryFailedPhotoImport`); changing selected photos creates a new job too.
- Repository mutation guard blocks direct add/edit, stock, deletion and reset for an active import. UI controls additionally show a non-destructive explanation. This is a Mock analogue of §3.14.1 `ACTIVE_IMPORT_EXISTS`, not evidence of backend integration.
- The photo-upload request's **`Idempotency-Key` is reused only for retransmission of an identical request**, never to create a new job after an earlier failed or completed import. §3.14 direct edits do not use this header. The Mock does not produce real HTTP idempotency keys.

## First registration handoff (0–5)

- `POST /api/owner-applications` returns an `applicationId`. Photo submission is a separate `PUT /api/owner-applications/{applicationId}/menu-photos` to the **same** application ID (all selected images in display order). Approval triggers the first import **on the server**: do not create a second client-side import on approval.
- If photo PUT fails after POST succeeds, retry **only** the PUT against the same application ID. Do not POST the application again. Current registration/approval Mock is left unchanged; actual API wiring belongs to an integration task.

## Verification and remaining risks

- JVM tests: 0/1/15/16 count and byte caps; JPEG/PNG signatures; 2 URI-specific fixtures; price placeholder; active write lock; cancel/failed/retry; persistence across repo reload. Compose tests: zero-photo CTA disabled, ready-job cancel, Owner+Customer subtype labels. Android CI/unit/lint and Owner Compose instrumentation run on the Open PR #96. CI success does not replace Galaxy S23 QA.
- Actual Galaxy S23 Photo Picker selection and large-font/portrait screenshot parity are **not** verified by automation. Before approval, test 0, 1, 15, and attempted 16 images; JPEG/PNG and HEIC conversion vs GIF; damaged/expired URI and storage errors; rotation and force-stop/reopen; failed retry; cancellation; current customer menu not changing; layout matching p43–44/p81–83.
- A photo with no development fixture intentionally reaches FAILED rather than inventing a ready review. Test fixture success is not a demonstration of real AI.
- Legacy already-published options above the price cap and 4+ servings have a separate data migration/direct-editor contract decision. The live `main` §3.14.2 10-option/Int contract and the 3-option/eight-digit frontend limit require explicit backend-owner agreement. Do not silently truncate data or claim Stage 8 review is integrated with a real backend.
- **Schedule mismatch:** the current Team19 Schedule row P47 describes owner tests/coverage, not this photo flow; P46 remains `Started` even after PR #91 merged. No Schedule cells have been edited. Draft branch slug is not task-completion evidence.

## Stage 8 local-only implementation (2026-11-03)

- Review entry and extractedItemId decisions are held in LocalOwnerMockRepository, not server autosave. Product matching uses stable catalog IDs; mockAutoAccepted marks only explicit fixture auto-matches. NON_PRODUCT is reviewable rather than silently blocking publishing.
- New product creation records name, brand, category, optional age and edition; the unmatched draft is saved across recreation and price-entry back navigation. Existing brand names require an explicit brandId; canonical brand name is at most 120 characters. New catalog product counts are deduplicated on publish.
- Final Mock posting uses publishAddOnly and preserves already posted prices and menu items. Success shows actual added menu rows and distinct newly created canonical products. This is NOT real backend review-and-apply.
- Active queued, processing and ready jobs block direct edits; failed is terminal and does not. Discard keeps older diagnostic imports preceding the most recent applied import and removes only the current unpublished retry chain and unreferenced private photo copies. Back from the unsubmitted picker deletes copies not referenced by an import.
- Developer-only hidden long-press fixtures, forced error routes, and sample menu panels were removed. Real photos without an injected fixture still fail truthfully; actual OCR/backend API integration remains future work.
- Manual approval gate: inspect retention/privacy of photo copies, sourceBox orientation overlay alignment and explicit product matching before merge. Galaxy S23 QA is required when changed behavior affects visible UI or a normal/critical user action, not for purely internal changes. No actual owner photos are committed.
