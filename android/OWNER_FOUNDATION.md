# Android Owner Foundation — unified build

Iteration 3 implementation scaffold. Android uses one `debug` or `release` APK without Customer/Developer flavors. Default startup stays `customer`. My Page now links to `owner/entry`.

## Build and tests

```sh
./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

Owner preview navigation:
- `owner/entry` shows explicit status **not implemented / not connected to server**.
- `owner/ux/registration/{html-screen-id}` registration and approval shells.
- `owner/ux/management/{html-view-id}` store/menu/hours/tags/preview shells.
- `owner/ux/photo-review/{html-screen-id}` extraction/review shells.
- `owner/components` tests UI components with local-only values.
- All placeholders state they cannot save, publish, scan or modify data.
- Legacy Developer import routes remain debug-only and are not linked from production Owner UI.

Theme: `DESIGN.md`, `Tokens.kt`, `BmIcon.kt`, `BmLoading.kt`, `ReducedMotion.kt` and Vector Drawable icons from the design branch. Exact Bookk Myungjo and Pretendard fonts require licensed font files (not bundled), so platform font fallbacks are clearly used. The 148 attached bottle silhouette SVGs are product-specific illustration references, not generic UI icons.

Manifest retains portrait-only policy. Existing camera FileProvider, photo-preparation code and regression tests moved into shared main/test sources. Customer search, Kakao map and Supabase Google sign-in are not rewritten.

This is a navigation/component foundation, NOT completed Owner product behavior, API integration, approval, review or publication. Verify CI and physical-device status bars, Back, keyboard, font scaling and both customer and legacy debug routes before merging.
