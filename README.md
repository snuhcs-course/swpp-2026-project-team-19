# BottleMap

<p align="center">
  <img src="docs/images/bottlemap-icon.png" alt="BottleMap icon" width="280" />
</p>

<p align="center"><strong>Find the bottle first, then the bar.</strong></p>

BottleMap is an Android application for drinkers who want to find bars serving a specific whisky. It turns bar-menu photos into structured, searchable menu data using AI, then lets customers search for a whisky and discover bars that currently serve it.

Developed by **Team 19 — Zero to One** for the SNU Software Development Principles and Practices course.

## Iteration 2

Iteration 2 focused on the **customer side** of the app. The historical demo used separate
Customer/Developer flavors. **Iteration 3 now uses one Android build with Customer search as the
default screen and the Owner entry accessible from My Page.** Owner registration, management,
and review screens are still work in progress; this does not imply completed server integration.

```text
Customer (guest or Google sign-in)
→ whisky search
→ serving-bar results (price, pour size, menu update date)
→ bar detail with full menu
→ map and nearby-bar discovery
```

### Demo Video

[![Iteration 2 demo video](https://img.youtube.com/vi/nqEcSemJcAA/hqdefault.jpg)](https://youtube.com/shorts/nqEcSemJcAA)

[Watch on YouTube](https://youtube.com/shorts/nqEcSemJcAA): customer search → bar comparison → bar detail and Kakao Map, then the developer-build owner flow (select bar → gallery or camera → extraction result).

## Features Demonstrated in Iteration 2

### Customer (Iteration 2 demonstration; now part of the unified build)
- Search without signing in (guest), or sign in with Google (Supabase Auth); the session is kept across app restarts until logout
- Search a whisky by Korean or English name or alias
- Result cards with bar, price, pour size, and menu update date; separate empty states for an unknown product and for no serving bars; retry on network or server errors
- Bar Detail screen with the full published menu, options, and update time; tap the address to copy it
- Embedded Kakao Map with bar markers from stored coordinates; bars without coordinates are handled
- Map-first bar discovery: bars in the visible map area, bar-name search on the map, and a nearby-bar carousel (1 km) that focuses the bar's marker
- Location-permission handling: denied permission and no nearby bars fall back without blocking search

### Owner / Operator (historical Iteration 2 developer-build demonstration)
- Select a bar, choose several menu photos from the gallery or take them with the in-app camera, and submit them in one import
- See the extraction result screen; the developer demo stops there and does not publish menus (temporary operator login, as in Iteration 1)

### Backend
- Public APIs for product search, bar menu/detail, nearby bars, map-area bars, and bar-name search
- Server verification of Google sign-in tokens (Supabase); protected owner endpoints
- Customer location is not written to the API access log

### AI / Data
- Hybrid menu extraction on the server: CLOVA OCR lines and the photo go to Gemini together (`EXTRACTION_MODE=hybrid`); if OCR fails, the photo alone goes to Gemini
- Product matching in menu import with staged rules after the exact alias match: S1 name variants, S2 brand + age/edition, S2b default product, S3 one-letter typo; each candidate records the rule that found it in `evidence.rule`
- Catalog v2 covering the pilot bars' whiskies, with Korean aliases for customer search
- Reviewed menus of four pilot bars published for customer search
- Evaluated but not deployed: an LLM matching layer and Naver Search candidates (results in the Design Documentation)

### CI/CD
- **Backend CI/CD:** tests on PostgreSQL; the check fails if line + branch coverage of `backend/app` is below 98%. `main` is deployed to the server after the tests pass
- **Android CI:** lint, unit tests, and debug APK builds for both flavors (Iteration 2 historical result). Iteration 3 CI runs a unified Debug variant.
- **AI CI:** AI unit tests with per-component coverage and a check that fails when tests are deleted or skipped

## Tech Stack

**Android:** Kotlin, Jetpack Compose, Material 3, Navigation Compose, ViewModel, Retrofit, OkHttp, Moshi, Kakao Maps SDK, Supabase Auth (Google sign-in)  
**Backend:** FastAPI, PostgreSQL, SQLAlchemy, Alembic  
**AI:** CLOVA OCR + Gemini (hybrid extraction), catalog aliases with staged matching rules  
**Deployment:** AWS EC2, RDS, S3, Caddy/HTTPS, GitHub Actions

## Repository Structure

```text
.
├── android/     Android app (unified Customer + Owner Navigation)
├── backend/     FastAPI server, matching, extraction adapters, tests
├── ai/          catalog, extraction/OCR/matching experiments, evaluation, AI tests
├── eval/        evaluation data
├── docs/        API spec, schema, matching flow, images
├── .github/     CI/CD workflows
└── README.md
```

## Getting Started

### Prerequisites
- Android Studio, JDK 17, Android SDK 37 (minimum SDK 26)
- Android device or emulator; location and camera features need a real device

### Clone

```bash
git clone https://github.com/snuhcs-course/swpp-2026-project-team-19.git
cd swpp-2026-project-team-19
```

### Build Settings

Pass these as Gradle properties (`-P...` or `~/.gradle/gradle.properties`). Never commit real keys; ask the team for them.

| Property | Needed for |
|---|---|
| `BOTTLEMAP_API_BASE_URL` | Backend URL. Deployed server: `https://bottlemap.o-r.kr/`. Debug default: `http://10.0.2.2:8000/` (emulator → local backend) |
| `BOTTLEMAP_KAKAO_NATIVE_APP_KEY` | Kakao Map. The app's package and signing-key hash must be registered in Kakao Developers |
| `BOTTLEMAP_SUPABASE_URL`, `BOTTLEMAP_SUPABASE_PUBLISHABLE_KEY`, `BOTTLEMAP_GOOGLE_WEB_CLIENT_ID` | Google sign-in. Guest search does not need it |

### Build

| Variant | Contents | Command |
|---|---|---|
| `Debug` | Customer search at startup; Owner UI skeleton from My Page | `./gradlew :app:assembleDebug` |
| `Release` | Same unified source set (separate release signing/config required) | `./gradlew :app:assembleRelease` |

There is **no Customer/Developer flavor chooser** and no separate flavor-specific APK.
The older temporary-operator menu-upload test route remains Debug-only and is not part of
the production Owner onboarding flow.

Example for the deployed backend (Windows: `.\gradlew.bat`):

```bash
./gradlew :app:assembleDebug \
  -PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/ \
  -PBOTTLEMAP_KAKAO_NATIVE_APP_KEY=<key> \
  -PBOTTLEMAP_SUPABASE_URL=<url> \
  -PBOTTLEMAP_SUPABASE_PUBLISHABLE_KEY=<key> \
  -PBOTTLEMAP_GOOGLE_WEB_CLIENT_ID=<client-id>
```

Debug APK output: `android/app/build/outputs/apk/debug/`.

**Galaxy S23 / Windows USB install** (connect a device with USB debugging enabled; from
the repository root, with build properties or credentials configured separately):

```powershell
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

Installation is not the same as launching the app; open BottleMap on the device afterward.
The first screen must be **Customer search**, never a Customer/Owner choice screen.

## Local Backend

See [`backend/README.md`](backend/README.md) for every setting.

```bash
cd backend
cp .env.example .env
uv sync
uv run --env-file .env alembic upgrade head
uv run --env-file .env python scripts/seed_catalog.py
uv run --env-file .env python scripts/seed_menu.py
uv run --env-file .env uvicorn app.main:app --reload
```

`MENU_EXTRACTOR=mock` needs no API keys. Real extraction needs `MENU_EXTRACTOR=gemini` with `GEMINI_API_KEY`, `EXTRACTION_MODEL`, `EXTRACTION_THINKING_LEVEL`, and, for `EXTRACTION_MODE=hybrid`, `CLOVA_OCR_INVOKE_URL` and `CLOVA_OCR_SECRET`.

Local API: `http://127.0.0.1:8000` · Swagger UI: `http://127.0.0.1:8000/docs`

## Testing

```bash
# Android
./gradlew :app:lintDebug
./gradlew :app:testDebugUnitTest
./gradlew :app:assembleDebug

# Backend (PostgreSQL test database, see backend/README.md)
cd backend && uv run --env-file .env pytest --cov

# AI (commands and policy in the Testing Documentation, section 2.1)
pytest ai
```

Iteration 2 results (details in the Testing Documentation):
- **Backend:** 918 tests passed, 98.95% coverage (after P40)
- **AI:** 141 tests (140 passed, 1 allowed skip that needs live CLOVA keys); coverage targets met for all four components
- **Android:** 110 JVM unit tests in 14 files passed for each flavor; coverage not measured yet
- **Device check:** 20 of 20 customer checks passed on a Galaxy S23 (developer flavor, deployed backend, reported by Hojin Nam)

## Known Limitations and TODOs

- **User testing:** external customer testing planned for Iteration 2 was moved to Iteration 3.
- **Owner features:** unified navigation and local-only Mock state are available from Customer My Page. Actual Owner screens and real API integration remain Iteration 3 work. The old temporary operator route is Debug-only and not part of Owner sign-in.
- **Devices:** the historical Iteration 2 device check used one Galaxy S23 and the Developer flavor. During Iteration 3 the unified app and Owner UI skeleton also passed the Android owner's Galaxy S23 regression checklist. Full Owner registration/import/publish UI device checks remain outstanding.
- **Android coverage:** no coverage report (JaCoCo) yet.
- **Matching:** the server runs rules only (exact alias and S1–S3). The LLM matching layer was evaluated but is not deployed. Menus written in Korean transliteration are still often left for the owner to match.
- **Processing:** menu processing runs inside the API process; a server restart during processing can leave an import in `processing`.
- **Build keys:** the Kakao, Supabase, and Google values are not in the repository and must be supplied at build time; release builds have no backend URL by default.

## Documentation

Project documents are in the [GitHub Wiki](https://github.com/snuhcs-course/swpp-2026-project-team-19/wiki):
- Proposal
- Requirements and Specifications
- Design Documentation
- Testing Documentation
- AI Collaboration Reports and Prompt Logs (Iterations 1 and 2)
- Risk Management
- Daily Standup Meeting Log
- Pilot Survey Results

## Team

**Team 19 — Zero to One**
- Nam Hojin — Android Frontend / Product Definition (Iteration 2 PM)
- Yang Haeul — Backend / Integration
- Park Jinwoo — AI
