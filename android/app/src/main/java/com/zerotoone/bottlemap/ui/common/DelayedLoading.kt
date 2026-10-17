// AI-assisted UI stabilization (2026-10-18, I2-P31/P32).
package com.zerotoone.bottlemap.ui.common

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import kotlinx.coroutines.delay

/** 
 * Suppress a loading-only placeholder during fast navigation/API responses.
 *
 * Call this ONLY from an active Loading branch. When that branch leaves the
 * composition, its timer is cancelled and it cannot surface an old spinner.
 * Actual errors, empty results and retry controls must render immediately.
 */
internal const val LOADING_FEEDBACK_DELAY_MS = 300L

@Composable
fun DelayedLoading(
    modifier: Modifier = Modifier,
    delayMillis: Long = LOADING_FEEDBACK_DELAY_MS,
    content: @Composable () -> Unit,
) {
    var visible by remember { mutableStateOf(false) }

    LaunchedEffect(delayMillis) {
        delay(delayMillis)
        visible = true
    }

    Box(modifier = modifier) {
        if (visible) content()
    }
}
