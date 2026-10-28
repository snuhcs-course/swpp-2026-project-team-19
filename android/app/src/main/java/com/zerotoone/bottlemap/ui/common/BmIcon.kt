package com.zerotoone.bottlemap.ui.common

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.isSpecified
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.VectorPath
import androidx.compose.ui.res.vectorResource
import androidx.compose.ui.tooling.preview.Preview
import com.zerotoone.bottlemap.R
import com.zerotoone.bottlemap.ui.theme.BottleMapDarkColorScheme
import com.zerotoone.bottlemap.ui.theme.BottleMapMotion
import com.zerotoone.bottlemap.ui.theme.BottleMapSpacing

/** The BottleMap icon set. Intended use of each icon: docs/android_icons.md. */
enum class BmIconId(internal val resId: Int) {
    SEARCH(R.drawable.ic_bm_search),
    BACK(R.drawable.ic_bm_back),
    MAP(R.drawable.ic_bm_map),
    BAR_PIN(R.drawable.ic_bm_bar_pin),
    LOCATION(R.drawable.ic_bm_location),
    BAR(R.drawable.ic_bm_bar),
    GLASS(R.drawable.ic_bm_glass),
    PRICE(R.drawable.ic_bm_price),
    UPDATED(R.drawable.ic_bm_updated),
    ACCOUNT(R.drawable.ic_bm_account),
    LOGIN(R.drawable.ic_bm_login),
    RETRY(R.drawable.ic_bm_retry),
    ERROR(R.drawable.ic_bm_error),
    EMPTY(R.drawable.ic_bm_empty),
    CAMERA(R.drawable.ic_bm_camera),
    REVIEW(R.drawable.ic_bm_review),
    PUBLISH(R.drawable.ic_bm_publish),
    MANAGE_BAR(R.drawable.ic_bm_manage_bar),
    CERTIFICATE(R.drawable.ic_bm_certificate),
}

/**
 * Draws a BottleMap icon (DESIGN.md 9, "Icons and images": one outlined family, filled only
 * when selected).
 *
 * - `selected = false`: outline only (style A), in [tint] (the content colour by default).
 * - `selected = true`: the same outline plus the icon's accent shape in
 *   `MaterialTheme.colorScheme.primary` (style B). The accent fades in over
 *   `BottleMapMotion.selectionMs`, or switches at once when the system turns animations off.
 *
 * Pass `contentDescription = null` when adjacent text already names the action.
 * A plain `Icon(painterResource(..), tint = ..)` also works and always gives style A,
 * because the accent path is transparent in the drawable.
 */
@Composable
fun BmIcon(
    icon: BmIconId,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    selected: Boolean = false,
    tint: Color = LocalContentColor.current,
) {
    val source = ImageVector.vectorResource(icon.resId)
    val line = if (tint.isSpecified) tint else LocalContentColor.current
    val accentColor = MaterialTheme.colorScheme.primary
    val accentAlpha by animateFloatAsState(
        targetValue = if (selected) 1f else 0f,
        animationSpec = if (rememberReducedMotion()) snap<Float>() else tween<Float>(BottleMapMotion.selectionMs),
        label = "bmIconAccent",
    )
    val accent = accentColor.copy(alpha = accentColor.alpha * accentAlpha)
    val image = remember(source, line, accent) { source.recolored(line = line, accent = accent) }
    // Colours are set per path above; a single Icon tint would also paint the accent path.
    Icon(
        imageVector = image,
        contentDescription = contentDescription,
        modifier = modifier,
        tint = Color.Unspecified,
    )
}

/** ic_bm_* drawables contain only top-level paths named "skeleton", "skeleton_dot" and "accent". */
private fun ImageVector.recolored(line: Color, accent: Color): ImageVector {
    val builder = ImageVector.Builder(
        name = name,
        defaultWidth = defaultWidth,
        defaultHeight = defaultHeight,
        viewportWidth = viewportWidth,
        viewportHeight = viewportHeight,
        autoMirror = autoMirror,
    )
    for (node in root) {
        val path = node as? VectorPath ?: continue
        builder.addPath(
            pathData = path.pathData,
            pathFillType = path.pathFillType,
            name = path.name,
            fill = when (path.name) {
                "accent" -> SolidColor(accent)
                "skeleton_dot" -> SolidColor(line)
                else -> null
            },
            fillAlpha = path.fillAlpha,
            stroke = if (path.stroke != null) SolidColor(line) else null,
            strokeAlpha = path.strokeAlpha,
            strokeLineWidth = path.strokeLineWidth,
            strokeLineCap = path.strokeLineCap,
            strokeLineJoin = path.strokeLineJoin,
            strokeLineMiter = path.strokeLineMiter,
        )
    }
    return builder.build()
}

@Preview(name = "BottleMap icons: outline (A) and selected (B)", widthDp = 360)
@Composable
private fun BmIconSetPreview() {
    MaterialTheme(colorScheme = BottleMapDarkColorScheme) {
        Surface(color = MaterialTheme.colorScheme.background) {
            Column(
                modifier = Modifier.padding(BottleMapSpacing.md),
                verticalArrangement = Arrangement.spacedBy(BottleMapSpacing.sm),
            ) {
                BmIconId.entries.chunked(2).forEach { pair ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(BottleMapSpacing.md),
                    ) {
                        pair.forEach { id ->
                            Row(
                                modifier = Modifier.weight(1f),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(BottleMapSpacing.xs),
                            ) {
                                BmIcon(id, contentDescription = null)
                                BmIcon(id, contentDescription = null, selected = true)
                                Text(
                                    text = id.name.lowercase(),
                                    style = MaterialTheme.typography.labelMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
