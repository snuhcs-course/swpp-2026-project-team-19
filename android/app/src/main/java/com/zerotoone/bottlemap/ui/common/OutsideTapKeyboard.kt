package com.zerotoone.bottlemap.ui.common

import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController

/**
 * Applied above the entire navigation hierarchy, including Customer and Owner.
 * A text field consumes its own tap; taps on available non-field background
 * clear focus (rather than merely hide the IME), so the next field tap reopens it.
 *
 * Clickable action controls should clear focus in their own handlers as well,
 * because they consume their pointer events before this parent gesture handler.
 */
@Composable
fun Modifier.dismissKeyboardOnOutsideTap(): Modifier {
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    return this.pointerInput(focus, keyboard) {
        detectTapGestures(onTap = {
            focus.clearFocus()
            keyboard?.hide()
        })
    }
}
