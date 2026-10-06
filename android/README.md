# BottleMap Android local integration

P25 uses the backend contract implemented on GitHub `main`.

## Default emulator setup

The debug build defaults to:

```text
http://10.0.2.2:8000/
```

This routes the Android Emulator to a FastAPI server running on the development PC.

Start the backend with local PostgreSQL configured, migrations applied, the catalog seeded, and temporary operator authentication enabled. For the first frontend/API pass, keep:

```text
TEMP_AUTH_ENABLED=true
TEMP_AUTH_USER_TYPE=operator
MENU_EXTRACTOR=mock
```

The customer search endpoint is public, so Customer mode does not depend on the operator token.

## Override the backend URL

Do not edit Kotlin source for another server. Pass a Gradle property instead:

```sh
./gradlew assembleDebug -PBOTTLEMAP_API_BASE_URL=http://192.168.0.10:8000/
```

A trailing slash is added automatically when omitted. For a real phone on the same LAN, bind Uvicorn to an address reachable from the phone, for example `--host 0.0.0.0`, and use the PC LAN IP. Cleartext HTTP is allowed only by the debug manifest.

For deployment, pass the deployed HTTPS base URL with the same property. The release default deliberately points to an invalid placeholder so a production endpoint is not accidentally hard-coded.

## Owner E2E

1. Owner mode calls `POST /api/auth/temp-login`.
2. It loads `GET /api/bars` and uses `activeMenuImport` to resume unfinished work.
3. The system Photo Picker provides a content URI without broad storage permission.
4. JPEG/PNG images within the backend limit are uploaded directly when their signature and orientation are safe. Other decodable images, oversized images, and oriented JPEGs are converted to a bounded JPEG.
5. Upload uses one idempotency key per submit attempt and polls `GET /api/menu-imports/{id}` using `pollAfterMs`.
6. The review screen renders the real response and submits all current default decisions to `POST /api/menu-imports/{id}/review-and-apply`.
7. After `status=applied`, Customer mode can search the newly published product with `GET /api/search/bars`.

The minimal P25 review accepts the backend's rank-1 proposal, confirms non-product lines, creates a product from `newProductDraft` when there is no proposal, and applies every proposed change. Duplicate catalog conflicts are shown instead of being silently worked around.

## Gemini smoke

After the mock E2E is stable, restart the backend with:

```text
MENU_EXTRACTOR=gemini
GEMINI_API_KEY=...
EXTRACTION_MODEL=gemini-3.5-flash-lite
EXTRACTION_THINKING_LEVEL=medium
```

No Android code changes are required; the frontend only observes the longer polling interval and final review response.
