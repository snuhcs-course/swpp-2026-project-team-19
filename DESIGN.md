# BottleMap Design System - Guided Minimal / Cocoa Charcoal

> Status: **Design system v1.0 final — frontend design baseline (2026-10-27)**. Visual choices marked **USER-APPROVED** were approved by the frontend owner after the interactive prototype review. **PROPOSED** values are defaults rather than mandatory product requirements. Real-device/build QA remains pending. Approval by the frontend owner does not imply team acceptance of changes to MVP requirements or API contracts.
>
> Target: Android, Jetpack Compose, Material 3. Primary language for customer-facing copy: Korean. This file is a reusable visual/interaction contract, **not** an API or product-scope amendment.
>
> Companion implementation: `Tokens.kt`, package `com.zerotoone.bottlemap.ui.theme` (verify the current repository path first).

## 0. Source priority, decision labels and agent requirements

1. Current team requirements and accepted API contracts override design proposals; approved screen specifications control exact layout. Never silently modify a requirement to suit this guide.
2. **USER-APPROVED visual direction:** Guided Minimal; dark-first; Cocoa Charcoal colors; mixed **Bookk Myungjo (large screen/display headings only) + Pretendard (all utilitarian UI)**; balanced density; medium rounding; restrained brown/amber emphasis; outlined icons; subtle motion; minimal Korean copy; no meaningless English.
3. **USER-APPROVED flow proposal:** **Home -> Product selection (skip only on a unique exact canonical product match) -> Confirmed canonical product results -> Map / Bar detail**. This replaces the earlier 'brand-wide All products + product chips inside results' proposal. This navigation change requires corresponding team wireframe/requirements update before release.
4. **USER-APPROVED card structure:** bar name, distance if known, **1–2 verified feature tags if available**, price+exact volume inline (price first), a compact representative bar photo (if available), menu update date when available. No volume expansion in search results.
5. **USER-APPROVED map marker direction:** roomier bubble, photo **left**, two tightly spaced lines **right**: bar name first and representative price+volume second; image slightly taller than the combined two text lines. If the map is bar-only exploration, do not show a product price.
6. **USER-APPROVED interaction:** default distance sort if location available; sort chooser is a dropdown; feature tag filters allow multi-selection if data exists. **Multiple selected tags use OR** (a bar with any selected tag matches); exact placement, dropdown option copy and individual component sizes are **SCREEN-SPEC** decisions.
7. **CONTRACT CHECK REQUIRED:** current reviewed API draft exposes canonical matched products, one row per bar x product and actual menu options. It does **not** establish customer-facing bar photo URLs, structured feature tags or customer-facing bottle illustration assets. These must be backed by an agreed interface before production UI; use labeled mock data in previews only. Do not interpret menu-upload photo URLs as public bar representative photos.
8. For each implementation, record requirement, source API/DTO, UI states, navigation, loading/empty/error/retry behavior and test results; do not invent `barImageUrl`, `tags`, `productArtworkUrl`, or new search endpoints.
9. Avoid local ad hoc visual constants: apply semantic token values through shared components. Screen-specific exceptions require documentation.

### Reference influence (not literal copying)

- Toss: clear next action, questions as concise screen titles, immediate feedback, accurate owner/operator step progression.
- Yeogiotte: synchronized list/map selection and a photo + place identity cue.
- Baemin: optional details appear on demand rather than being expanded by default.
- Danggeun: clear outlined icons, accessible Korean labels.
- Spotify: discoverability, not a compulsory content-heavy feed or multicolored dark UI.

## 1. Experience principles and information hierarchy

**Principle: Clarity first, detail on demand.** Each surface should answer the next useful user question, not display every piece of data available.

- **Home:** 'What drink should I search for?' or 'Explore bars on a map'. Do not recreate a lengthy recommendation feed.
- **Product selection (when ambiguous):** 'Which exact drink did you mean?' Display the API-provided canonical product name and a small coherent bottle illustration; show only legitimate matched catalog products. For a single exact canonical product match, proceed directly to that product's results.
- **Confirmed-product results:** 'Where can I drink this? What is the real representative price and size? What kind of place is it?' Use a compact card with bar image and at most 1–2 feature tags when sourced.
- **Map:** 'Where is that bar?' Keep its name primary. Prices are secondary to place identity, only in a product-specific context.
- **Bar detail:** 'What other serving sizes are available and what are their actual prices?' Show the full published menu rather than multiplying result-card rows.
- **Owner/operator:** 'What step am I in and what must I do next?' Show truthful progress with Back/recovery routes.

