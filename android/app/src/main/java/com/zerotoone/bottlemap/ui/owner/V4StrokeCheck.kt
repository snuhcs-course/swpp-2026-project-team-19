package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.unit.dp

/** Straight three-point SVG-style check; used across the photo flow. */
@Composable
internal fun V4StrokeCheck(
    modifier: Modifier = Modifier.size(20.dp),
    color: Color = Color(0xFFB9DFC8),
) {
    Canvas(modifier) {
        val w = size.width
        val h = size.height
        val unit = w / 24f
        val line = 2.4f * unit
        drawLine(color,Offset(w * 0.16f,h * 0.53f),Offset(w * 0.41f,h * 0.78f),
            strokeWidth=line,cap=StrokeCap.Round)
        drawLine(color,Offset(w * 0.41f,h * 0.78f),Offset(w * 0.87f,h * 0.23f),
            strokeWidth=line,cap=StrokeCap.Round)
    }
}
