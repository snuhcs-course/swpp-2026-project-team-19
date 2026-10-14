# BottleMap Backend

FastAPI service backed by PostgreSQL (RDS in deployed environments). Run commands in this directory.

Deploying to AWS (EC2, RDS, S3, HTTPS) is described in [DEPLOY.md](DEPLOY.md).

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

## Setup and run

Create your local environment file from the template if it does not exist:

```sh
cp .env.example .env
```

```sh
uv sync
uv run --env-file .env uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive docs are at `/docs`.
`GET /health` returns `{"status":"ok","version":"<commit>"}` and does not require a database connection. `version` is the short hash of the commit the server started from (`null` outside a git checkout), so a deployment can be checked from outside.

## Authentication

Protected APIs take `Authorization: Bearer <token>` (API spec, section 3.1). Two kinds of token are accepted.

**Supabase access tokens (Google login).** The app signs in with Google through Supabase and sends the Supabase access token. The backend verifies it locally with the project's public signing keys (JWKS): signature (ES256), issuer, audience, expiry with 30 seconds of leeway, the required claims, and that it is not an anonymous session. No Supabase secret or `service_role` key is needed.

| Variable | Default | Description |
| --- | --- | --- |
| `SUPABASE_URL` | — | Project URL, e.g. `https://<project-ref>.supabase.co`. The issuer is `<url>/auth/v1` and the keys come from `<url>/auth/v1/.well-known/jwks.json`. Without it, Supabase tokens get `503` and temporary login still works. |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` | Accepted `aud`. |
| `SUPABASE_JWT_ALGORITHMS` | `ES256` | Accepted signing algorithms, comma-separated. Asymmetric only: `HS256` and `none` are rejected. |

The server checks these at start-up and refuses to start if a value is invalid. The public keys are cached for ten minutes; a token with an unknown `kid` refetches them, at most once every 30 seconds, which picks up a rotated key.

**Temporary tokens (local development).** `POST /api/auth/temp-login` issues a three-hour token for the fixed subject `local-dev-user` (display name `Local dev user`). It is off by default:

```sh
TEMP_AUTH_ENABLED=true \
TEMP_AUTH_JWT_SECRET="replace-with-a-local-secret-at-least-32-characters" \
TEMP_AUTH_USER_TYPE=operator \
uv run uvicorn app.main:app --reload
```

The role of a temporary token is `TEMP_AUTH_USER_TYPE` (`customer` or `operator`) at request time, so changing it applies to tokens already issued; the `user_type` claim in the token is ignored. The deployed server keeps temporary login on only until Google login works in the app.

**Users and roles.** `GET /api/me` is the only API that creates users: the first call stores the token's subject as `users.auth_subject` with user type `customer` (a temporary user takes `TEMP_AUTH_USER_TYPE`), and later calls keep the email in step with the token. Operator routes (`require_operator`) read a Supabase user's role from `users.user_type` on every request; a user without a row is a customer. Token claims never grant a role.

**Errors.** A missing, invalid or expired token is `401 UNAUTHENTICATED` with `WWW-Authenticate: Bearer`. When the server cannot check tokens (no `SUPABASE_URL`, signing keys out of reach or empty, invalid temporary-login settings) it answers `503 SERVICE_UNAVAILABLE`, so the app keeps the session and retries instead of sending the user back to login.

## Database configuration

Set these environment variables when database access or Alembic migrations are needed:

Local defaults are in the ignored `backend/.env` file. Run `uv` commands from `backend/` with `--env-file .env` to load them. The username, password, and database must match a local PostgreSQL role and database you create.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `POSTGRES_HOST` | Yes | — | PostgreSQL hostname, such as the RDS endpoint |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL port |
| `POSTGRES_USER` | Yes | — | Database username |
| `POSTGRES_PASSWORD` | Yes | — | Database password |
| `POSTGRES_DATABASE` | Yes | — | Database name |
| `POSTGRES_TEST_DATABASE` | For DB tests | — | Test database name; must end with `_test` (see Tests) |
| `POSTGRES_SSLMODE` | No | libpq default (`prefer`) | Set `require` for RDS so the connection never falls back to plain text |

Do not commit credentials. Export them in your shell or inject them through the deployment environment.

