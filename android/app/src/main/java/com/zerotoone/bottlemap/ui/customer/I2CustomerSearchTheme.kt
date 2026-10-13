// AI-assisted implementation draft (2026-10-13, I2-P13/P14). Human build/review pending.
package com.zerotoone.bottlemap.ui.customer

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Scoped to I2 Customer search so P19 Owner and application-wide theme stay unchanged.
private val i2CustomerSearchColors = darkColorScheme(
    primary = Color(0xFFD6B77E),
    onPrimary = Color(0xFF0C1626),
    background = Color(0xFF0C1626),
    onBackground = Color(0xFFF4F5F7),
    surface = Color(0xFF14253C),
    onSurface = Color(0xFFF4F5F7),
    surfaceVariant = Color(0xFF101E32),
    onSurfaceVariant = Color(0xFFB5C4D1),
    outline = Color(0xFF344A63),
    outlineVariant = Color(0xFF344A63),
    error = Color(0xFFFFA2A9),
    errorContainer = Color(0xFF482A35),
    onErrorContainer = Color(0xFFFFE1E1),
)

@Composable
internal fun I2CustomerSearchTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = i2CustomerSearchColors, content = content)
}
