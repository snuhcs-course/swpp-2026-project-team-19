package com.zerotoone.bottlemap.ui.customer

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.zerotoone.bottlemap.ui.theme.BottleMapTheme

/** Preserve Customer behavior while sharing the same Cocoa Charcoal design tokens. */
@Composable
internal fun I2CustomerSearchTheme(content: @Composable () -> Unit) {
    BottleMapTheme {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background,
            contentColor = MaterialTheme.colorScheme.onBackground,
        ) { content() }
    }
}
