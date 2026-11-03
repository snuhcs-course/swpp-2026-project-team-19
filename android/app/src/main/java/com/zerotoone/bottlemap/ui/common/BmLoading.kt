package com.zerotoone.bottlemap.ui.common

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.zerotoone.bottlemap.ui.theme.BottleMapDarkColorScheme
import com.zerotoone.bottlemap.ui.theme.BottleMapSpacing
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/*
 * Indeterminate loading animations in the icon style (DESIGN.md 9): a whisky glass on the same
 * 24-unit grid and 1.5 outline as the ic_bm_* icons. There is no percentage and no progress value,
 * because menu extraction and network waits have no known length (DESIGN.md 5.2).
 *
 * Colours: outline = colorScheme.onSurfaceVariant (BottleMapPalette.textSecondary),
 * liquid = colorScheme.primary (BottleMapPalette.primary).
 * The loops (2.0 s and 2.4 s) are slower than the BottleMapMotion UI durations on purpose; show or
 * hide the loader itself with DelayedLoading and a contentTransitionMs fade.
 * When the system turns animations off, the glass is drawn as one still frame.
 * Pair the loader with a short visible Korean label; TalkBack announces an indeterminate progress bar.
 */

/** Whisky level ebbs and rises (never empty, never full) with a gentle surface wave. Default size 48dp. */
@Composable
fun GlassFillLoading(modifier: Modifier = Modifier) {
    GlassFillLoading(modifier, reduceMotion = rememberReducedMotion())
}

/** Three ice cubes drop in one by one with a small bounce, then fade out and the loop restarts. Default size 48dp. */
@Composable
fun IceDropLoading(modifier: Modifier = Modifier) {
    IceDropLoading(modifier, reduceMotion = rememberReducedMotion())
}

// ---- geometry (24 x 24 grid, 1.5 outline like the ic_bm_* icons) ----
private val DEFAULT_SIZE = 48.dp
private const val GLASS = "M3.5 6.5 L4.75 19.25 A1.75 1.75 0 0 0 6.5 21 H17.5 A1.75 1.75 0 0 0 19.25 19.25 L20.5 6.5"
private val LINE = Stroke(width = 1.5f, cap = StrokeCap.Round, join = StrokeJoin.Round)
private val TAU = (2 * PI).toFloat()
private val PI_F = PI.toFloat()

private const val FILL_MS = 2000
private const val ICE_MS = 2400

private class Cube(val x: Float, val y: Float, val rot: Float, val start: Float)

private val CUBES = listOf(
    Cube(8.9f, 16.75f, -5f, 0.06f),
    Cube(15.1f, 16.75f, 6f, 0.26f),
    Cube(12f, 10.8f, 12f, 0.46f),
)
private const val CUBE = 3.8f
private const val CUBE_R = 0.9f
private const val DROP = 7f // fall distance in grid units
private const val FALL = 0.13f // fractions of the ICE_MS cycle
private const val BOUNCE = 0.09f
private const val FADE0 = 0.80f
private const val FADE1 = 0.94f
private const val ICE_BASE = 12.8f
private const val ICE_RISE = 0.35f

@Composable
internal fun GlassFillLoading(modifier: Modifier, reduceMotion: Boolean) {
    val lineColor = MaterialTheme.colorScheme.onSurfaceVariant
    val liquidColor = MaterialTheme.colorScheme.primary
    val phase: State<Float>? = if (reduceMotion) null else loopPhase(FILL_MS)
    val glass = remember { PathParser().parsePathString(GLASS).toPath() }
    val inside = remember { PathParser().parsePathString("$GLASS Z").toPath() }
    val liquid = remember { Path() }
    Canvas(modifier.size(DEFAULT_SIZE).loadingSemantics()) {
        val t = phase?.value
        val level = if (t == null) 14f else 17.6f - 6.4f * (1f - cos(TAU * t)) / 2f
        inGrid {
            liquid.setSurface(level, if (t == null) 0f else 0.32f, 8f, if (t == null) 0f else -TAU * t)
            clipPath(inside) { drawPath(liquid, liquidColor) }
            drawPath(glass, lineColor, style = LINE)
        }
    }
}

