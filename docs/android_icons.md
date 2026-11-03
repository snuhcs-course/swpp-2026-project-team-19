# BottleMap icons and loading animations (Android)

The app's own icon set: 19 outlined icons and two loading animations, drawn in the style set by `DESIGN.md` section 9 ("Icons and images", "Buttons, loading and feedback"). Colours come from `ui/theme/Tokens.kt`.

| What | Where |
|---|---|
| Vector drawables | `android/app/src/main/res/drawable/ic_bm_*.xml` |
| Fallback line colour | `android/app/src/main/res/values/bm_icon_colors.xml` |
| `BmIcon`, `BmIconId` | `android/app/src/main/java/com/zerotoone/bottlemap/ui/common/BmIcon.kt` |
| `GlassFillLoading`, `IceDropLoading` | `.../ui/common/BmLoading.kt` |
| Reduced-motion check | `.../ui/common/ReducedMotion.kt` |

The icons are not wired into any screen yet. Each screen owner replaces the current text glyphs (`←`, `⌕`, `⌖`) when they work on that screen.

## Icons

All icons are 24 x 24 dp on a 24-unit grid, with a 1.5-unit round outline.

| `BmIconId` | Drawable | Meaning | Intended use |
|---|---|---|---|
| `SEARCH` | `ic_bm_search` | 검색 | Search field leading icon on Home; place search on the nearby map |
| `BACK` | `ic_bm_back` | 뒤로 | Top-bar Back on search results, bar detail, bar location map, account and nearby screens (mirrored in RTL) |
| `MAP` | `ic_bm_map` | 지도 | "지도에서 위치 보기" on bar detail; list/map toggle |
| `BAR_PIN` | `ic_bm_bar_pin` | 바 위치 핀 | Bar marker on the Kakao maps (bar location map, nearby map) |
| `LOCATION` | `ic_bm_location` | 내 위치 | "내 위치로 이동" button and the user-location marker |
| `BAR` | `ic_bm_bar` | 바 상세 | Bar detail header; "상세 보기" entry from the nearby carousel |
| `GLASS` | `ic_bm_glass` | 잔 (글라스) | By-the-glass menu option next to the pour volume (ml) |
| `PRICE` | `ic_bm_price` | 가격 | Price (KRW) in search results and bar menu |
| `UPDATED` | `ic_bm_updated` | 메뉴 갱신일 | Menu updated date (`menuUpdatedAt`) |
| `ACCOUNT` | `ic_bm_account` | 마이페이지 | 마이페이지 entry and account screens |
| `LOGIN` | `ic_bm_login` | 로그인 | Login button. Generic sign-in arrow; it is not the Google mark |
| `RETRY` | `ic_bm_retry` | 다시 시도 | Retry buttons on error states |
| `ERROR` | `ic_bm_error` | 오류 | Error states ("불러오지 못했습니다") |
| `EMPTY` | `ic_bm_empty` | 결과 없음 | Empty results ("검색 결과가 없습니다", "매장이 없습니다") |
| `CAMERA` | `ic_bm_camera` | 메뉴 사진 촬영 | Owner menu upload: take or add a menu photo |
| `REVIEW` | `ic_bm_review` | 검수 필요 | Owner extraction review |
| `PUBLISH` | `ic_bm_publish` | 메뉴 게시 | Owner "confirm and publish" |
| `MANAGE_BAR` | `ic_bm_manage_bar` | 내 바 관리 | Owner home / owner entry (not on `main` yet) |
| `CERTIFICATE` | `ic_bm_certificate` | 사업자등록증 | Owner application: business registration certificate (planned) |

**Pending:** the bottle icon (병 (보틀), for the by-the-bottle menu option and bottle price rows) is not approved yet. It needs design changes and will come in a later PR. Until then those rows have no icon; do not substitute another icon such as `GLASS`.

## Outline and selected states (A/B rule)

DESIGN.md: one outlined icon family; a filled state is used only for selected items. Every drawable has the same two layers:

- `skeleton`: the 1.5 outline (plus `skeleton_dot`, a small filled dot, in `camera` and `error`). This is the icon in every state.
- `accent`: one shape (liquid, lens, label, seal...) that is filled only when the item is selected.

| State | Draw it as | Looks like |
|---|---|---|
| A, default | `BmIcon(BmIconId.MAP, "지도")` | Outline only, in the caller's content colour |
| B, selected | `BmIcon(BmIconId.MAP, "지도", selected = true)` | Same outline plus the accent in `colorScheme.primary` |

