# I5-P21: customer location on the device

P21 consumes the existing P15 API (merged in #212), `GET /api/search/all-bars`.
The API contract is already defined in sections 3.10 and 3.19 of
`docs/frontend_backend_api_spec.md`. No Backend, AI, schema, or shared API
specification changes are required by this Android implementation.

## Data flow

- `BottleMapApi` no longer exposes customer latitude/longitude or map bounds.
  The old nearby-bars and map-bars request methods have been removed.
- `Repositories.allBars` shares one `AllBarsRepository` between map and nearby
  repositories, including their independently created screen instances.
- The catalog contains public bar metadata only. It is cached in memory for
  60 seconds, then refreshed on the next request. Empty results are cached;
  failed, malformed, and cancelled responses are not. Concurrent callers share
  a successful fetch. Customer coordinates and filtered results are not cached.
- Nearby bars use Haversine with radius `6,371,008.8` m and round to integer
  meters using ties-to-even before radius filtering. Equal distances sort by
  bar ID. The existing 1 km carousel and maximum 3 km repository radius remain.
- Map bars use inclusive rectangle edges, sorted by bar ID. The existing screen
  zoom/TooWide guard remains a presentation policy, although the all-bars API
  itself has no bounds or span limit.
- Product search requests retain `limit=100`, without location. Search starts
  without waiting for GPS. A late foreground fix updates distance locally;
  it does not send another search or record another search-completed event.
  Distance ties use bar name, product display name, bar ID, product ID.
- Without a location, the distance projection preserves the server's order.
  Existing available sort options and explicit user sorting continue to apply.
  Existing permission, loading, empty, error, and retry UI is reused.

## Decisions and limits

- The user requested silent truncation: there is no new result-limit message.
  If `truncated=true`, only the returned rows participate in distance sorting;
  a closer bar beyond the server's 100-row cutoff cannot appear in that result.
- The response does not identify the server's exact-match-first brand groups.
  Local distance sorting therefore follows section 3.19.4's ordering without
  those groups.
- A newly approved/deactivated bar can take up to 60 seconds to appear in a
  subsequent catalog query. TTL expiry does not trigger background polling.
- The existing one-shot `AndroidNearbyLocationSource` remains in use.
  This change addresses requests to BottleMap's customer API. It does not
  establish what map tiles/viewport metadata the Kakao SDK sends to Kakao;
  the plan's TA/store-policy question remains a separate follow-up.
- The legacy nearby response decoder remains for existing contract tests; it
  is no longer used by production discovery. The old GPS-before-search test
  was replaced because forwarding customer location is precisely what P21
  removes, with new network and late-GPS regression coverage instead.

## Local verification

Run from the repository root:

```powershell
.\gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug :app:compileDebugAndroidTestKotlin
```

Added tests cover independent server-formula distance fixtures (including the
500 m rounding boundary, antimeridian and pole), inclusive viewport edges,
metadata preservation, cache sharing/concurrency/TTL/empty/failure/cancellation,
late GPS/permission revocation, complete distance tie ordering, and actual
Retrofit HTTP requests to a loopback JDK HTTP server (no added dependencies).

`OnDeviceLocationNetworkTest` writes a synthetic-only capture to
`android/app/build/reports/p21-network.log`. It checks one catalog request
across nearby/map screens and changed locations, plus query, product ID, and
legacy search requests. Every request must omit location/bounds parameters,
body, and Authorization. The generated log is ignored with build outputs.
This is automated local HTTP evidence, not a Galaxy S23 network capture.

Captured requests from the local test (synthetic data only):

```text
GET /api/search/all-bars
GET /api/search/bars?query=synthetic%20whisky&source=input&limit=100
GET /api/search/bars?productId=00000000-0000-4000-8000-000000000021&source=popular&limit=100
GET /api/search/bars?query=synthetic%20legacy&limit=50
4 requests; no customer coordinates/bounds/body/Authorization.
```

## QA result — complete with approved automated substitutions (2026-11-26)

The user reported the four functional Galaxy S23 checks below as passing.
They explicitly requested automated validation in place of the two checks
that were difficult to observe on the phone. Those two checks were rerun:

```powershell
.\gradlew.bat :app:testDebugUnitTest --tests '*OnDeviceSearchTest' --tests '*OnDeviceLocationNetworkTest' --tests '*AllBarsRepositoryTest'
```

Result: **13 passed, 0 failures, 0 errors, 0 skipped** (3 suites).

```text
Galaxy S23 / approved automated P21 QA results
Branch: feature/i5-p21-on-device-location
[x] Whisky search -> bar detail -> Back: passed, user-reported on Galaxy S23.
[x] Location allowed: nearby bars, distance sort, map movement: passed, user-reported on Galaxy S23.
[x] Location denied/revoked: search and map browsing remain usable: passed, user-reported on Galaxy S23.
[x] Late GPS does not duplicate search: passed by approved automated substitution (OnDeviceSearchTest).
[x] Customer coordinates/map bounds absent from requests: passed by approved automated substitution (OnDeviceLocationNetworkTest).
[x] Relaunch: search, map and login: passed, user-reported on Galaxy S23.
Result: 4 device checks passed + 2 automated substitutions passed; 0 failed.
```

The late-GPS test completes the first search before supplying location, then
repeats the same selection and revokes location. The repository call count
and search-completed event count remain one; an explicit forced refresh
still makes a second request. The search effect is keyed only by query,
product selection, and source, not GPS.

The network test captures real serialized Retrofit requests on a loopback
HTTP server across nearby/map screens, changed origins/viewports, and three
search forms. It confirms one shared catalog fetch and no customer coordinate
or bounds parameters, request body, or Authorization. This is not a physical
phone capture and does not inspect Kakao SDK traffic.

### Installation reference

Preserve existing app data and run these commands in order:

```powershell
git fetch origin
git switch feature/i5-p21-on-device-location
git pull --ff-only
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

If installation cannot see the phone, enable USB debugging and check that
`adb devices -l` lists it as `device`. Do not clear app data for this check.

### CI and review are separate from QA

For implementation commit `4a4366ac`, Android CI and AI CI succeeded. Owner
Compose UI CI failed in
`OwnerRegistrationV4ComposeTest.manualBusinessFormKeepsDigitsAndTransitionsToNextStages`:
the opening-date heading was not found. Neither that test nor the onboarding
screen is changed by P21. The cause is unconfirmed; this is an unresolved CI
finding, not a claim of a confirmed main-branch failure. See
[the run](https://github.com/snuhcs-course/swpp-2026-project-team-19/actions/runs/45768883853).

P21 QA is complete under the user's accepted validation method. Human review
and PR disposition remain; the schedule stays Started. Actual work-time and
end-date fields are unchanged.