### Local PostgreSQL

Install PostgreSQL and create the role and database that match `backend/.env`:

```sh
# Ubuntu / WSL
sudo apt install postgresql
sudo -u postgres psql -c "CREATE ROLE bottlemap LOGIN PASSWORD 'change-me';"
sudo -u postgres psql -c "CREATE DATABASE bottlemap OWNER bottlemap;"

# macOS (Homebrew)
brew install postgresql@16
brew services start postgresql@16
export PATH="$(brew --prefix postgresql@16)/bin:$PATH"  # if psql is not found
psql postgres -c "CREATE ROLE bottlemap LOGIN PASSWORD 'change-me';"
psql postgres -c "CREATE DATABASE bottlemap OWNER bottlemap;"
```

To run the database tests, also create a separate test database (same commands with `bottlemap_test`):

```sh
sudo -u postgres psql -c "CREATE DATABASE bottlemap_test OWNER bottlemap;"   # Ubuntu / WSL
psql postgres -c "CREATE DATABASE bottlemap_test OWNER bottlemap;"           # macOS
```

Check that the server is running with `pg_isready -h localhost -p 5432`.

## Tests

```sh
uv run --env-file .env pytest
```

Tests that need PostgreSQL use the database named by `POSTGRES_TEST_DATABASE` (same host and credentials as `POSTGRES_*`). Each test run drops and rebuilds that database's schema from the migrations, and each test is rolled back afterwards, so the name must end with `_test`; any other name stops the run. If the variable is not set, the database tests are skipped and the other tests still run. Shared fixtures (`db_session`, `client`) are in `tests/conftest.py`. Tests always use the mock extractor, whatever `MENU_EXTRACTOR` says, so they never call the Gemini API. Auth tests never call Supabase either: they sign tokens with an ES256 key made in the test and serve the public keys from memory (the `supabase` fixture and `tests/auth_support.py`).

To measure coverage of `app/` (line and branch):

```sh
uv run --env-file .env pytest --cov
```

The run fails below 98% total coverage (`[tool.coverage.report]` in `pyproject.toml`). Skipping the database tests drops coverage well under that, so a missing test database cannot go unnoticed.

GitHub Actions runs the same command on every pull request and on pushes to `main` that touch the backend (`.github/workflows/backend-ci-cd.yml`), against a PostgreSQL 18 service container like the RDS instance. The run page shows a coverage table, and the full `coverage.xml` is attached as an artifact.

## Migrations

Models live under `app/models/` and must be imported from `app/models/__init__.py` for autogeneration. Apply the existing migrations with:

```sh
uv run --env-file .env alembic upgrade head
```

After changing models, generate a new migration and apply it:

```sh
uv run --env-file .env alembic revision --autogenerate -m "describe schema change"
uv run --env-file .env alembic upgrade head
```

Review autogenerated migration files before applying them to a shared or production database.

## Seed data

`scripts/seed_catalog.py` loads the pilot bars and the product catalog from `ai/catalog/` (`bars_v1.json`, `catalog_v1_draft.json`) into an up-to-date database:

```sh
uv run --env-file .env python scripts/seed_catalog.py
```

The script is safe to re-run. Bars, brands, and products are upserted by id, so edits in the JSON are applied on the next run. Aliases get `normalized_alias` from `app/core/normalize.py`; aliases that normalize to a value the same brand or product already has are skipped. Rows removed from the JSON are not deleted from the database. See `ai/catalog/README.md` for the JSON-to-table mapping.

`scripts/seed_menu.py` publishes the Seorosang demo menu (`ai/catalog/menu_seed_seorosang_v1.json`, 35 entries) so product search and menu lookup return results during development. Run it after `seed_catalog.py`:

```sh
uv run --env-file .env python scripts/seed_menu.py
```

Each run resets that bar's current menu board to the seed contents and sets `published_at` to now, so it also restores the menu after testing uploads or publishing. Existing bar menu items are reused by bar and product. Whisky Bokchun has no seeded menu and is kept empty for the live registration demo.

### Changing the normalization rules

`normalized_alias` is stored, so after changing `app/core/normalize.py` recompute it for every brand and product alias before the new backend serves lookups:

