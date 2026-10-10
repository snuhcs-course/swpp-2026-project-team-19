# BottleMap

<p align="center">
  <img src="docs/images/bottlemap-icon.png" alt="BottleMap icon" width="280" />
</p>

<p align="center"><strong>Find the bottle first, then the bar.</strong></p>

BottleMap is an Android application for drinkers who want to find bars serving a specific whisky. It turns bar-menu photos into structured, searchable menu data using AI, then lets customers search for a whisky and discover bars that currently serve it.

Developed by **Team 19 — Zero to One** for the SNU Software Development Principles and Practices course.

## Iteration 1

```text
Owner uploads menu photo
→ AI extraction
→ product matching
→ owner review / publish
→ customer whisky search
→ serving-bar results
```

Iteration 1 is demonstrated through a **live demo on Android devices**.

### Demo Video

[Iteration 1 demo video](./iteration1_demo.mp4) (58 s, Korean subtitles) shows the full flow: customer whisky search, owner menu photo upload, extraction review, publishing, and a follow-up search that returns the newly published bar.

https://github.com/user-attachments/assets/95d5136d-451b-4b04-be59-0966a6e5605a

## Features

### Customer
- Search whisky by product name or supported alias
- Resolve names against the canonical catalogue
- Show bars currently serving the matched product
- Show bar name, price, pour size / option label, menu update date, and distance when available
- Handle loading, unknown-product, no-bars, and network/API error states

### Owner / Operator
- Temporary operator login for the Iteration 1 demo
- Load registered bars and resume unfinished imports
- Select a menu image with Android Photo Picker
- Validate and prepare JPEG/PNG images before upload
- Upload menu image and poll extraction status
- Review real AI extraction/matching results
- Apply current backend proposals and publish
- Search the published result from Customer mode

### AI / Data
- Gemini-based menu extraction
- Canonical whisky catalogue with Korean/English aliases
- Product entity resolution for menu upload and search
- Evaluation scripts and preserved experiment outputs

## Tech Stack

**Android:** Kotlin, Jetpack Compose, Material 3, Navigation Compose, ViewModel, Retrofit, OkHttp, Moshi  
**Backend:** FastAPI, PostgreSQL, SQLAlchemy, Alembic  
**AI:** Gemini vision model, canonical product catalogue, alias matching  
**Deployment:** AWS EC2, RDS, S3, Caddy/HTTPS

## Repository Structure

```text
.
├── android/
├── backend/
├── ai/
├── eval/
├── .github/
└── README.md
```

## Getting Started

### Prerequisites
- Android Studio
- JDK 17
- Android SDK 37
- Android device or emulator
- Minimum Android SDK: 26

### Clone

```bash
git clone https://github.com/snuhcs-course/swpp-2026-project-team-19.git
cd swpp-2026-project-team-19
```

### Build for the deployed backend

macOS/Linux:

```bash
./gradlew :app:assembleDebug -PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/
```

Windows PowerShell:

```powershell
.\gradlew.bat :app:assembleDebug -PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/
```

APK output:

```text
android/app/build/outputs/apk/debug/
```

> The default debug endpoint is `http://10.0.2.2:8000/` for local emulator development. For the deployed demo backend, pass `BOTTLEMAP_API_BASE_URL` explicitly.

## Local Backend

See [`backend/README.md`](backend/README.md).

Typical setup:

```bash
cd backend
cp .env.example .env
uv sync
uv run --env-file .env alembic upgrade head
uv run --env-file .env python scripts/seed_catalog.py
uv run --env-file .env python scripts/seed_menu.py
uv run --env-file .env uvicorn app.main:app --reload
```

Local API: `http://127.0.0.1:8000`  
Swagger UI: `http://127.0.0.1:8000/docs`

## Testing

### Android

```bash
./gradlew :app:testDebugUnitTest
./gradlew :app:assembleDebug
```

Current unit tests cover customer search mapping and owner review-decision mapping, including unknown product/no-bars distinction, nullable pour sizes, RFC3339 timestamps, and unresolved review decisions.

### Backend

```bash
cd backend
uv run --env-file .env pytest --cov
```

Backend CI/CD runs the tests on relevant pull requests and pushes to `main`, and deploys `main` to the server after they pass. The current Iteration 1 baseline reports **434 passing tests** and about **99% line-and-branch coverage**.

## Live Demo Flow

### Owner
1. Open **Owner** mode.
2. Select the demo bar.
3. Choose a real menu image.
4. Upload it.
5. Wait for AI extraction/matching.
6. Review the extracted menu.
7. Confirm and publish.

### Customer
1. Open **Customer** mode on the second phone.
2. Search for a whisky published in the owner flow.
3. Confirm that the corresponding bar appears.
4. Check price / option information and update time.

## Known Limitations

- Android currently supports one image per menu import, while the backend supports multiple images.
- Iteration 1 review is a minimal thin slice and is not yet a full catalogue-correction editor.
- Bar detail and map interaction are deferred beyond the Iteration 1 results-list slice.
- Temporary operator authentication is for the demo period only.
- Gemini extraction latency can vary from several seconds to longer.
- Menu processing runs inside the FastAPI process; a server restart during processing can leave an import stuck in `processing`.
- Android has local unit tests, but no permanent Android GitHub Actions workflow on `main`.
- Release builds have no production backend URL by default; the URL must be supplied at build time.

## Demo Readiness Checklist

- [ ] Pull latest `main`
- [ ] Confirm deployed `/health` works
- [ ] Confirm temporary operator login is enabled
- [ ] Confirm demo catalogue/database state
- [ ] Build with `https://bottlemap.o-r.kr/`
- [ ] Install the same verified build on both demo phones
- [ ] Run `:app:testDebugUnitTest`
- [ ] Run `:app:assembleDebug`
- [ ] Smoke-test Owner upload → extraction → review → publish
- [ ] Smoke-test Customer search on the second phone
- [ ] Keep one known-good JPEG/PNG demo menu image on-device
- [ ] Confirm stable network access
- [ ] Freeze code/config/demo data after the final smoke test unless a critical fix is needed

## Documentation

Project documentation is maintained in the GitHub Wiki:
- Proposal
- Requirements and Specifications
- Design Documentation
- Testing Documentation
- Risk Management
- Meeting Logs
- Iteration 1 Pilot Survey Results
- AI Collaboration Report

## Team

**Team 19 — Zero to One**
- Nam Hojin — Android Frontend / Product Definition
- Yang Haeul — Backend / Integration
- Park Jinwoo — AI / Iteration 1 PM

## Iteration 1 Status

The core thin slice is integrated on `main`:

```text
menu photo upload
→ AI extraction
→ product matching
→ human review / publication
→ customer whisky search
→ serving-bar result
```
