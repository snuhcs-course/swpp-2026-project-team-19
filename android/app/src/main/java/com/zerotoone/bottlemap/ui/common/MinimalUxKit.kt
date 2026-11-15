package com.zerotoone.bottlemap.ui.common

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.ui.theme.BottleMapPalette

/**
 * Colours of BottleMap_Minimal_UX_v18.html. The eight principal roles are the Tokens.kt
 * palette; the remaining values are screen-specific colours the prototype states in its CSS
 * and are kept here, named by their role, instead of as literals in the screens.
 */
object UxColor {
    val bg get() = BottleMapPalette.canvas
    val surface get() = BottleMapPalette.surface
    val elevated get() = BottleMapPalette.surfaceElevated
    val variant get() = BottleMapPalette.surfaceVariant
    val gold get() = BottleMapPalette.primary
    val goldOn get() = BottleMapPalette.onPrimary
    val text get() = BottleMapPalette.textPrimary
    val sub get() = BottleMapPalette.textSecondary
    val muted get() = BottleMapPalette.textMuted
    val line get() = BottleMapPalette.outlineVariant
    val outline get() = BottleMapPalette.outline
    val error get() = BottleMapPalette.error
    val success get() = BottleMapPalette.success

    val goldHover = Color(0xFFD9AD7D)
    val toastBg = Color(0xFF483829)
    val toastBorder = Color(0xFF8D6A4B)
    val toastText = Color(0xFFF3E3CE)
    val alertBg = Color(0xFF49312E)
    val alertBorder = Color(0xFF795149)
}

/** Pretendard role (utilitarian text). Falls back to the theme's body font. */
@Composable
fun uxSans(): FontFamily? = MaterialTheme.typography.bodyMedium.fontFamily

/** Bookk Myungjo role (display and screen titles only). Falls back to the theme's heading font. */
@Composable
fun uxSerif(): FontFamily? = MaterialTheme.typography.headlineSmall.fontFamily

/** A CSS-like text style: size in px of the 390px prototype maps 1:1 to sp. */
@Composable
fun uxText(
    size: Float,
    weight: Int = 400,
    color: Color = UxColor.text,
    lineHeight: Float = 1.55f,
    serif: Boolean = false,
    letterSpacing: TextUnit = TextUnit.Unspecified,
): TextStyle = TextStyle(
    fontFamily = if (serif) uxSerif() else uxSans(),
    fontSize = size.sp,
    fontWeight = FontWeight(weight),
    color = color,
    lineHeight = lineHeight.em,
    letterSpacing = letterSpacing,
)

/** `.main-btn`: gold, 56dp minimum height, radius 12, 15sp/750. */
@Composable
fun UxMainButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    Box(
        modifier.fillMaxWidth().heightIn(min = 56.dp)
            .alpha(if (enabled) 1f else 0.5f)
            .background(UxColor.gold, RoundedCornerShape(12.dp))
            .border(1.dp, UxColor.gold, RoundedCornerShape(12.dp))
            .quietClick(enabled = enabled, onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 12.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, style = uxText(15f, 750, UxColor.goldOn))
    }
}

/** `.secondary-btn`: outlined, transparent, 56dp minimum height. */
@Composable
fun UxSecondaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    Box(
        modifier.fillMaxWidth().heightIn(min = 56.dp)
            .alpha(if (enabled) 1f else 0.5f)
            .border(BorderStroke(1.dp, UxColor.outline), RoundedCornerShape(12.dp))
            .quietClick(enabled = enabled, onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 12.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, style = uxText(15f, 750, UxColor.text))
    }
}

/** Top banner for transient feedback, clear of the system status/app toolbar. */
@Composable
fun UxToast(message: String, modifier: Modifier = Modifier) {
    Row(
        modifier.fillMaxWidth().padding(start = 18.dp, end = 18.dp, top = 58.dp)
            .background(UxColor.toastBg, RoundedCornerShape(10.dp))
            .border(1.dp, UxColor.toastBorder, RoundedCornerShape(10.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp)
            .testTag("ux-toast"),
        horizontalArrangement = Arrangement.Start,
    ) {
        Text(message, style = uxText(12f, 400, UxColor.toastText))
    }
}

/** Click without ripple or highlight (the app-wide quiet interaction policy). */
@Composable
fun Modifier.quietClick(enabled: Boolean = true, role: Role = Role.Button, onClick: () -> Unit): Modifier =
    this.clickable(
        interactionSource = remember { MutableInteractionSource() },
        indication = null,
        enabled = enabled,
        role = role,
        onClick = onClick,
    )