Use B only for a selected or active item (a selected tab, toggle or chip), never for decoration, and never mix it with other stroke weights. A loading, error or empty state stays A.

`selected` fades the accent in over `BottleMapMotion.selectionMs` (180 ms), or switches at once when the system has turned animations off. Pass `contentDescription = null` when visible text next to the icon already names it.

A plain `Icon(painterResource(R.drawable.ic_bm_map), contentDescription, tint = ...)` also works and always gives state A, because the accent path is transparent in the XML. Do not try to make state B with a single tint: the tint would paint the accent and the outline in one colour.

## Colours

| Part | Compose source | Tokens.kt value |
|---|---|---|
| Icon outline | `tint` parameter, default `LocalContentColor.current` (`onSurface` inside a `Surface`) | `BottleMapPalette.textPrimary` `#F2EDE8` |
| Icon accent (state B) | `MaterialTheme.colorScheme.primary` | `BottleMapPalette.primary` `#C99D6B` |
| Loader outline and ice | `MaterialTheme.colorScheme.onSurfaceVariant` | `BottleMapPalette.textSecondary` `#C7BBB0` |
| Loader liquid | `MaterialTheme.colorScheme.primary` | `BottleMapPalette.primary` `#C99D6B` |

These values hold once the app theme uses `BottleMapDarkColorScheme`. Until `BottleMapTheme` is switched to it, the components follow whatever colour scheme the theme provides; the `@Preview`s wrap themselves in `BottleMapDarkColorScheme`.

The only XML colour is `@color/bm_icon_line` (`#FFF2EDE8`, equal to `BottleMapPalette.textPrimary`). It is used only when a drawable is drawn without a tint, for example in a View. If `textPrimary` changes in `Tokens.kt`, change it here too.

## Loading animations

```kotlin
DelayedLoading {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        GlassFillLoading()
        Text("메뉴를 읽는 중")
    }
}
```

- `GlassFillLoading`: the whisky level ebbs and rises with a gentle wave (2.0 s loop). `IceDropLoading`: three ice cubes drop in, then fade out (2.4 s loop). Both are 48 dp by default; pass `Modifier.size(...)` to change it.
- Indeterminate only: there is no percentage and no progress value (DESIGN.md 5.2, "no fake progress"). TalkBack hears an indeterminate progress bar, so pair the loader with a short visible label.
- When the system has turned animations off (`Settings.Global.ANIMATOR_DURATION_SCALE` is 0), the glass is drawn as one still frame.
- The loops are slower than the 150/180/240 ms UI motion on purpose. Show and hide the loader with `DelayedLoading` and a `contentTransitionMs` (240 ms) fade.

## Adding or changing an icon

1. Draw it on a 24 x 24 grid with 2 units of padding, a 1.5 round outline (round caps and joins), and at most one accent shape. Keep the corner radii (about 1.5 to 2.5) and the level of detail of the existing icons. Do not trace or copy icons from another set or from a brand mark.
2. Write `res/drawable/ic_bm_<name>.xml` with top-level `<path>` elements only (no `<group>`, `<clip-path>` or gradients): a `skeleton` path with `android:strokeColor="@color/bm_icon_line"`, `android:strokeWidth="1.5"`, round cap and join and a transparent fill; optionally a `skeleton_dot` path filled with `@color/bm_icon_line`; and an `accent` path with `android:fillColor="#00000000"`. `BmIcon` recognises the layers by these `android:name` values. Circles and rounded rectangles have to be written as path data (arcs are fine).
3. Add an entry to `BmIconId` and a row to the table above.
4. Check both states in the `BmIconSetPreview` preview at 24 dp and 48 dp.

## Origin and licence

The 19 icons and the two loading animations were drawn for BottleMap in this project (Jinwoo Park, October 2026). The path data was written by hand on the 24-unit grid; no icon set or brand artwork was copied.

To check this, the icons were compared with Lucide 0.460.0 (ISC), Tabler Icons 3.24.0 outline (MIT), Feather 4.29.2 (MIT), Phosphor 2.1.1 regular (MIT), Heroicons 2.2.0 outline (MIT) and Iconoir 7.10.1 regular (MIT), by shared vertices and by rendered overlap. No BottleMap icon shares more than half of its vertices with any icon in those sets. Some icons are universal symbols and therefore look like their counterparts in every set (back arrow, folded map, crosshair location, exclamation circle, camera). The closest are `location`, which has the same ring and tick span as Lucide `locate-fixed`, and `map`, which has the same folded-map outline as Tabler `map`; the coordinates differ. All of those sets are under permissive licences, so even a stricter reading would require only an attribution notice.