```sh
uv run --env-file .env python scripts/renormalize_aliases.py           # dry run: report only
uv run --env-file .env python scripts/renormalize_aliases.py --apply
uv run --env-file .env python scripts/seed_catalog.py
```

The dry run counts value changes and lists aliases that would be deleted because they now collide with another alias of the same brand or product, and values that become shared by different products (these turn exact matches into ambiguous ones). Re-running the seed afterwards adds aliases that were skipped under the old rules but are now distinct.

## Menu import (upload, review, publish)

An operator uploads menu photos with `POST /api/bars/{barId}/menu-imports`. The request stores the photos and returns `202` right away; extraction, product matching, and a draft diff against the bar's current menu run in the background. The app polls `GET /api/menu-imports/{menuImportId}` until the status is `ready_for_review` (full review data in the same response) or `failed`.

The operator then submits every decision at once with `POST /api/menu-imports/{menuImportId}/review-and-apply`. New brands, products and aliases, the decisions, and the new menu board are saved in one transaction, and the import becomes `applied`. Nothing reaches the catalog or the customer-facing menu before that. `GET /api/catalog/brands` and `GET /api/catalog/products` let the review screen find an existing brand or product before creating one.

```text
uploaded → processing → ready_for_review → applied
                      ↘ failed
```

To find where to upload or what to continue, `GET /api/bars` lists the bars with each one's unfinished import, and `GET /api/bars/{barId}/menu-imports` lists a bar's imports, newest first.

Request and response details, error codes, and rules not covered by the API spec draft are in Swagger UI (`/docs`).

### Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `IMAGE_STORAGE` | `local` | Where photos are stored: `local` (development) or `s3` (deployment). |
| `IMAGE_STORAGE_DIR` | `backend/var/images` | Directory for `local` storage (ignored by git). Files are served at `/media/...` for local development only. |
| `S3_BUCKET` | — | Required with `s3` (checked at start-up). Private bucket; review responses link photos through presigned URLs. |
| `AWS_REGION` | `ap-northeast-2` | Region of the bucket. Credentials come from the EC2 instance role (or `AWS_*` variables locally). |
| `S3_URL_TTL_SECONDS` | `900` | How long a presigned photo URL works; `imageUrlExpiresAt` tells clients when to fetch a new one. |
| `MENU_EXTRACTOR` | `mock` | Extraction backend: `mock` (fixed results, see below) or `gemini` (the vision LLM in `app/extraction`). |
| `GEMINI_API_KEY` | — | Required with `gemini`. Never commit it. |
| `EXTRACTION_MODEL` | — | Required with `gemini`. Exact model ID; P14 adopted `gemini-3.5-flash-lite`. |
| `EXTRACTION_THINKING_LEVEL` | — | Required with `gemini`: `minimal`, `low`, `medium` or `high`; P14 adopted `medium`. |
| `EXTRACTION_MAX_ATTEMPTS`, `EXTRACTION_REQUEST_TIMEOUT_S`, `EXTRACTION_WALL_TIMEOUT_S` | `6`, `300`, `330` | Optional retry and timeout settings for `gemini` (P14 values). |
| `EXTRACTION_MODE` | `gemini` | With `MENU_EXTRACTOR=gemini`: `gemini` (photo only) or `hybrid` (CLOVA OCR lines + photo, frozen hybrid prompt v1; OCR line boxes kept in `raw_output`). If OCR fails, the photo goes through `gemini` and the fallback is logged. |
| `CLOVA_OCR_INVOKE_URL`, `CLOVA_OCR_SECRET` | — | Required with `EXTRACTION_MODE=hybrid` (CLOVA General OCR). Never commit the secret. |

With `gemini`, the server checks these settings at start-up and refuses to start if one is missing or invalid. Each photo is one model call (a few seconds to a few minutes with retries) in the background job. A successful run stores the model's original output, model ID, tokens, latency and attempts in `extraction_runs.raw_output`; a failed run stores the error and, when the model answered, its text.