Keep long marketing descriptions, redundant helper paragraphs, repetitive labels, unnecessary nested cards and decorative photography out of the default view. Focus on one primary task per screen; provide details through meaningful navigation, not indiscriminate scrolling.

## 2. Color system — approved Cocoa Charcoal

The following HEX values were **USER-APPROVED in the interactive HTML review**. They are the exact visual baseline; **device contrast, sunlight/bright-map legibility and platform rendering still require QA**.

| Semantic role / Kotlin token | HEX | Status | Purpose |
|---|---|---|---|
| `background` / `BottleMapPalette.canvas` | `#211E1B` | USER-APPROVED | Page canvas, avoid generic pure black |
| `surface` | `#302B27` | USER-APPROVED | Card/input/sheet surfaces |
| `surfaceElevated` | `#3A332E` | USER-APPROVED | Selected/raised areas |
| `primary` | `#C99D6B` | USER-APPROVED | Sparing actions, selection, prices when appropriate |
| `onPrimary` | `#211A14` | USER-APPROVED | Primary button foreground |
| `onSurface` / `textPrimary` | `#F2EDE8` | USER-APPROVED | Main copy |
| `onSurfaceVariant` / `textSecondary` | `#C7BBB0` | USER-APPROVED | Secondary copy |
| `outlineVariant` | `#51473F` | USER-APPROVED | Quiet borders / dividers |
| `surfaceVariant` | `#403832` | PROPOSED | Quiet chips, control fills |
| `outline` | `#786A60` | PROPOSED | High-importance focus boundary |
| `error` / `success` | `#FFB4AB` / `#B9DFC8` | PROPOSED | Semantic status only |

- Don't add new accent colors per card, drink or tag. Feature tags should look like neutral metadata, not a colored badge wall.
- The marker on a bright map needs sufficient contrast and a visible silhouette; don't apply a dark tint to the actual map tiles.
- Check **WCAG AA** text contrast (normal 4.5:1, large 3:1), including text on marker and selected chips. Decorative images are not substitutes for alt/semantics.
- Dark-first is approved; full light palette, dynamic colors and system theme switching are deferred. Use `MaterialTheme.colorScheme` so these can be added without changing feature screens.

## 3. Typography — mixed families, approved reviewed sizes

**USER-APPROVED:** **Bookk Myungjo for large display/screen headline roles only**, **Pretendard for bar names, product names, prices, volume, filters, buttons, markers, forms, owner steps, captions and body copy**. Do not apply the serif to small metadata or currency. A screen title should remain readable and may wrap naturally; use font roles rather than per-screen family overrides.

| Semantic role | Size | Weight | Proposed line height | Family | Status |
|---|---:|---|---:|---|---|
| `display` | 28sp | Bold | 36sp | Bookk Myungjo | PROPOSED size |
| `screenTitle` | **24sp** | Bold | 32sp | **Bookk Myungjo** | USER-APPROVED size/family |
| `sectionTitle` | 20sp | SemiBold | 28sp | Pretendard | PROPOSED |
| `cardTitle` | **16sp** | SemiBold | 23sp | Pretendard | USER-APPROVED size |
| `body` | 16sp | Normal | 24sp | Pretendard | PROPOSED |
| `label` | 14sp | Medium | 20sp | Pretendard | PROPOSED |
| `caption` / menu date | **12sp** | Normal | 18sp | Pretendard | USER-APPROVED size |
| `price` | **16sp** | SemiBold | 23sp | Pretendard | USER-APPROVED size |
| `pourAmount` | 13sp | Medium | 20sp | Pretendard | PROPOSED |
| `markerLabel` | **12sp** | SemiBold | 16sp | Pretendard | Web prototype was 12px; 12sp Android starting point |
| `markerPrice` | **12sp** | Medium | 16sp | Pretendard | PROPOSED |
| `unitRate` | 12sp | Normal | 16sp | Pretendard | Optional supporting explanation |

