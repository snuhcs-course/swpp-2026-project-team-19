package com.zerotoone.bottlemap.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Immutable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * BottleMap design tokens - design-system v1.0 final baseline (2026-10-27).
 *
 * USER-APPROVED: eight Cocoa Charcoal HEX values; mixed font roles
 * (Bookk Myungjo for display/screen titles, Pretendard otherwise),
 * 24sp screen title / 16sp card title / 16sp price / 12sp caption;
 * outlined icons, restrained amber accents, balanced density and subtle motion.
 * PROPOSED: other dp/sp, illustrations, marker photo geometry and durations.
 * 12px HTML marker label is translated to a 12sp Android starting point.
 * All visual values still require device/accessibility QA.
 * Font files are not bundled in this source document.
 *
 * This file contains visual tokens ONLY. Exact-product search bypass and OR
 * multi-tag filtering are UI/ViewModel rules documented in design.md.
 * Do not place product/group sorting,
 * representative serving-size selection, navigation or API DTOs here.
 *
 * Baseline: Compose + Material 3, namespace com.zerotoone.bottlemap.
 * Validate the package, theme integration and current Gradle versions in repo.
 */
object BottleMapPalette {
    // Cocoa Charcoal - never a pure-black default canvas.
    val canvas = Color(0xFF211E1B)
    val surface = Color(0xFF302B27)
    val surfaceElevated = Color(0xFF3A332E)
    val surfaceVariant = Color(0xFF403832)

    // Keep emphasis sparing. The eight principal HEX roles are user-approved.
    val primary = Color(0xFFC99D6B)
    val onPrimary = Color(0xFF211A14)
    val primaryContainer = Color(0xFF503C29)
    val onPrimaryContainer = Color(0xFFF7DFBF)

    // Copy and icons. textPrimary/textSecondary/outlineVariant approved.
    val textPrimary = Color(0xFFF2EDE8)
    val textSecondary = Color(0xFFC7BBB0)
    val textMuted = Color(0xFFB9AEA4)
    val outline = Color(0xFF786A60)
    val outlineVariant = Color(0xFF51473F)

    // Semantic states - not general-purpose decorative accents.
    val error = Color(0xFFFFB4AB)
    val onError = Color(0xFF690005)
    val errorContainer = Color(0xFF8E3736)
    val onErrorContainer = Color(0xFFFFD8CC)
    val success = Color(0xFFB9DFC8)
    val onSuccess = Color(0xFF163624)
    val successContainer = Color(0xFF244C38)
    val onSuccessContainer = Color(0xFFD6EEDC)

    // Custom map overlay/price-row roles; use only where their semantics apply.
    val mapMarker = surface
    val mapMarkerSelected = primary
    val onMapMarker = textPrimary
    val onMapMarkerSelected = onPrimary
    val priceOptionBackground = surfaceElevated
    val divider = outlineVariant
    val scrim = Color(0xFF000000)
}

/**
 * The current product decision is DARK FIRST. A full light scheme is not
 * approved; do not silently call lightColorScheme() or follow system dark
 * preference until a reviewed light palette and toggle behavior exist.
 *
 * Screen code should use MaterialTheme.colorScheme for semantic colors.
 */
val BottleMapDarkColorScheme: ColorScheme = darkColorScheme(
    primary = BottleMapPalette.primary,
    onPrimary = BottleMapPalette.onPrimary,
    primaryContainer = BottleMapPalette.primaryContainer,
    onPrimaryContainer = BottleMapPalette.onPrimaryContainer,
    secondary = BottleMapPalette.textSecondary,
    onSecondary = BottleMapPalette.canvas,
    secondaryContainer = BottleMapPalette.surfaceVariant,
    onSecondaryContainer = BottleMapPalette.textPrimary,
    tertiary = BottleMapPalette.success,
    onTertiary = BottleMapPalette.onSuccess,
    tertiaryContainer = BottleMapPalette.successContainer,
    onTertiaryContainer = BottleMapPalette.onSuccessContainer,
    background = BottleMapPalette.canvas,
    onBackground = BottleMapPalette.textPrimary,
    surface = BottleMapPalette.surface,
    onSurface = BottleMapPalette.textPrimary,
    surfaceVariant = BottleMapPalette.surfaceVariant,
    onSurfaceVariant = BottleMapPalette.textSecondary,
    outline = BottleMapPalette.outline,
    outlineVariant = BottleMapPalette.outlineVariant,
    error = BottleMapPalette.error,
    onError = BottleMapPalette.onError,
    errorContainer = BottleMapPalette.errorContainer,
    onErrorContainer = BottleMapPalette.onErrorContainer,
    inverseSurface = BottleMapPalette.textPrimary,
    inverseOnSurface = BottleMapPalette.canvas,
    inversePrimary = Color(0xFF7A532D),
    surfaceTint = BottleMapPalette.primary,
    scrim = BottleMapPalette.scrim,
)

