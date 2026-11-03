package com.zerotoone.bottlemap.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.font.FontFamily

/** Dark-first Cocoa Charcoal. Font binaries are not yet in the design branch. */
@Composable
fun BottleMapTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = BottleMapDarkColorScheme,
        typography = bottleMapTypography(
            fontFamily = FontFamily.SansSerif,
            headingFontFamily = FontFamily.Serif,
        ),
        content = content,
    )
}
