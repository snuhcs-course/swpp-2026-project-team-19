package com.zerotoone.bottlemap.ui.customer

import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/**
 * Shared fixed overlay for Customer detail and Owner customer preview.
 * Kept out of verticalScroll so it never moves with menu content.
 * 48dp touch target, black disk and centered amber upward chevron.
 */
@Composable
internal fun P18ScrollTopButton(
    scroll: ScrollState,
    modifier: Modifier=Modifier,
) {
    if(scroll.value<=0) return
    val scope=rememberCoroutineScope()
    Box(modifier.size(48.dp)
        .background(Color.Black,CircleShape)
        .clickable { scope.launch { scroll.animateScrollTo(0) } }
        .semantics { contentDescription="페이지 맨 위로 이동" }
        .testTag("customer-preview-scroll-top"),
        contentAlignment=Alignment.Center) {
        P18DetailCategoryChevron(open=true)
    }
}