/** PROPOSED dimensions in dp; agents must reference these names, not literals. */
object BottleMapSpacing {
    val xxs: Dp = 4.dp
    val xs: Dp = 8.dp
    val sm: Dp = 12.dp
    val md: Dp = 16.dp
    val lg: Dp = 20.dp
    val xl: Dp = 24.dp
    val xxl: Dp = 32.dp
    val xxxl: Dp = 40.dp

    val screenHorizontal: Dp = lg
    val sectionGap: Dp = xl
    val cardPadding: Dp = md
    val rowGap: Dp = sm
    val barCardTagsToPriceGap: Dp = xxs
    val mapMarkerTextGap: Dp = 2.dp // small gap between name and price/size lines
    val mapMarkerImageToTextGap: Dp = xs
    val priceToPourGap: Dp = xs
    val barToProductGap: Dp = sm
    val productSeparatorGap: Dp = md
}

/** PROPOSED rounded-corner values, all dp. */
object BottleMapRadii {
    val small: Dp = 8.dp
    val medium: Dp = 12.dp
    val large: Dp = 16.dp
    val pill: Dp = 100.dp
}

object BottleMapShapes {
    val button = RoundedCornerShape(BottleMapRadii.medium)
    val textField = RoundedCornerShape(BottleMapRadii.medium)
    val card = RoundedCornerShape(BottleMapRadii.large)
    val priceRow = RoundedCornerShape(BottleMapRadii.small)
    val sheet = RoundedCornerShape(
        topStart = BottleMapRadii.large,
        topEnd = BottleMapRadii.large,
    )
    val chip = RoundedCornerShape(BottleMapRadii.pill)
    val mapMarker = RoundedCornerShape(BottleMapRadii.medium)
}

/** PROPOSED minimum sizes; never use fixed heights to clip scaled text. */
object BottleMapSizes {
    val minTouchTarget: Dp = 48.dp
    val primaryButtonMinHeight: Dp = 56.dp
    val secondaryButtonMinHeight: Dp = 48.dp
    val searchFieldMinHeight: Dp = 56.dp
    val filterChipMinTouchHeight: Dp = 48.dp
    val mapMarkerTouchTarget: Dp = 48.dp

    // PROPOSED media and illustration sizes; visual media may be <48dp,
    // but each interactive marker/row must still have >=48dp touch target.
    val barCardThumbnail: Dp = 64.dp
    val mapMarkerPhoto: Dp = 38.dp
    // Visual BOUNDING BOXES, width x height (PROPOSED). Size names used before
    // v1.0 mean HEIGHT, not width; keep aliases for existing preview call sites.
    val productBottleSmallWidth: Dp = 16.dp
    val productBottleSmallHeight: Dp = 24.dp
    val productBottleMediumWidth: Dp = 24.dp
    val productBottleMediumHeight: Dp = 38.dp
    val productBottleLargeWidth: Dp = 40.dp
    val productBottleLargeHeight: Dp = 64.dp

    // Compatibility: previous one-dimensional size tokens always mean HEIGHT.
    val productBottleSmall: Dp = productBottleSmallHeight
    val productBottleMedium: Dp = productBottleMediumHeight
    val productBottleLarge: Dp = productBottleLargeHeight
}

/**
 * Motion values in milliseconds. These are animation durations, not loading
 * deadlines. Honor OS-level reduced-motion/accessibility behavior.
 */
@Immutable
data class BottleMapMotionTokens(
    val tapFeedbackMs: Int = 150,
    val selectionMs: Int = 180,
    val contentTransitionMs: Int = 240,
)

val BottleMapMotion = BottleMapMotionTokens()