- `sp` is mandatory in Android; the browser's 12px marker preview is not proof of pixel-identical Android text. Validate on devices with font scaling.
- Pair representative amount **before** its actual size, e.g. `17,000원  30ml`, in one accessible inline group. If wrapping is unavoidable at larger text scales, preserve price-first semantic reading order.
- Bookk Myungjo is available as Light/Bold; don't synthesize unsupported intermediate weights or alter original font files. Obtain licensed app-compatible font resources; verify license at implementation. **Do not bundle/distribute font binaries in generated design documents.**
- Compose role mapping: `display` -> `displaySmall`, **`screenTitle` -> `headlineSmall` (24sp only; do not use `headlineMedium` as an alias)**, `sectionTitle` -> `titleLarge`, `cardTitle` -> `titleMedium`, `body` -> `bodyLarge`, `label` -> `labelLarge`, `caption` -> `bodySmall`. Custom `price`/`pourAmount`/`marker` styles live alongside Material 3 typography in `Tokens.kt`.

## 4. Spacing, sizing and component architecture

**PROPOSED 4dp scale**: 4, 8, 12, 16, 20, 24, 32, 40dp. Reuse `BottleMapSpacing`; do not invent arbitrary local values.

| Meaning | Token | Initial value | Status |
|---|---|---:|---|
| Screen horizontal padding | `screenHorizontal` | 20dp | PROPOSED |
| Section separation | `sectionGap` | 24dp | PROPOSED |
| Card interior | `cardPadding` | 16dp | PROPOSED |
| Card corner | `BottleMapRadii.large` | 16dp | PROPOSED |
| Input/button corner | `BottleMapRadii.medium` | 12dp | PROPOSED |
| Button min height | `BottleMapSizes.primaryButtonMinHeight` | 56dp | PROPOSED |
| Touch targets | `minTouchTarget` | >=48dp each axis | ACCESSIBILITY REQUIREMENT |
| Bar representative photo | `barCardThumbnail` | **64dp square** | PROPOSED compact example |
| Map marker representative photo | `mapMarkerPhoto` | **38dp square** | PROPOSED; slightly taller than two text lines |
| Map marker title/body separation | `mapMarkerTextGap` | **2dp** | PROPOSED compact vertical rhythm |

Keep fixed dimensions for thumbnails, **not for the height of text-based cards**. Respect system font scale and dynamic wrapping. Prefer quiet separators to nested cards. Avoid unnecessary horizontal scrolling. Observe status/navigation safe areas, keyboard IME and landscape constraints.

### Reusable components (outside `Tokens.kt`)

`BottleMapSearchField`, `ProductChoiceRow`, `BottleIllustration`, `BarResultCard`, `BarImage`, `FeatureTagChip`, `SortDropdown`, `PriceSizePair`, `BarMapMarker`, `BarMenuProduct`, `StepProgress`, `LoadingEmptyError`.

`Tokens.kt` is a collection of reusable **visual values**, not DTOs, ViewModels or full Composables. All components should take semantic inputs rather than fabricated API field names.

## 5. Navigation and flow contract

### 5.1 Customer flow — USER-APPROVED UX proposal

```text
Home (search or bar-first map exploration)
  -> ProductSearch(query)
      |-- unique exact canonical match -> ConfirmedProductResults(productId)
      `-- ambiguous brand/partial/multiple match -> ProductSelection(matchedProducts)
              `-> ConfirmedProductResults(productId)
                  |-> list <-> map (same selected product, sort, filters)
                  `-> BarDetail(barId, highlighted productId when available)
