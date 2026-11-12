package com.zerotoone.bottlemap.ui.common

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.Dp

/**
 * The outlined 24-unit icons of BottleMap_Minimal_UX_v18.html (`iconPaths`), drawn with the
 * same 1.7 stroke, round caps and joins. Used where the v18 screens need an icon that
 * [BmIcon] does not have, so both screens draw the identical glyph.
 */
enum class BmLineIconId(internal val svgPath: String) {
    SEARCH(circle(11f, 11f, 7f) + "M16.5 16.5 21.5 21.5"),
    USER(circle(12f, 8f, 4f) + "M4.5 21a7.5 7.5 0 0 1 15 0"),
    BACK("M15 18 9 12 15 6"),
    DOWN("M6 9 12 15 18 9"),
    ARROW("M9 18 15 12 9 6"),
    CHECK("M20 6 9 17 4 12"),
    CHECK_CIRCLE(circle(12f, 12f, 9f) + "M7 12l3 3 7-7"),
    CLOSE("M6 6l12 12M18 6 6 18"),
    ALERT(circle(12f, 12f, 9f) + "M12 7v6M12 17h.01"),
    RETRY("M20 11a8 8 0 0 0-14.5-5L3 9M3 3v6h6M4 13a8 8 0 0 0 14.5 5l2.5-3m0 6v-6h-6"),
    PLUS("M12 5v14M5 12h14"),
}

private fun circle(cx: Float, cy: Float, r: Float) =
    "M${cx - r} ${cy}a$r $r 0 1 0 ${2 * r} 0a$r $r 0 1 0 ${-2 * r} 0"

@Composable
fun BmLineIcon(icon: BmLineIconId, size: Dp, color: Color, modifier: Modifier = Modifier) {
    val path = remember(icon) { PathParser().parsePathString(icon.svgPath).toPath() }
    Canvas(modifier.size(size)) {
        val unit = this.size.width / 24f
        scale(unit, unit, pivot = androidx.compose.ui.geometry.Offset.Zero) {
            drawPath(path, color, style = Stroke(width = 1.7f, cap = StrokeCap.Round, join = StrokeJoin.Round))
        }
    }
}
