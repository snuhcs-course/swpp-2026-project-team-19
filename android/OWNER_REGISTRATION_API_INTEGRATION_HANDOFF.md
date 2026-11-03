# Owner registration Android integration handoff (PR #108)

## Source-of-truth precedence

- **Current contract:** repository `docs/frontend_backend_api_spec.md`, especially §§2.2, 3.11.1–3.11.15, 3.6 and 4–5.
- Drive's `BottleMap_frontend_backend_api_spec_v2.md` (modified Oct 4, 2026) predates the newer repository contract and does not describe owner applications. Do **not** implement from the older Drive copy.
- UI: approved ACTION_FIRST v4 HTML / PDF pp.2–19 and 21–29; p.26 is overridden by the Galaxy S23 reference screenshot.
- This PR preserves an **offline LocalOwnerMockRepository**. No real NTS, OCR, operator approval or upload integration is claimed by Android Mock screens.

## Confirmed API workflow to implement later (not part of PR #108)

1. Auth: use provider token; call `GET /api/me` before application submission. Owner is an **approved bar relationship**, not `userType=operator`. Only operator can approve/reject.
2. Optional certificate OCR: `POST /api/owner-applications/business-certificate-ocr` with one JPEG/PNG file, max 10 MB. Nullable recognized fields are prefill-only; the user edits/confirms them. Preserve partial OCR, 413/415/422/429/503 paths. The certificate image is not submitted automatically as an application property.
3. Existing bar: `GET /api/search/bar-names` (3.11.11) for the agreed server lookup and a real `barId`. This is **not** the as-yet unagreed address search UI.
4. Submit: `POST /api/owner-applications` only once. `existing_bar` sends `barId`; `new_bar` sends `proposedBar` name/address/optional phone; common business registration number, representative, `YYYY-MM-DD` opening date, contact phone. Do not send local `MockPhoto`, checkpoint, `submittedAtEpochMs`, `dismissedApplicationIds` or other Mock fields.
5. Once the server returns `201` with `applicationId`, upload ordered menu images via `PUT /api/owner-applications/{applicationId}/menu-photos` (whole-list replacement, up to 15, each <=10 MB, combined <=60 MB). **If upload fails after create, persist the returned application ID and retry only the PUT**, never create a duplicate application (a repeat POST can return `409 OWNER_APPLICATION_EXISTS`).
6. Read `GET /api/me/owner-applications` for all states, `GET /api/owner-applications/{id}` for details, `POST /api/owner-applications/{id}/cancel` for a pending application. “목록에서 지우기” currently means **local hide only**, not a server-side DELETE; the API defines no owner application delete endpoint.
7. After operator approval, refresh `GET /api/me/bars` / `GET /api/bars/{barId}` and read `activeMenuImport`. Approval may create a menu-import job; go to processing/review according to its real status, or photo selection if absent/failed. Never invoke `approveForFixture()` from an owner control or assume the owner can approve their own application.
8. Map errors centrally: `422 BUSINESS_VERIFICATION_FAILED` -> editable confirmation (input preserved); `429 RATE_LIMITED` -> limit screen with server `retryAfter`; `409 OWNER_APPLICATION_EXISTS` -> open existing application from `details.applicationId`; `404 USER_NOT_FOUND` -> `GET /api/me` then retry; 401/403 follow auth rules; OCR 503 fallback to manual entry; upload 409 -> reload status before retrying.

## Existing Mock state vs HTTP DTO

| Android Mock field/behavior | Contract mapping; integration guard |
|---|---|
| `MockRegistrationDraft` and `resumePageKey` | Local form/checkpoint only; not a request body. Do not persist applicant PII in plain app-private Mock preferences for a production build. |
| `MockOwnerApplication.submittedAtEpochMs` | Locally stamped at submission to avoid fabricated dates. Server `createdAt` and `reviewedAt` are separate nullable/nonnull RFC 3339 fields; parse to Instant and never label submitted time as review time. |
| `MockOwnerApplication.registrationPhotos` | Union of certificate/bar/menu references for local demos. Server application uses ordered `menuPhotos` signed URLs. Operator photo handling and bar photos have separate contracts; never serialize the union. |
| `MockPhoto.uri` | Android local camera/provider or picker URI, not a backend `imageUrl`. Stream bytes as multipart; handle transient grants and re-openability; refresh expired signed URLs via detail GET. |
| `MockApplicationStatus` and `VerifyFixture` | Only UI-side test states. Real status, `businessVerification` and error codes come from server responses. No owner-triggered fake approval/rejection. |
| `dismissedApplicationIds` | Local hiding of rejected cards. Do not invent an owner DELETE endpoint or claim the backend record was deleted. |
| `OwnerMenuPhotoStore` / first-registration capture | Preserve original draft and accepted upload photos until server ownership is established; delete only proven app-owned unreferenced files. The removed capture path is resolved through FileProvider rather than a filesystem guess. |

## Recommended incremental integration + Definition of Done

- Keep the Compose screens/navigation and a repository interface; replace the Local Mock implementation with a remote adapter and explicit DTO mappers **only after** testing real server responses.
- Test loaded/empty/loading/retry, process restart, slow network and 401/403/404/409/422/429/503, including a **successful POST followed by failed PUT**.
- Confirm server-generated application IDs and timestamps, never infer success from a local Mock decision.
- Preserve approved UI and previously verified Customer flow. Test Galaxy S23 manually before enabling the Owner flow for real users.
- Operator approval/rejection belongs to operator backend/dashboard; do not expose developer controls in Owner management.
- The current UI still uses Mock-only storage of sensitive business/contact data; production privacy/retention signoff must be completed separately before real applicants.

## PR #108 review cutoff

Merged-blocking Codex fixes: FileProvider capture deletion, real local application timestamp, safe unformatted phone number pasting. Removed the exception/application Debug QA catalog, hidden stage-label shortcut, component gallery / legacy upload entry from Owner onboarding, and fake approval/rejection buttons. **Mock repository and domain models remain intentionally** as test seams.
