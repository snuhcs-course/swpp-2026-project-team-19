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

## Galaxy S23 QA — pending user execution

Preserve existing app data and run these commands in order:

```powershell
git fetch origin
git switch feature/i5-p21-on-device-location
git pull --ff-only
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

If installation cannot see the phone, enable USB debugging and check that
`adb devices -l` lists it as `device`. Do not clear app data for this check.

Copy the block below, mark results, and return it in chat:

```text
Galaxy S23 P21 QA
Branch: feature/i5-p21-on-device-location
[ ] Start as Guest: customer search opens; search a whisky, select a product, open its bar detail, and return successfully.
[ ] Grant location: nearby/map pins and distances appear; nearest-first sorting works. Pan the map and verify pins match the visible region.
[ ] Switch list/map, open a bar and go Back: selection and navigation still work; existing map zoom-limit behavior remains.
[ ] Deny/revoke location: search and map browsing remain usable; distance sorting is unavailable, with no crash or stale location distance.
[ ] Start a search before GPS is ready: results appear; GPS later supplies distances without a second search request.
[ ] With Network Inspector or an authorized debug capture, inspect nearby/map/whisky-search requests: all-bars has no query; search has no lat/lng; no nearby-bars/map-bars request is made. Keep real coordinates/tokens out of shared logs.
[ ] Switch nearby/map within 60 seconds: the bar catalog is reused. After 60 seconds and a new query, it refreshes; offline refresh shows the existing retry state and retry succeeds after reconnection.
[ ] Background/relaunch: no crash; Guest/Google login, customer search, map, and bar detail still work.
Result: pending
```

CI completion, device QA, a device network capture, and review are recorded
separately. P21 stays Started until its remaining evidence and required review
are complete. Actual work-time and end-date fields are owned by the user.
