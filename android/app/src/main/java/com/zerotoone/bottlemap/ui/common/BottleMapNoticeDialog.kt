package com.zerotoone.bottlemap.ui.common

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/** Short blocking notice for an explicit user action, never a success substitute. */
@Composable
internal fun BottleMapNoticeDialog(
    message: String,
    onDismiss: () -> Unit,
    tag: String,
    title: String = "안내",
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = Modifier.testTag(tag),
        shape = RoundedCornerShape(16.dp),
        containerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
        title = { Text(title) },
        text = { Text(message) },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("확인") }
        },
    )
}
