package com.zerotoone.bottlemap.ui.owner

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.delay

/**
 * Re-evaluate local Mock operating status while an owner/customer screen remains visible.
 * Exception expiry is derived from the current Seoul date/time; no repository mutation or
 * backend request occurs. The coroutine is cancelled when the composable leaves composition.
 */
@Composable
internal fun rememberOwnerNow(): Long {
    var current by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(30_000L)
            current = System.currentTimeMillis()
        }
    }
    return current
}
