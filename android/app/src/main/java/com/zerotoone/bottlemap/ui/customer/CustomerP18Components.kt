
package com.zerotoone.bottlemap.ui.customer

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.ui.common.BmIcon
import com.zerotoone.bottlemap.ui.common.BmIconId
import com.zerotoone.bottlemap.ui.theme.BottleMapPalette
import java.text.NumberFormat
import java.util.Locale

/** P18 HTML uses the same approved Cocoa Charcoal semantic palette as design.md. */
internal val P18Bg get() = BottleMapPalette.canvas
internal val P18Surface get() = BottleMapPalette.surface
internal val P18Elevated get() = BottleMapPalette.surfaceElevated
internal val P18Text get() = BottleMapPalette.textPrimary
internal val P18Muted get() = BottleMapPalette.textSecondary
internal val P18Gold get() = BottleMapPalette.primary
internal val P18Line get() = BottleMapPalette.outlineVariant
internal val P18Soft get() = BottleMapPalette.surfaceVariant

@Composable
internal fun P18Back(onClick: () -> Unit, dark: Boolean = false, modifier: Modifier = Modifier) {
    Box(modifier.size(48.dp)
        .then(if (dark) Modifier.background(P18Bg, RoundedCornerShape(12.dp)) else Modifier)
        .clickable(onClick = onClick).testTag("customer-back"),
        contentAlignment = Alignment.Center) {
        BmIcon(BmIconId.BACK, "뒤로", Modifier.size(24.dp), tint = P18Text)
    }
}

@Composable
internal fun P18Photo(modifier: Modifier = Modifier, size: Dp = 64.dp) {
    Box(modifier.size(size).background(P18Soft, RoundedCornerShape(12.dp))
        .testTag("customer-photo-placeholder"), contentAlignment = Alignment.Center) {
        BmIcon(BmIconId.BAR, "매장 사진 없음", Modifier.size(24.dp), tint = P18Muted)
    }
}

@Composable
internal fun P18Action(label: String, onClick: () -> Unit,
    primary: Boolean = false, modifier: Modifier = Modifier) {
    Box(modifier.heightIn(min = 48.dp)
        .background(if (primary) P18Gold else P18Surface, RoundedCornerShape(12.dp))
        .then(if (primary) Modifier else Modifier.border(1.dp, P18Line, RoundedCornerShape(12.dp)))
        .clickable(onClick = onClick).padding(horizontal = 12.dp),
        contentAlignment = Alignment.Center) {
        Text(label, fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
            color = if (primary) BottleMapPalette.onPrimary else P18Text)
    }
}

@Composable
internal fun P18Message(title: String, description: String, action: String,
    onAction: () -> Unit, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(horizontal = 28.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally) {
        Text(title, style = MaterialTheme.typography.headlineSmall, color = P18Text,
            lineHeight = 32.sp, textAlign = TextAlign.Center)
        Spacer(Modifier.height(12.dp))
        Text(description, color = P18Muted, fontSize = 14.sp, lineHeight = 21.sp,
            textAlign = TextAlign.Center)
        Spacer(Modifier.height(32.dp))
        P18Action(action, onAction, primary = true, modifier = Modifier.fillMaxWidth())
    }
}

@Composable
internal fun P18SearchField(
    query: String, onQuery: (String) -> Unit, onSubmit: () -> Unit,
    placeholder: String = "위스키 이름", modifier: Modifier = Modifier,
    focused: Boolean = true,
    focusRequestToken: Int = 0,
) {
    val focusRequester = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    val focusManager = LocalFocusManager.current
    fun submit() {
        keyboard?.hide()
        focusManager.clearFocus()
        onSubmit()
    }
    LaunchedEffect(focusRequestToken) {
        if (focusRequestToken > 0) {
            focusRequester.requestFocus()
            keyboard?.show()
        }
    }
    Row(modifier.height(56.dp)
        .background(P18Surface, RoundedCornerShape(12.dp))
        .border(if (focused) 1.5.dp else 1.dp,
            if (focused) BottleMapPalette.outline else P18Line, RoundedCornerShape(12.dp))
        .padding(start = 13.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        BmIcon(BmIconId.SEARCH, null, Modifier.size(24.dp).clickable { submit() }, tint = P18Muted)
        Box(Modifier.weight(1f), contentAlignment = Alignment.CenterStart) {
            if (query.isEmpty()) Text(placeholder, fontSize = 16.sp, color = BottleMapPalette.textMuted)
            BasicTextField(query, onValueChange = { onQuery(it.take(100)) },
                modifier = Modifier.fillMaxWidth().focusRequester(focusRequester).testTag("customer-search-field"),
                singleLine = true, textStyle = TextStyle(color = P18Text, fontSize = 16.sp),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { submit() }))
        }
        if (query.isNotEmpty()) {
            Box(Modifier.size(48.dp).clickable {
                onQuery("")
                focusRequester.requestFocus()
                keyboard?.show()
            }, contentAlignment = Alignment.Center) {
                Canvas(Modifier.size(20.dp)) {
                    val width = 1.5.dp.toPx()
                    drawLine(P18Muted, androidx.compose.ui.geometry.Offset(size.width*.23f,size.height*.23f),
                        androidx.compose.ui.geometry.Offset(size.width*.77f,size.height*.77f),
                        strokeWidth=width,cap=androidx.compose.ui.graphics.StrokeCap.Round)
                    drawLine(P18Muted, androidx.compose.ui.geometry.Offset(size.width*.77f,size.height*.23f),
                        androidx.compose.ui.geometry.Offset(size.width*.23f,size.height*.77f),
                        strokeWidth=width,cap=androidx.compose.ui.graphics.StrokeCap.Round)
                }
            }
        }
    }
}

/** Exact P18 40×64 SVG geometry for the four source bottle variants. */
@Composable
internal fun P18Bottle(name: String, width: Dp = 40.dp, height: Dp = 64.dp) {
    P18ExactBottle(name,width,height)
}

internal fun p18Price(price: Int): String =
    NumberFormat.getIntegerInstance(Locale.KOREA).format(price) + "원"

/** API §3.9: temporary discount applies only at startsAt <= now < endsAt. */
internal fun p18EffectivePrice(price: Int,
    discount: com.zerotoone.bottlemap.network.BarMenuDiscountDto?,
    at: java.time.Instant = java.time.Instant.now()): Int =
    if (discount!=null && runCatching {
        at >= java.time.Instant.parse(discount.startsAt) &&
            at < java.time.Instant.parse(discount.endsAt)
    }.getOrDefault(false)) discount.discountedPriceKrw else price

/** 30ml, else nearest volume; ties prefer the larger serving, never price/ml. */
internal fun p18Representative(options: List<com.zerotoone.bottlemap.network.SearchOptionDto>)
    : com.zerotoone.bottlemap.network.SearchOptionDto? =
    options.filter { it.pourMl != null }.minWithOrNull(
        compareBy<com.zerotoone.bottlemap.network.SearchOptionDto> {
            kotlin.math.abs((it.pourMl ?: 30) - 30)
        }.thenByDescending { it.pourMl ?: 0 }
    ) ?: options.minByOrNull { it.sortOrder }