@Composable
internal fun IceDropLoading(modifier: Modifier, reduceMotion: Boolean) {
    val lineColor = MaterialTheme.colorScheme.onSurfaceVariant
    val liquidColor = MaterialTheme.colorScheme.primary
    val phase: State<Float>? = if (reduceMotion) null else loopPhase(ICE_MS)
    val glass = remember { PathParser().parsePathString(GLASS).toPath() }
    val inside = remember { PathParser().parsePathString("$GLASS Z").toPath() }
    val liquid = remember { Path() }
    Canvas(modifier.size(DEFAULT_SIZE).loadingSemantics()) {
        val t = phase?.value
        val ys = FloatArray(CUBES.size)
        val alphas = FloatArray(CUBES.size)
        val keep = if (t == null) 1f else 1f - ((t - FADE0) / (FADE1 - FADE0)).coerceIn(0f, 1f)
        var rise = 0f
        var ripple = 0f
        CUBES.forEachIndexed { i, c ->
            if (t == null) {
                ys[i] = c.y
                alphas[i] = 1f
                return@forEachIndexed
            }
            val u = (t - c.start) / FALL
            if (u < 0f) {
                alphas[i] = 0f
            } else if (u < 1f) { // ease-in fall with a quick fade-in
                ys[i] = c.y - DROP * (1f - u * u)
                alphas[i] = (u / 0.3f).coerceAtMost(1f) * keep
            } else { // one small bounce, the liquid rises a little, short ripple
                val v = (t - c.start - FALL) / BOUNCE
                ys[i] = c.y - (if (v < 1f) 0.6f * sin(PI_F * v) else 0f)
                alphas[i] = keep
                val w = (t - c.start - FALL) / 0.12f
                rise += ICE_RISE * (w / 0.66f).coerceIn(0f, 1f)
                if (w < 1f) ripple += 0.25f * (1f - w) * (1f - w)
            }
        }
        val level = if (t == null) ICE_BASE - 3 * ICE_RISE else ICE_BASE - rise * keep
        inGrid {
            liquid.setSurface(level, ripple, 5f, if (t == null) 0f else -TAU * t * 5f)
            clipPath(inside) { drawPath(liquid, liquidColor) }
            CUBES.forEachIndexed { i, c ->
                if (alphas[i] > 0f) {
                    rotate(c.rot, pivot = Offset(c.x, ys[i])) {
                        drawRoundRect(
                            color = lineColor,
                            topLeft = Offset(c.x - CUBE / 2f, ys[i] - CUBE / 2f),
                            size = Size(CUBE, CUBE),
                            cornerRadius = CornerRadius(CUBE_R),
                            alpha = alphas[i],
                            style = LINE,
                        )
                    }
                }
            }
            drawPath(glass, lineColor, style = LINE)
        }
    }
}

@Composable
private fun loopPhase(durationMs: Int): State<Float> =
    rememberInfiniteTransition(label = "bmLoading").animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(durationMs, easing = LinearEasing), RepeatMode.Restart),
        label = "phase",
    )

private fun Modifier.loadingSemantics(): Modifier =
    semantics { progressBarRangeInfo = ProgressBarRangeInfo.Indeterminate }

/** Draw in the 24-unit grid whatever the Canvas size; the 1.5 outline scales with it. */
private inline fun DrawScope.inGrid(block: DrawScope.() -> Unit) {
    val s = size.minDimension / 24f
    scale(s, s, pivot = Offset.Zero, block = block)
}

/** Liquid body: wavy top edge from x=2 to 22, closed below the glass; clipped to the glass inside. */
private fun Path.setSurface(level: Float, amp: Float, wavelength: Float, phase: Float) {
    reset()
    var x = 2f
    moveTo(x, level + amp * sin(phase + TAU * x / wavelength))
    while (x < 22f) {
        x += 0.5f
        lineTo(x, level + amp * sin(phase + TAU * x / wavelength))
    }
    lineTo(22f, 23f)
    lineTo(2f, 23f)
    close()
}

@Preview(name = "Loaders: animated and reduced motion")
@Composable
private fun BmLoadingPreview() {
    MaterialTheme(colorScheme = BottleMapDarkColorScheme) {
        Surface(color = MaterialTheme.colorScheme.background) {
            Row(
                modifier = Modifier.padding(BottleMapSpacing.md),
                horizontalArrangement = Arrangement.spacedBy(BottleMapSpacing.md),
            ) {
                GlassFillLoading(Modifier, reduceMotion = false)
                IceDropLoading(Modifier, reduceMotion = false)
                GlassFillLoading(Modifier, reduceMotion = true)
                IceDropLoading(Modifier, reduceMotion = true)
            }
        }
    }
}