/**
 * PROPOSED semantic typography scale. Values are in sp.
 * M3 typography roles below and custom price/pour styles share this scale.
 */
object BottleMapTypeScale {
    val display: TextUnit = 28.sp
    val displayLineHeight: TextUnit = 36.sp
    val screenTitle: TextUnit = 24.sp
    val screenTitleLineHeight: TextUnit = 32.sp
    val sectionTitle: TextUnit = 20.sp
    val sectionTitleLineHeight: TextUnit = 28.sp
    val cardTitle: TextUnit = 16.sp
    val cardTitleLineHeight: TextUnit = 23.sp
    val body: TextUnit = 16.sp
    val bodyLineHeight: TextUnit = 24.sp
    val label: TextUnit = 14.sp
    val labelLineHeight: TextUnit = 20.sp
    val caption: TextUnit = 12.sp
    val captionLineHeight: TextUnit = 18.sp
    val price: TextUnit = 16.sp
    val priceLineHeight: TextUnit = 23.sp
    val pourAmount: TextUnit = 13.sp
    val pourAmountLineHeight: TextUnit = 20.sp
    val unitRate: TextUnit = 12.sp
    val unitRateLineHeight: TextUnit = 16.sp
    val markerLabel: TextUnit = 12.sp
    val markerLabelLineHeight: TextUnit = 16.sp
    val markerPrice: TextUnit = 12.sp
    val markerPriceLineHeight: TextUnit = 16.sp
    val featureTag: TextUnit = 12.sp
    val featureTagLineHeight: TextUnit = 18.sp
}

/**
 * Supply licensed FontFamily resources in the actual Android app:
 * - fontFamily: Pretendard (all utilitarian text)
 * - headingFontFamily: Bookk Myungjo (only display and headline roles)
 *
 * The defaults preserve backwards source compatibility while previewing;
 * FontFamily.Default is a TEMPORARY FALLBACK, not the production design.
 * Bookk Myungjo has Light and Bold files; do not request synthetic SemiBold.
 * Example integration: bottleMapTypography(fontFamily = pretendard,
 *                                     headingFontFamily = bookkMyungjo)
 */
fun bottleMapTypography(
    fontFamily: FontFamily = FontFamily.Default,
    headingFontFamily: FontFamily = fontFamily,
): Typography = Typography(
    displayLarge = TextStyle(fontFamily = headingFontFamily, fontWeight = FontWeight.Bold, fontSize = 32.sp, lineHeight = 40.sp),
    displayMedium = TextStyle(fontFamily = headingFontFamily, fontWeight = FontWeight.Bold, fontSize = 30.sp, lineHeight = 38.sp),
    displaySmall = TextStyle(fontFamily = headingFontFamily, fontWeight = FontWeight.Bold, fontSize = BottleMapTypeScale.display, lineHeight = BottleMapTypeScale.displayLineHeight),
    headlineLarge = TextStyle(fontFamily = headingFontFamily, fontWeight = FontWeight.Bold, fontSize = 28.sp, lineHeight = 36.sp), // PROPOSED
    headlineMedium = TextStyle(fontFamily = headingFontFamily, fontWeight = FontWeight.Bold, fontSize = 26.sp, lineHeight = 34.sp), // PROPOSED: distinct from approved screenTitle/headlineSmall
    headlineSmall = TextStyle(fontFamily = headingFontFamily, fontWeight = FontWeight.Bold, fontSize = BottleMapTypeScale.screenTitle, lineHeight = BottleMapTypeScale.screenTitleLineHeight),
    titleLarge = TextStyle(fontFamily = fontFamily, fontWeight = FontWeight.SemiBold, fontSize = BottleMapTypeScale.sectionTitle, lineHeight = BottleMapTypeScale.sectionTitleLineHeight),
    titleMedium = TextStyle(fontFamily = fontFamily, fontWeight = FontWeight.SemiBold, fontSize = BottleMapTypeScale.cardTitle, lineHeight = BottleMapTypeScale.cardTitleLineHeight),
    titleSmall = TextStyle(fontFamily = fontFamily, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, lineHeight = 22.sp),
    bodyLarge = TextStyle(fontFamily = fontFamily, fontWeight = FontWeight.Normal, fontSize = BottleMapTypeScale.body, lineHeight = BottleMapTypeScale.bodyLineHeight),
    bodyMedium = TextStyle(fontFamily = fontFamily, fontWeight = FontWeight.Normal, fontSize = 14.sp, lineHeight = 21.sp),
    bodySmall = TextStyle(fontFamily = fontFamily, fontWeight = FontWeight.Normal, fontSize = BottleMapTypeScale.caption, lineHeight = BottleMapTypeScale.captionLineHeight),
    labelLarge = TextStyle(fontFamily = fontFamily, fontWeight = FontWeight.Medium, fontSize = BottleMapTypeScale.label, lineHeight = BottleMapTypeScale.labelLineHeight),
    labelMedium = TextStyle(fontFamily = fontFamily, fontWeight = FontWeight.Medium, fontSize = 12.sp, lineHeight = 16.sp),
    labelSmall = TextStyle(fontFamily = fontFamily, fontWeight = FontWeight.Medium, fontSize = 12.sp, lineHeight = 18.sp),
)