Matching uses the product aliases in the database, so load the catalog first (see [Seed data](#seed-data)).

### Mock extraction

The mock ignores the image content and picks a fixed result by the uploaded **file name**:

| File name | Result |
| --- | --- |
| contains `fail` | Extraction fails; the import becomes `failed`. |
| contains `sample` | 5 lines: a section header, an exact match (`글렌피딕 12년`), the same product with a conflicting age (ambiguous), an unknown product (unmatched), and a description. |
| anything else | A labeled real menu photo: 8 whiskies (exact matches) and 2 cognacs (unmatched), with `잔`/`병` prices, plus a header and a description. |

Every photo in one upload gets the same result. Extractors implement `MenuExtractor` in `app/adapters/extraction.py`; the Gemini one is `app/adapters/gemini_extraction.py`.

### Try it

With the server running and `TEMP_AUTH_ENABLED=true`, `TEMP_AUTH_USER_TYPE=operator` in `.env`:

- **Swagger UI:** open `/docs`, run `POST /api/auth/temp-login`, paste the token into **Authorize**, then call the upload endpoint (choose files under `images`) and the status endpoint with the returned `menuImportId`.
- **curl** (Whisky Bokchun has no seeded menu, so every item is an `add`):

```sh
TOKEN=$(curl -s -X POST localhost:8000/api/auth/temp-login | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])")
curl -s -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: $(uuidgen)" \
  -F mode=full_replace -F images=@sample.jpg \
  localhost:8000/api/bars/564384a5-b81e-5169-a09f-482da9310223/menu-imports
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/menu-imports/<menuImportId>
```

The upload accepts any real JPEG or PNG (checked by its first bytes), so any photo renamed to `sample.jpg` works. HEIC is rejected because the AI extractor accepts only JPEG and PNG.

### Submitting the review

Build the request from the `ready_for_review` response: one entry in `itemDecisions` for every item of every image, and one entry in `changeDecisions` for every `proposedChanges` entry. Accepting every proposal looks like this:

| Item | Decision |
| --- | --- |
| `effectiveLineType` is not `product` | `{"action": "confirm_non_product", "finalLineType": <effectiveLineType>}` |
| has `proposedProductId` | `{"action": "select_existing_product", "finalLineType": "product", "productId": <proposedProductId>}` |
| no candidate | `{"action": "create_product", "finalLineType": "product", "brand": {"type": "new", "canonicalName": ...}, "product": {"displayName": ...}}`, prefilled from `newProductDraft`; use `{"type": "existing", "brandId": ...}` for a brand found with `/api/catalog/brands` |

Each item also carries `extractedItemId`, and the body carries `reviewVersion` from the response. Mark each change `apply` or `ignore`; only applied `remove` changes take products off the board. Option corrections go in `optionDecisions`, and `reject` drops a misread line. Swagger UI shows every field and error code.

```sh
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d @review.json localhost:8000/api/menu-imports/<menuImportId>/review-and-apply
```

The response has the counts of added, updated, removed and ignored changes and of created brands and products; `GET /api/bars/{barId}/menu` and customer search show the new menu right away. Sending the same request again returns the same result without applying it twice.

### Resetting test data

- `scripts/reset_demo.py` brings the whole database back to the state right after seeding, for example after rehearsing the demo. It deletes every menu import (applied ones too) with its photos, every menu board, and every bar, brand, product, and alias that is not in the seed files, then runs the catalog and Seorosang menu seeds again. Other bars are left without a menu, and users are kept. It shows what it would delete without `--apply`.

  ```sh
  uv run --env-file .env python scripts/reset_demo.py            # show what would be deleted
  uv run --env-file .env python scripts/reset_demo.py --apply
  ```

- `scripts/seed_menu.py` restores the Seorosang board after a test publish. Brands, products and aliases created by a review stay in the catalog.
- `scripts/reset_menu_imports.py` deletes imports that were never applied, with their photos, for example one left in `ready_for_review` that blocks the bar's next upload (`409 ACTIVE_IMPORT_EXISTS`). It lists only without `--apply`. Applied imports are kept, since the board and created products refer to them.

  ```sh
  uv run --env-file .env python scripts/reset_menu_imports.py --bar <barId> --apply   # or --import <id>, --all
  ```

### Current limitations

- Processing runs inside the API process (FastAPI background tasks). If the server stops while an import is `processing`, it stays there.
- A product cannot be reactivated during review: selecting an inactive product is rejected (`PRODUCT_INACTIVE`).
