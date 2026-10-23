# BottleMap agent guide

Instructions for AI coding agents working in this repository, shared by the Android (FE), backend (BE), and AI work. `CLAUDE.md` imports this file, so keep the shared rules here.

BottleMap is an Android app that finds bars serving a specific whisky. Bar owners or operators upload a menu photo, AI extracts the menu, items are matched to a whisky catalogue, a person reviews and publishes the result, and customers search the published menus.

Bar owners onboard themselves: they log in with Google, apply to own an existing bar or to register a new one, and an operator approves the application. Operators can still create bars directly, but as the service grows, bars are expected to come in through owner applications rather than one by one from operators.

## Repository layout

| Path | What it is | Owner |
|---|---|---|
| `android/app/` | Android app: Kotlin, Jetpack Compose, Retrofit/OkHttp/Moshi. Package `com.zerotoone.bottlemap` | Hojin Nam |
| `backend/` | FastAPI + PostgreSQL (SQLAlchemy 2, Alembic), managed with `uv`. Deployment in `backend/DEPLOY.md` | Haeul Yang |
| `ai/` | Extraction experiments, catalogue and seed data, evaluation scripts | Jinwoo Park |
| `docs/` | Specs shared by FE and BE (see below) | Team |

The Gradle root is the repository root (`settings.gradle.kts` maps `:app` to `android/app`).

## Specs: the contract between FE and BE

- `docs/frontend_backend_api_spec.md`: HTTP API contract (paths, request and response bodies, error codes, frontend handling).
- `docs/schema_draft.dbml` and `docs/schema_guide.md`: database schema and the meaning of each table and column.
- `docs/menu_ai_matching_flow.md`: menu import, AI extraction, matching, review, and publishing rules.

For an API that is already implemented, the backend code and its OpenAPI (`/docs` on a running server) show the actual behavior. Trust the specs and the current code over old chats, drafts, or memory. If two of them disagree, do not guess: state the conflict and name the owner who has to decide (see the Owner column above).

Each member owns their area. Do not redesign another member's code without their agreement, and do not change it unless the task asks for it. If a change alters the contract (a path, a field, an error code, or behavior the other side relies on), confirm it with the owner of the other side, update the API spec in the same PR, and say in the PR description what the other side must change.

## Working rules

- Before starting, check the requirement, the current iteration scope, the relevant contract in the specs, and what counts as done.
- Make small changes that can be tested.
- Never invent API fields or backend behavior that the API spec does not define. If the other side is not built yet, work against mock data that follows the spec.
- State your assumptions clearly instead of presenting them as facts.
- When you finish, check the change against the requirement, the request and response types on both sides, and the error and failure cases.

## Commands

Android (run from the repository root):

```sh
./gradlew :app:testDebugUnitTest
./gradlew :app:assembleDebug                                                 # uses http://10.0.2.2:8000/
./gradlew :app:assembleDebug -PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/
```

Never hard-code a server URL in Kotlin; pass `BOTTLEMAP_API_BASE_URL`.

Backend (run from `backend/`):

```sh
uv sync
uv run --env-file .env pytest --cov                     # CI fails below 98% coverage
uv run --env-file .env uvicorn app.main:app --reload
uv run --env-file .env alembic upgrade head
```

Database tests are skipped unless `POSTGRES_TEST_DATABASE` (ending in `_test`) is set in `backend/.env`; a run with skipped database tests also drops below the coverage threshold. Tests always use the mock menu extractor and must never call the Gemini API or Supabase: auth tests sign their own tokens and serve the public keys from memory (the `supabase` fixture in `backend/tests/conftest.py`).

## API conventions (both sides)

- JSON field names are `camelCase`. IDs are UUID strings, times are UTC RFC 3339 strings, prices are integer KRW, and a missing value is `null`, not an empty string.
- Errors use one shape: `{"error": {"code", "message", ...}}`. Clients branch on `error.code`, not on the message text.
- Auth is `Authorization: Bearer <token>` with a Supabase access token from Google login (spec 3.1). `POST /api/auth/temp-login` stays for local development, and for the demo server only until Google login works in the app. The backend accepts both kinds: Supabase tokens are verified with the project's public keys (`SUPABASE_URL`), and temp-login tokens only while `TEMP_AUTH_ENABLED=true`.
- Permissions come from the server, never from the client or the token's claims. A Supabase user's `users.user_type` (`customer` or `operator`) is read from the database on every request, and a user without a row is a customer; a temporary token takes its role from `TEMP_AUTH_USER_TYPE` on the server.
- Being a bar owner is not a user type but a `bar_owners` row linking a user to one bar, created when an operator approves an owner application (spec 3.11).
- Customer search (`GET /api/search/bars`), nearby bars (`GET /api/search/nearby-bars`), map bars (`GET /api/search/map-bars`), bar-name search (`GET /api/search/bar-names`), and bar menu (`GET /api/bars/{barId}/menu`) are public. Bar management, menu import, and review APIs are for operators and the bar's approved owner; the catalogue search APIs are for operators and owners. Approving owner applications is operator-only. The full table is in spec 2.2.

## Android notes

- Structure is MVVM with repositories: screens and their `ViewModel`s in `ui/customer/` and `ui/owner/`, screen state exposed as `StateFlow`, API calls through the repositories in `data/`, and Retrofit with Moshi in `network/`. Async work uses Kotlin coroutines.
- Dependencies are wired by hand (no Hilt or other DI framework).
- Every screen that loads data handles loading, success, empty, error, and retry states.

## Backend notes

- Change the schema only through a new Alembic migration. Never edit a migration that is already on `main`.
- Routes stay thin. Business logic goes in `app/services/`, external systems (Gemini, S3, local storage) sit behind the interfaces in `app/adapters/`, and matching lives in `app/matching/`.
- Raise spec errors with `ApiError(status, code, message)` from `app/core/errors.py` so the response uses the common error shape.
- Every `/api` route is listed with its permission in `backend/tests/test_route_permissions.py`; add a new route there when you create it.
- `scripts/reset_demo.py` and `scripts/reset_menu_imports.py` delete data. Do not run them against the deployed database unless explicitly asked.

## Git and PRs

- Branch from `main` as `feature/i<iteration>-<task-id>-<short-name>`, all lowercase, for example `feature/i2-p9-google-token-verification` for task P9 in Iteration 2.
- The PR title is `I<iteration>-<task ID>: <task summary>`, for example `I2-P9: Implement server verification of Google login tokens; handle invalid and expired credentials`. A PR that covers several tasks lists them with `/`, as in `I2-P13/P14: ...`. PRs are squash-merged.
- Commit or push only when the member you are working for asks.
- Merging to `main` deploys the backend to production automatically after CI passes, so `main` must stay deployable.

## Never commit

- Secrets: any `.env` file (only `.env.example`), API keys, database passwords, JWT secrets, SSH keys. Do not paste them into chat or logs either.
- Anything under `data/`, including menu photos: owners consented to their use in the project, not to publishing them, and the repository is public.
- Build outputs (`android/app/build/`, APKs), `backend/.venv/`, and coverage files.