/** Display actual price before actual serving size as a single semantic pair. */
fun bottleMapPriceTextStyle(fontFamily: FontFamily = FontFamily.Default): TextStyle = TextStyle(
    fontFamily = fontFamily,
    fontWeight = FontWeight.SemiBold,
    fontSize = BottleMapTypeScale.price,
    lineHeight = BottleMapTypeScale.priceLineHeight,
)

fun bottleMapPourTextStyle(fontFamily: FontFamily = FontFamily.Default): TextStyle = TextStyle(
    fontFamily = fontFamily,
    fontWeight = FontWeight.SemiBold,
    fontSize = BottleMapTypeScale.pourAmount,
    lineHeight = BottleMapTypeScale.pourAmountLineHeight,
)

/** Optional supporting explanation of sort rate; never a purchasable price. */
fun bottleMapUnitRateTextStyle(fontFamily: FontFamily = FontFamily.Default): TextStyle = TextStyle(
    fontFamily = fontFamily,
    fontWeight = FontWeight.Normal,
    fontSize = BottleMapTypeScale.unitRate,
    lineHeight = BottleMapTypeScale.unitRateLineHeight,
)

/** Marker texts remain Pretendard, even when screen titles use Bookk Myungjo.
 * Price and size are rendered as a single inline cluster beneath the bar name.
 */
fun bottleMapMarkerNameTextStyle(fontFamily: FontFamily = FontFamily.Default): TextStyle = TextStyle(
    fontFamily = fontFamily,
    fontWeight = FontWeight.SemiBold,
    fontSize = BottleMapTypeScale.markerLabel,
    lineHeight = BottleMapTypeScale.markerLabelLineHeight,
)

fun bottleMapMarkerPriceTextStyle(fontFamily: FontFamily = FontFamily.Default): TextStyle = TextStyle(
    fontFamily = fontFamily,
    fontWeight = FontWeight.Medium,
    fontSize = BottleMapTypeScale.markerPrice,
    lineHeight = BottleMapTypeScale.markerPriceLineHeight,
)

fun bottleMapFeatureTagTextStyle(fontFamily: FontFamily = FontFamily.Default): TextStyle = TextStyle(
    fontFamily = fontFamily,
    fontWeight = FontWeight.Medium,
    fontSize = BottleMapTypeScale.featureTag,
    lineHeight = BottleMapTypeScale.featureTagLineHeight,
)

/**
 * Neutral, rule-based product bottle illustration palette (PROPOSED).
 * These do NOT authorize extra app-wide accent colors.
 * Brand ID -> silhouette/color matching belongs in a separate component,
 * never in theme tokens. Do not reproduce real trademarks or bottle labels.
 */
object BottleMapBottleIllustrationPalette {
    val glass = Color(0xFF9A5824)
    val glassHighlight = Color(0xFFB77337)
    val neckDetail = BottleMapPalette.primary
    val outline = BottleMapPalette.outlineVariant
    val genericLabel = Color(0xFFE6DCCD)
    val labelChoices: List<Color> = listOf(
        Color(0xFFE7DDCB), // ivory
        Color(0xFF91A2AD), // grey-blue
        Color(0xFF8E4048), // wine
        Color(0xFF587B63), // muted green
        Color(0xFFD3AD6E), // warm gold
        Color(0xFFF1EEE6), // soft white
    )
}