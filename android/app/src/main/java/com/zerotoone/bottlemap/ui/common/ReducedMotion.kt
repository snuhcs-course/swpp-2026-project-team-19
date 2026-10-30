package com.zerotoone.bottlemap.ui.common

import android.provider.Settings
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext

/**
 * True when the user turned animations off (Settings > Accessibility > Remove animations,
 * or developer options "Animator duration scale" = off), i.e. ANIMATOR_DURATION_SCALE is 0.
 *
 * DESIGN.md 9 asks every motion to respect this. The value is read when the caller enters
 * the composition; a settings change applies the next time the screen is composed.
 */
@Composable
internal fun rememberReducedMotion(): Boolean {
    val resolver = LocalContext.current.contentResolver
    return remember(resolver) {
        runCatching {
            Settings.Global.getFloat(resolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
        }.getOrDefault(false)
    }
}
