package com.zerotoone.bottlemap.ui.common

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/**
 * The same bottom-confirmation language as the photo-review '게시하기' sheet.
 * Unlike a centered AlertDialog, ModalBottomSheet layers over the app's bottom tabs.
 * Only UI is owned here: callers keep their existing save/delete/retry behavior.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OwnerBottomConfirmSheet(
    title: String,
    message: String,
    confirmLabel: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    cancelLabel: String = "취소",
    enabled: Boolean = true,
    tag: String = "owner-bottom-confirm",
    error: String? = null,
    extraContent: (@Composable () -> Unit)? = null,
) {
    val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = state,
        containerColor = UxColor.surface,
        contentColor = UxColor.text,
        scrimColor = Color.Black.copy(alpha = 0.65f),
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
        dragHandle = null,
        modifier = Modifier.testTag(tag),
    ) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
                .navigationBarsPadding()
                .padding(start = 20.dp, end = 20.dp, top = 16.dp, bottom = 30.dp),
        ) {
            Box(
                Modifier.align(Alignment.CenterHorizontally)
                    .padding(bottom = 19.dp)
                    .size(width = 41.dp, height = 4.dp)
                    .background(UxColor.outline, RoundedCornerShape(10.dp))
            )
            Text(title, style = uxText(21f, 700, serif = true),
                modifier = Modifier.padding(vertical = 10.dp))
            if (message.isNotBlank()) {
                Text(message, style = uxText(13f, 400, UxColor.sub, lineHeight = 1.65f),
                    modifier = Modifier.padding(bottom = 16.dp))
            }
            extraContent?.invoke()
            if (error != null) {
                Text(error, style = uxText(13f, 400, UxColor.error),
                    modifier = Modifier.padding(bottom = 12.dp))
            }
            Row(Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                UxSecondaryButton(cancelLabel, onDismiss,
                    Modifier.weight(1f).testTag("$tag-cancel"))
                UxMainButton(confirmLabel, onConfirm,
                    Modifier.weight(1f).testTag("$tag-confirm"), enabled = enabled)
            }
        }
    }
}
