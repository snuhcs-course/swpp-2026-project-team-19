# BottleMap I2-P19/P20/A5 — Google + Supabase Android Auth Setup

**Implementation:** Android Credential Manager → Google ID token with nonce → Supabase Auth `signInWith(IDToken)` → persisted/auto-refreshed Supabase session → `GET /api/me` with Supabase access token.

**Source of truth:** `docs/frontend_backend_api_spec.md` sections 2.2, 3.1 and 3.2. Google ID tokens are **never** sent to the BottleMap backend. Supabase anonymous sign-in is **not** used; Guest means no token.

## 1. Google Cloud

1. In Google Cloud Console, select the Google project connected to the team's Supabase project.
2. Configure Google Auth Platform consent branding/audience as needed and add test users while the application is in testing mode.
3. Create an **OAuth Web application client ID**. This is the Android app's `BOTTLEMAP_GOOGLE_WEB_CLIENT_ID` and the `setServerClientId(...)` value. Do not use an Android client ID here.
4. Create an **Android OAuth client** for applicationId `com.zerotoone.bottlemap` and the SHA-1 signing certificate fingerprint for each relevant debug/release keystore.
5. From repo root on Windows, run:

   ```powershell
   .\gradlew.bat :app:signingReport
   ```

   Copy `SHA1:` under the **debug** variant to the Google Android OAuth client. This is the **colon-separated SHA-1**, not Kakao's Base64 key hash. Different PCs can have different debug signing certificates.

## 2. Supabase Dashboard

1. Open the team's Supabase project → **Authentication → Providers → Google** and enable the provider.
2. Configure the Google **Web OAuth client ID and client secret** in the Supabase dashboard. Register the Android client ID(s) as additional valid client IDs/audiences if supported in your provider console.
3. Keep **Skip nonce check OFF**. Android sends SHA-256(rawNonce) to Google and rawNonce to Supabase.
4. Check **Auth signing keys** are ES256 (as required by the BottleMap backend), rather than an HS256-only legacy secret. Backend JWKS verification cannot validate a legacy HS256 session.
5. Get the Supabase **project URL** and **publishable / anon client key** from project settings (client publishable key is not `service_role` and is intended for client apps).
6. Do not enable Supabase anonymous sign-in for this flow.

Ask the Backend owner to verify the deployed server's `SUPABASE_URL`, `SUPABASE_JWT_AUDIENCE=authenticated`, `SUPABASE_JWT_ALGORITHMS=ES256` settings, without sharing secret values.

## 3. Local Android settings (outside Git)

In `%USERPROFILE%\.gradle\gradle.properties` (Gradle global properties), add:

```properties
BOTTLEMAP_GOOGLE_WEB_CLIENT_ID=YOUR_GOOGLE_WEB_OAUTH_CLIENT_ID.apps.googleusercontent.com
BOTTLEMAP_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
BOTTLEMAP_SUPABASE_PUBLISHABLE_KEY=YOUR_SUPABASE_PUBLISHABLE_KEY
```

These properties are compiled into `BuildConfig`. **Never use Supabase service_role or a Google client secret in an Android APK.** The client publishable key and Web client ID are not secret credentials; they still must correspond to the correct project.

Keep the existing `BOTTLEMAP_KAKAO_NATIVE_APP_KEY` setting for the map.

## 4. Build / S23 verification

