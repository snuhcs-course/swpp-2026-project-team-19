# BottleMap I2-P25 / I2-A6 — Kakao Maps Android setup

The app embeds the official **KakaoMaps SDK v2 for Android, 2.15.2** (not a WebView or external maps app).

## Local credentials (never commit actual values)

1. In [Kakao Developers](https://developers.kakao.com/), create or select the BottleMap app and enable Kakao Map.
2. Register the Android package **`com.zerotoone.bottlemap`** and the **signing certificate key hash** for the APK being tested. Debug and release builds may have different key hashes.
3. Copy the **Native App Key** (not REST API or JavaScript key).
4. Store it in your personal **`%USERPROFILE%\.gradle\gradle.properties`**, outside the repository:

   ```properties
   BOTTLEMAP_KAKAO_NATIVE_APP_KEY=REPLACE_WITH_YOUR_NATIVE_APP_KEY
   ```

5. Keep the backend URL in your existing local Gradle configuration, or explicitly pass it on the command line. Example from repository root:

   ```powershell
   .\gradlew.bat :app:testDebugUnitTest :app:assembleDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
   .\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
   ```

   The Native App Key is compiled into `BuildConfig`; **package and certificate key-hash restrictions are mandatory**. Never commit it, paste it into a PR, or attach it in build logs.

6. If the map fails to authenticate, verify package, key hash and key type, then inspect Android Studio Logcat filtered with `k3f` / `BottleMapKakao`.

## Device ABI

Official SDK supports **armeabi-v7a / arm64-v8a**, **OpenGL ES 2.0+**, **Android API 23+**. The project has minSdk 26. An x86_64-only Android emulator may fail to load Kakao's native map engine.

Use an **ARM64 physical Android device** for definitive E2E verification. Check connected device ABI:

```powershell
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $adb devices
& $adb shell getprop ro.product.cpu.abi
```

## Verification checklist

- [ ] `testDebugUnitTest` passes (coordinate validation and existing search/bar-detail regression).
- [ ] `assembleDebug` succeeds, with the SDK dependency resolved.
- [ ] Actual installed ARM device shows a Kakao vector map inside BottleMap.
- [ ] Search result -> bar detail -> Kakao map -> Back -> detail -> Back -> search results.
- [ ] Marker/name correspond to the **same barId** and the coordinates returned from `GET /api/bars/{barId}/menu`.
- [ ] Selecting a different bar creates a marker at the different backend location.
- [ ] Failed map authentication/network initialization shows an error and Retry.
- [ ] Invalid/missing latitude or longitude never opens a fabricated map location.
- [ ] Bar detail and prior search results are preserved on normal Back.
- [ ] No owner, Google login, nearby 500m or carousel feature is changed.

## API contract / design notes

- Backend `latitude`, `longitude`: **required, non-null** numeric fields under the current 3.9 contract. Null/missing fields violate the contract and cause DTO parsing error; frontend must not synthesize a replacement.
- UI model validates ranges and rejects non-finite values, missing data, and `0,0` placeholder.
- Kakao `LatLng.from(latitude, longitude)` receives **latitude first**.
- The Map destination shares the existing Bar Detail `ViewModel` using the Navigation back stack entry; no extra bar-menu fetch on normal map entry.
- Label-based native map marker is keyed by `barId`; the single-marker implementation leaves a straightforward path to A7/A8 multi-marker support.
- The I2 Figma's **schematic map** is replaced by the actual Kakao SDK view, not shipped as a static bitmap.

Official references:

- https://apis.map.kakao.com/android_v2/docs/getting-started/quickstart/
- https://apis.map.kakao.com/android_v2/docs/getting-started/precautions/
- https://apis.map.kakao.com/android_v2/docs/api-guide/label/label/
- https://apis.map.kakao.com/android_v2/sample/