```

- **No brand-wide bar result listing** and no `All products` product filter in the final results screen. A brand query such as `글렌피딕` first yields canonical candidates such as the 12y and 15y entries; the user chooses one **before** seeing bar prices. **USER-APPROVED:** if the search resolves to exactly one unambiguous *exact product* (e.g., the reviewed API draft reports `matchType = alias_exact` and `matchedProducts.size == 1`), **skip ProductSelection** and show that product's bar results. One candidate returned by `partial` alone does not qualify as exact.
- Use the existing `GET /api/search/bars?query=...` draft response `matchType`, `matchedProducts[]` and `items[]`: unique exact-match bypass or candidate selection sets one canonical `productId`, then **filters previously returned rows by `productId` in frontend UI state**, or follows a separately agreed query route. Do **not** invent a productId backend query parameter. If the original response is truncated, the filtered list may be incomplete; keep the contract risk explicit.
- A unique exact match must still resolve to a canonical `productId` before results are shown; ambiguous/brand/partial matches retain ProductSelection. If `matchedProducts[]` is empty, show unrecognized; if the confirmed candidate has no serving `items`, show known-but-no-bars. **Exact-skip is a frontend UX decision, not a new API field or endpoint.**
- `resultCount` can be displayed only if it is actually returned. `truncated=true` must not be hidden: a truncated search means the local filtered rows may not represent all selling bars, especially if the backend limit was reached. Treat potential truncation as a data-contract risk and coordinate with backend before shipping complete-coverage claims.
- In results screen, compare one canonical product across bars. Default sort by known distance; user may choose **price per 1ml** in a **sort dropdown**. No ambiguous brand-wide price sorting.
- Preserve product selection, sort, tag filter and selected bar between list and map. Android Back returns to product selection and preserves query; search new query resets stale result filters.
- A separate root-level Map tab is **not** required. Home's bar-first map entry remains available; bar-first map shows bar identity without arbitrary product prices.

### 5.2 Owner/operator task flow

- Screen spec for the owner menu flow (photo upload, reading, line-by-line review, publish): `docs/owner_menu_flow_ux.md` (I3-P25).
- Use Toss-like clearly named ordered steps for upload -> processing -> review -> publishing only according to team-accepted workflow. Do not show invented percentages for indeterminate OCR/AI work.
- Keep Back/retry and restore inputs across Android lifecycle/configuration changes.
- Owner screens may use denser operational data than customer Explore screens; do not force a one-question-one-screen rule on reviews.

### 5.3 Responsibilities and approval boundary

This is **USER-APPROVED frontend UX**, not evidence that team requirements/wireframes were updated. The Oct 2026 requirements still describe search as proceeding to bar results without an explicit mandatory product-choice screen. Record this change request and get team agreement before treating it as MVP acceptance criteria.

## 6. Search, product choice and results

### 6.1 Current reviewed API surface (not a new contract)

- Draft public search endpoint: `GET /api/search/bars?query=...&lat=...&lng=...` with optional coordinates; `matchType`, `matchedProducts[]`, `items[]` (bar x product), actual `options[]`, `menuUpdatedAt`, optional distance, `truncated`.
- Draft public detail endpoint: `GET /api/bars/{barId}/menu`; provides the published menu and its serving options.
- **Not established:** public bar representative-photo URLs, structured bar feature tags, their allowed vocabulary and moderation, customer product bottle illustration images. The preview must mark such content as mock until contract/data are agreed.

### 6.2 ProductSelection screen

- One canonical product per tappable row; **use `matchedProducts[].displayName` from the current API as the product name** (do not invent Korean/English translations), with a **small deterministic stylized bottle illustration at left**. Optionally show age/edition and actual selling-bar count when available; no artificial 'popular' ranking or photo carousel.
- Bottle illustration is **an abstract visual aid**, not a product photograph or promise of exact bottle appearance. See Section 10 for construction rules. Tap target >=48dp; keyboard and screen reader identify the product by text, not bottle shape alone.
- Product-selection list handles query loading, ambiguous alias/brand/partial response, no recognized product, recognized product with zero bars, server failure/retry and extremely long product names. **Skip this list only for one exact canonical product match**; do not auto-skip based solely on `matchedProducts.size == 1`.
- Selecting a product fixes canonical `productId` before sorting/list/map; no `All` state in results. The correct product must never change because a map/list filter is toggled.

### 6.3 Representative serving option — USER-APPROVED

For each `(barId, productId)` choose from **actually published valid** `options[]`:

1. Prefer exactly **30ml**.
2. Otherwise choose `abs(pourMl - 30)` smallest.
3. On equal distance choose **larger pourMl**.
4. **PROPOSED deterministic tie-breaker:** when the same size appears more than once, choose the lowest actual `priceKrw`, then `sortOrder`, while preserving `optionLabel` in bar detail.
5. Invalid, absent or zero `pourMl`/`priceKrw`: don't invent a unit rate or a free price; show a truthful unavailable state and sort these after valid rates.

Representative != cheapest total price != cheapest KRW/ml. Never label the representative price '최저가' or '부터' unless validated separately.

### 6.4 Results screen sorting and tags

- **USER-APPROVED:** a **sort dropdown**, default **distance ascending** if meaningful location is available; no location -> don't label as nearest, instead preserve backend's contracted default and show appropriate fallback description.
- **USER-APPROVED:** price sort uses `priceKrw / pourMl` of the **representative option**, ascending; use precise values in comparator and round only for optional displayed explanatory rate. Price+volume always shows **real payable amount and actual volume**.
- **USER-APPROVED:** feature tags allow **multiple selections with OR semantics**: with no tag selected, display all eligible bars; with one or more tags selected, display bars containing **at least one** selected tag. Up to **two relevant sourced tags** appear on a default result card. Final vocabulary, number of filter chips and filter placement are **SCREEN-SPEC/PENDING DATA CONTRACT** decisions, not approved API fields.
- A tag must mean a verified characteristic. Do not infer '좋은 안주', '분위기', '친절함', '가성비' from a photo or a menu name. Without trustworthy tag fields, **hide tag filters and tags in production**, but mock in a clearly labeled demo.
- Stable price-sort tie-breakers **PROPOSED**: distance if available, bar name, bar ID; invalid rate at end. Keep dropdown selection across list/map mode switch.

### 6.5 Result card: information contract

```text
BarResultCard (ONE confirmed productId per result screen)
|-- text column
|   |-- bar name (PRIMARY)  + known distance
|   |-- feature tags (max 2, ONLY if real data exists)
|   |-- actual representative price + actual pour volume (inline, PRICE FIRST)
|   `-- menu updated date (menuUpdatedAt, short secondary copy)
|-- representative bar photo (RIGHT, compact; or graphic placeholder)
`-- one clear bar-detail action via card/affordance
```

- No per-product/volume expansion in results: one confirmed product, one representative real option **per bar**. `Show more drinks` is no longer part of the customer search results because product selection precedes the result page.
- **User feedback:** reduce bar-card image slightly, close excess vertical gaps between tags and price, remove the redundant generic helper phrase '메뉴 가격은 실제 등록 정보 기준 표시' and instead show the actual **menu update date** in the metadata area. Do not show a date if it is missing.
- **PROPOSED** image size 64dp square, aligned in a right-hand image slot. Name and distance must remain readable when image is missing, loading, broken, or restricted. Photos must be permitted/approved and actually associated with that bar.
- Keep bar cards compact but ensure no clipped text on font scaling. If a name wraps or the tags overflow, priority is **name -> price+volume -> distance -> tags -> update date**. Optional tags may wrap/hide but never hide the real serving amount.
- No dense paragraph blocks, fake amenities, thumbnail-driven disappearance of price or multiple primary CTAs.

### 6.6 Price + volume presentation

- Standard reading order: **`17,000원` then `30ml`**, same horizontal cluster, `price = 16sp` approved, `pourAmount = 13sp` proposed.
- At larger font scales permit price above volume while preserving reading order and shared semantics. Do not display price alone, or imply the selected 30ml is lowest total price.
- `1ml당 가격` is an optional secondary *comparison metric*, never a purchasable price. Card default does not need to show it; the dropdown label should explain the sort criterion.

## 7. Bar detail and published menu

- Public `GET /api/bars/{barId}/menu` drives identity and menu fields already defined in the reviewed API draft. From results, highlight the confirmed product where helpful; do not hide other published menu products in the bar detail.
- All actual price/size `options[]` belong here grouped by product, with **price first, volume second** and `optionLabel` when needed. Respect `sortOrder`; do not merge two equally sized yet differently priced/labeled options.
- The representative 30ml/nearest option can be spotlighted, but bar detail must expose the entire list. Per-product collapse/expand is an optional layout choice for long menus, not a way to hide availability.
- Show `publishedAt` only if known. No menu -> explicit empty; network fail -> retry; avoid suggesting a bar carries a product that does not exist in the current published menu.
- Bar representative photo and feature tags are **conditional UI concepts**, not fields in the checked public menu response. Only bind them after interface acceptance; otherwise use safe placeholders and omit unverifiable tags.

## 8. Map marker and map/list interaction

**USER-APPROVED marker layout: roomier bubble with photo at left, two compact right-aligned content lines.**

```text
+----------------------------------------------+
| [bar photo]   bar name (primary)              |
| [  38dp  ]   17,000원  30ml (secondary)        |
+----------------------------------------------+
```

- Structure: photo **left**; name and price/size stack **right**, with minimal vertical text gap (`mapMarkerTextGap`, proposed 2dp). Image height should be just greater than combined line block. Name is visually and semantically higher priority than price. Provide a text alternative when the image is unavailable.
- **USER-APPROVED** `markerStyle=bubble`, `markerFont` from web prototype **12px** -> Android **12sp starting point**, and `roomy` density rather than packed labels. No crowded three-line captions or multiple tag chips inside the marker.
- At a confirmed-product map: name first, representative real price and volume second. At a bar-first map without selected product: name (and optional distance), **no invented drink price**.
- Marker selection must update the same selected bar detail/preview as list; one marker per `barId`. Sort and multi-tag filter state carries across list/map; if filters remove the selected bar, clear or update selection consistently.
- If markers overlap, cluster/declutter without hiding the selected bar's identity. Do not cover map attribution or system gesture areas. **48dp minimum interactive target** even where visual marker is smaller.
- Selected, default, inaccessible-photo, no-location, map-loading, map-error, empty results and retry states should be tested; don't rely on color alone to communicate selection.
- Marker exact width, photo crop and bottom-sheet gesture thresholds remain **SCREEN-SPEC** decisions; token candidate photo is 38dp.

## 9. Shared component behavior

### Search field and product candidates
- Obvious search affordance and Korean accessible label; states: idle/focus/editing/submitting/success/no-match/error/retry. Trim query, 1–100 characters per reviewed API draft; preserve keyboard/back/navigation state appropriately.
- Product choice rows must show text identity even with a decorative bottle illustration; matched-product list may be derived from a search result without inventing an autocomplete endpoint.
- Recent/popular queries are not automatically implemented without actual data and feature approval.

### Sort dropdown
- Use a single trigger with current sort label; menu contains only actually supported choices. Don't imply '가까운 순' without location; label unit-rate sorting unambiguously.
- Selected state and keyboard/TalkBack semantics explicit; avoid placing the dropdown where it obstructs the product title or primary result count.

### Multi-select feature tags
- Chip has selected/unselected/pressed/disabled/clear states; selected tags remain visible after scrolling and after list/map transitions.
- Use **OR filtering** for multiple selected tags (any selected tag matches); clear all tags restores all eligible results. If matching results become empty, offer a clear-filters action. **Without backend-supported/verifiable tags, hide this control in production**; demo-only tags must be labeled as sample.
- Max 1–2 sourced tags inside each bar card to protect image and price space. The filter control can expose more categories via user action; never display a wall of badge-like decoration.

### Buttons, loading and feedback
- >=48dp interaction targets; >=56dp proposed main CTA. Distinguish hierarchy without multiple equally prominent buttons. Loading prevents duplicates; errors preserve user input, explain recovery and have Retry.
- Owner step indicator shows accurate current/total steps only when known; no fictional OCR/AI progress percentages. Don't claim automatic publication if review/confirmation is required.
- Subtle motion: tap ~150ms, selection ~180ms, transitions ~240ms **PROPOSED**; respect reduced-motion/accessibility settings.

### Icons and images
- One outlined icon family; filled state may be used for selected items, but not alongside unrelated stroke weights.
- Bar photo is **an informative image** (bar identity / ambience). Provide alt/semantics where meaningful and placeholder on missing/failure; don't fetch public photos from short-lived operator menu-upload URLs.
- Bottle illustration is **decorative adjunct** with canonical text alongside; see Section 10.

## 10. Bottle illustration visual language (product choice)

Derived from the uploaded concept: **rule-based silhouettes**, not hand-drawn photorealistic bottles. Build a compact static illustration renderer, not a generated image per catalog item.

- Use a **small fixed vocabulary** (initial proposal: ~5 silhouette forms, ~6 muted label colors and 3 semantic text-density levels: L detail, M brand initial, S plain silhouette). Do not reproduce real brand logos, trademarks, product label photography or proprietary artwork as exact replicas without rights.
- Identity rule **PROPOSED**: brand canonical ID controls stable silhouette + label palette; age/edition affects **only short label text** when available. One brand should maintain recognizable style as catalog items are added. Do not infer canonical IDs from display names.
- Brand/age/edition metadata must originate from an accepted catalog contract. If missing, use a generic neutral bottle; never invent age or edition. Font on the tiny bottle label may be illustrative, but accessibility name is **the adjacent canonical product text**.
- Use three **explicit visual bounding boxes (width x height)**, all **PROPOSED**: **L 40 x 64dp** for an optional detail/selection showcase, **M 24 x 38dp** in a product choice row (default), **S 16 x 24dp** for dense lists. The prior ambiguous `38dp` means **M height**, not width. Render the silhouette inside its bounding box without stretching; these are visual dimensions, not touch targets. The containing row/marker stays at least 48dp touchable; text takes precedence.
- Keep no photographic textures, glass highlights or detailed whiskey amber effects. Provide accessible outline for contrast against Cocoa Charcoal.
- **Future product category readiness:** a bottle motif applies to bottled alcoholic drinks only; do not globally force whisky silhouettes on all unrelated navigation icons.

### Art direction vs data contract

Illustration style is **USER-APPROVED concept direction**, but the mapping from product metadata to a particular silhouette/color is **PROPOSED** and belongs in a separate graphic/component module. `Tokens.kt` owns only sizes, neutral illustration ink and label-palette values. It must not contain `brandId` lookups or per-product business logic.

## 11. Accessibility, localization and QA

- Korean concise copy by default; no decorative English, duplicate explanatory text or false confidence claims.
- >=48dp actionable touch regions, plus TalkBack labels for candidate bottles (via adjacent product), photo placeholders, tag multi-select states, dropdown, map markers and expanded menus.
- Font sizes defined in `sp`; test 1.0x, 1.3x and larger where available. No fixed-height clipping; safe areas, IME/search keyboard, device rotations and network failures considered.
- TalkBack price order: product -> actual price -> actual volume -> optional comparison rate -> action. For map markers: bar name -> actual price/volume (if chosen) -> open bar.
- Display correct number and currency formatting for Korean locale; source values remain numeric, not strings in DTO.
- Verify at least WCAG AA text contrast on surfaces and map overlays; no color-only distinction.
- Photo availability and tag metadata are optional states. Broken/absent assets must not break the result card or marker.

## 12. Tests and Definition of Done

| Case | Required behavior |
|---|---|
| Search `글렌피딕` (brand/multiple products) | Product selection list displays distinct canonical 12y, 15y, etc. from real `matchedProducts[]`; **no bar list yet** |
| Unique exact product search (`matchType=alias_exact`, one canonical match) | Skip selection and show only that product's results; brand/partial/ambiguous matches do not auto-skip |
| Confirm `글렌피딕 12년` | Only bars with selected canonical `productId` shown; selected product remains fixed in list and map |
| Product recognized; zero selling bars | Separate no-bars state (not unknown-product) |
| Unknown query | Explicit unknown-product state and retry/edit path |
| API returns truncated rows | Don't promise exhaustive bars; integration issue flagged |
| Multiple sizes 15/30/45ml | Result card displays only **30ml** actual price; bar detail exposes **all** options |
| No 30ml; 15/45ml | Representative is 45ml (equal distance -> larger) |
| No 30ml; 20/40/60ml | Representative is 40ml |
| Same size with different `optionLabel` | Preserve detail rows; deterministic representative selection documented |
| Sort dropdown: distance | Ascending valid distance when available; no-location fallback does not claim 'nearest' |
| Sort dropdown: unit price | Ascending exact `priceKrw / pourMl` from representative option; visible card price remains actual pay amount |
| Tags select two filters | Apply **OR** (either selected tag matches), show multiple selected states; clearing restores unfiltered candidates |
| No public tag/photo data | Tags/filter hidden, photo placeholder, no fake amenity or photo |
| Card with long name, 2 tags and photo | Name and real price/size remain legible; menu date shown only if known |
| Map marker with photo | Image left; title above price+ml at right; selected/readable; 48dp touch |
| Bar-only map | Bar identity shown, no unselected-product price |
| Font scaling/TalkBack | Mixed font titles readable; price/size announced correctly; marker not clipped |
| Search/map/bar detail loading and network error | Loading/empty/error/retry; query and selection retained when appropriate |
| Owner processing progress | Accurate step, no fabricated percent; Back/retry doesn't destroy user work |

**Done for a design-token baseline** = this document and `Tokens.kt` share the same approved values/names and can guide implementation without further global design decisions. **Not yet done for shipped Android** = licensed font assets are integrated, screens approved, backend media/tag contract checked, current Gradle repository builds, screenshot QA passes S22/S23.

## 13. Decisions, open integration dependencies and scope boundaries

### User-approved in design review (2026-10-27)

- Cocoa Charcoal exact 8 primary HEX roles; dark-first.
- Mixed typography: Bookk Myungjo in prominent screen/display titles, Pretendard elsewhere. Approved sizes: screen title 24sp, card title 16sp, price 16sp, caption 12sp; marker 12px HTML reference -> 12sp Android candidate.
- Customer flow **home -> choose canonical product (bypass for a single exact match) -> product-specific bar results -> map / bar detail**.
- Search result card shows name, known distance, sourced 1–2 feature tags, **representative actual price + volume**, compact bar image and actual menu update date; result screen does not expand sizes or other products.
- Sort dropdown (distance by default; representative price per 1ml after product confirmed); **OR-based multi-select** feature-tag UI contingent on trustworthy data.
- Map marker: roomy bubble, bar photo left, bar name on right above price+volume with small line gap; confirmed-product vs bar-only map state differentiation.
- Illustrated bottle choices: small, coherent icon-like silhouettes derived from structured metadata, not realistic photos or copied logos.

### Proposed defaults (changeable during individual screen implementation)

- `64dp` card thumbnail, `38dp` map thumbnail, `2dp` map lines gap, card spacing/radii, display/section/body line heights, bottle illustration palette/form mapping.
- Equal-size representative option tie-break, exact sort dropdown option labels and placement, photo crop, marker bubble dimensions and collision/clustering. **Tag OR semantics are approved, not proposed.**

### External acceptance needed, but **not** more global design input

- Conditional product-selection step and exact-product bypass vs current team requirements/wireframe must be approved and documented.
- Public bar image/tag contracts and source/moderation policy remain **team/backend decisions**; this guide specifies only optional visual behavior, not endpoint shapes or tag vocabulary. Current reviewed API draft does not supply these fields.
- Real font resources and license verification; Android project tree/Gradle compilation; accessible on-device screenshots.
- Full light theme, future broader alcohol categories and any accessory recommendation features are outside this v1.0 baseline.

## 14. Agent implementation workflow

1. Inspect newest team requirements, current API, actual repo theme and Android Baseline; state conflicts rather than pretending they do not exist.
2. Set `MaterialTheme` with `BottleMapDarkColorScheme` and `bottleMapTypography(fontFamily = pretendard, headingFontFamily = bookkMyungjo)`. Do not ship with default font placeholders.
3. Implement reusable components in small increments; first `PriceSizePair` + `ProductChoiceRow`, then `BarResultCard` with optional media/tags, then `BarMapMarker` and `BarMenuProduct`.
4. Keep query -> matchType / matchedProducts -> **exact-match bypass or product selection** -> selected `productId` -> filtered bar rows -> representative option -> sort -> **OR-based** tag filter in a ViewModel/state layer; keep DTOs faithful to current contract. **Never** put this code in `Tokens.kt`.
5. For unfinished backend media/tag support, create separate **explicit mock interfaces** and states; show no invented production data when feature is not delivered.
6. Make one source-of-truth UI state shared by result list and map; verify Back, orientation, font scale, filtering, sorting and error/retry.
7. Validate screenshot/design differences on Galaxy S22/S23 and test `assembleDebug`. Keep exact sizes and individual screen prose editable through normal review rather than expanding global tokens for every pixel.

## 15. Sources, scope and provenance

- User-approved design brief, 2026-10-27 final exact-product bypass and tag-OR decisions, and follow-up decisions in project discussion, October 2026.
- Uploaded Claude reference artifact `BottleMap design draft.html` (exploration/reference, not binding approval).
- Google Drive `BottleMap_Android_Baseline.md`, 2026-10-01 (verify live repository).
- Google Drive `Requirements-and-Specifications.md`, modified 2026-10-21 (a more recent requirements source than the API draft).
- Google Drive `BottleMap_frontend_backend_api_spec_v2.md`, 2026-10-04 (checked draft interface contract for customer search and bar menu, confirm newest deployed contract before implementation).

- Interactive design review feedback, 2026-10-27: exact HEX values, type sizes, font mixing, marker layout, image/tag density and product-first flow.
- Bookk Myungjo font license reference: https://noonnu.cc/font_page/1084 (free commercial use including embedding per published summary, modification restricted; verify the official grant at app packaging).
- Frontend note: user-approved UI decisions do not automatically add backend work or change Iteration 2 scope.