```powershell
git fetch origin
git switch --track origin/feature/i2-p19-p20-a5-google-supabase-auth
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

To check the backend account endpoint using a valid session, use Android's signed-in My Page UI and do **not** paste access or refresh tokens into chat/logs.

### Manual acceptance

- [ ] No account: launch → Customer search/result → Bar Detail → Kakao Map works without any credential prompt.
- [ ] Customer Search header → My Page shows `Guest로 이용 중`.
- [ ] Login → select Google account → My Page shows backend `displayName` or email and `userType`.
- [ ] Cancel Google selection → remains Guest, can search.
- [ ] Disable network during Google sign-in → error UI; restored network → retry succeeds.
- [ ] Tap login twice → only one credential selection request.
- [ ] Force-stop and relaunch the app → Supabase session restores, `GET /api/me` reloads profile.
- [ ] Rotate/activity recreation (portrait is configured), background/foreground → stable auth UI.
- [ ] Logout → My Page Guest; app restart remains Guest; no previous user's auth header.
- [ ] Expired session: SDK refreshes; invalid refresh token returns to Guest/safe sign-in state without an infinite loop.
- [ ] Login with Google and visit bar detail/map; signed-in account does not block public search.

### PR #35 review regression checks (after auth race fixes)

**Keep PR #35 unmerged until these have been checked on the current branch head.**

1. **Stale profile response vs. Logout**: from Signed-in My Page, trigger Logout while profile/account work could still be running. Guest must appear immediately and the previous account must never reappear. The `AuthViewModelTest.logoutImmediatelyHidesIdentityAndIgnoresLateUncancellableProfileResponse` unit test deterministically simulates a late non-cancellable response.
2. **Expired/invalid session**: use a dedicated Google/Supabase test account and a safely invalidated refresh session. After SDK reports NotAuthenticated or Backend `401 UNAUTHENTICATED` (following its one permitted refresh), My Page must transition to Guest without retrying `/api/me` endlessly.
3. **Transient outage**: sign in, disable mobile data/Wi-Fi temporarily while profile refresh is needed, then restore connectivity. A `NETWORK_ERROR` or `503` must retain Supabase credentials and offer account sync Retry, not silently log out.
4. **Offline Logout**: sign in, turn off networking, tap Logout, force-stop and relaunch. Account must still be Guest. Re-enable the network and confirm that old authenticated UI/token does not reappear.
5. **Credential Manager screen exit**: while the Google account chooser is open, press system Back; repeat after Home/background and Activity recreation (Developer options > Don't keep activities can help). Returning to Login must allow another attempt, not remain stuck on SigningIn. Leaving the UI **after** delivering the Google credential should not cancel the ViewModel-owned Supabase exchange.
6. **Guest regression**: with no session and after logout, run Search → Results → Bar Detail → Kakao Map; also check navigation Back. Authentication must never gate these views.

To retain a local build/test log **outside the repository** (do not paste access tokens into logs):

```powershell
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/" 2>&1 |
    Tee-Object -FilePath "$HOME\Desktop\bottlemap-pr35-android-build.log"
```

Confirm `BUILD SUCCESSFUL`, record the tested commit SHA (`git rev-parse HEAD`), Android device/OS, and concise pass/fail notes. Redact any OAuth/client credentials or tokens before sharing evidence with reviewers. No Android GitHub Actions job is added by this task.

### Troubleshooting

- No Google accounts / account chooser error: Google Play services installed, correct Web client ID, Android OAuth package and SHA-1, and Google OAuth test users.
- Google succeeds but Supabase refuses ID token: Google provider disabled, client IDs mismatched, nonce check, or wrong Supabase URL/publishable key.
- Supabase signs in but `GET /api/me` returns 401: ask Backend owner to check ES256 JWKS, issuer, audience, signing key and deployed SUPABASE_URL.
- Backend `503 SERVICE_UNAVAILABLE`: preserve SDK session and retry later; Guest public search remains available.
- Sign-out should clear SDK persisted session even when remote sign-out fails. Do not cache access tokens in app-specific preferences.

## 5. Implementation boundaries / traceability

- New Auth UI is under `ui/auth/`. Existing Search, Bar Detail and Map flows are unchanged other than an optional My Page action and optional bar-menu auth header.
- `CustomerRepository.searchBars` is always public/no auth header. `CustomerRepository.getPublishedBarMenu` sends a valid Supabase JWT when one exists; on UNAUTHENTICATED it refreshes once, then falls back to Guest.
- `/api/me` receives **only** a Supabase access token.
- Auth session storage/refresh is delegated to supabase-kt Auth SDK, not handwritten token persistence.
- Do not claim device E2E or live Google/Supabase account integration passed until the owner runs and records those checks.

Official references:
- https://supabase.com/docs/guides/auth/social-login/auth-google
- https://supabase.com/docs/reference/kotlin/auth-signinwithidtoken
- https://supabase.com/docs/reference/kotlin/auth-onauthstatechange
- https://developer.android.com/identity/sign-in/credential-manager-siwg
