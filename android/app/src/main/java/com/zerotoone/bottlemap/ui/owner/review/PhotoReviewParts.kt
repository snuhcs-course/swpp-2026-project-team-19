package com.zerotoone.bottlemap.ui.owner.review

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.ui.common.UxColor
import com.zerotoone.bottlemap.ui.common.quietClick
import com.zerotoone.bottlemap.ui.common.uxText
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

/** Review-screen colours from the v18 CSS that are not palette roles. */
internal object ReviewColor {
    val pendingBorder = Color(0xFF715640)
    val issueDivider = Color(0x7551473F)
    val pourPanelBorder = Color(0xFF927049)
    val pourPanelBg = Color(0xFF3D3026)
    val detailsBg = Color(0xFF292521)
    val detailNameBg = Color(0xFF332D28)
    val selectedBg = Color(0xFF5E4833)
    val selectedText = Color(0xFFFFE0B8)
    val primaryChoiceBorder = Color(0xFF9E7A54)
    val primaryChoiceText = Color(0xFFFFDDB0)
    val publishBorder = Color(0xFF735B43)
    val publishBg = Color(0xFF332B25)
    val publishProgress = Color(0xFF806044)
    val mergeNotice = Color(0xFFE4C397)
    val mergeButtonBg = Color(0xFF514236)
    val excludeBg = Color(0xFF382925)
    val excludeBorder = Color(0xFF745149)
    val excludeText = Color(0xFFEBD5CE)
    val categoryBorder = Color(0xFF806B55)
    val sourceBorder = Color(0xFF87715E)
    val sourceFocusBorder = Color(0xFF9D5435)
    val sourceFocusFill = Color(0x11F1E6D1)
    val sourceFocusText = Color(0xFF30251B)
    val sheetPaper = Color(0xFFE9DDC5)
    val sheetBorder = Color(0xFF9A8469)
    val sheetText = Color(0xFF443326)
    val paperA = Color(0xFFC7B59A)
    val paperB = Color(0xFFE5D7BF)
    val paperC = Color(0xFFAD9372)
    val paperLine = Color(0x186B5947)
    val photoBackdrop = Color(0xDE0B0909)
    val sheetScrim = Color(0xCA100E0D)
    val checkboxOff = Color(0xFF3B3B3B)
}

/**
 * A single-line text field drawn like the prototype's inputs. The border turns gold while
 * focused; [onFocusLost] fires when the field loses focus (the HTML `change` event).
 */
@Composable
internal fun ReviewField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String = "",
    fontSize: Float = 13f,
    fontWeight: Int = 400,
    minHeight: Dp = 48.dp,
    radius: Dp = 10.dp,
    background: Color = UxColor.elevated,
    border: Color = UxColor.outline,
    invalid: Boolean = false,
    paddingStart: Dp = 13.dp,
    paddingEnd: Dp = 13.dp,
    keyboardType: KeyboardType = KeyboardType.Text,
    imeAction: ImeAction = ImeAction.Done,
    onImeAction: (() -> Unit)? = null,
    onFocusLost: (() -> Unit)? = null,
    focusRequester: FocusRequester? = null,
    enabled: Boolean = true,
    trailing: (@Composable (focused: Boolean) -> Unit)? = null,
) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(radius)
    BasicTextField(
        value = value,
        onValueChange = onValueChange,
        enabled = enabled,
        singleLine = true,
        textStyle = uxText(fontSize, fontWeight, if (enabled) UxColor.text else UxColor.muted),
        cursorBrush = SolidColor(UxColor.gold),
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType, imeAction = imeAction),
        keyboardActions = KeyboardActions(onAny = { onImeAction?.invoke() }),
        modifier = modifier
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .onFocusChanged { state ->
                if (focused && !state.isFocused) onFocusLost?.invoke()
                focused = state.isFocused
            },
        decorationBox = { inner ->
            Box(
                Modifier.fillMaxWidth().heightIn(min = minHeight)
                    .background(background, shape)
                    .border(
                        if (focused) 2.dp else 1.dp,
                        when {
                            focused -> UxColor.gold
                            invalid -> UxColor.error
                            else -> border
                        },
                        shape,
                    ),
                contentAlignment = Alignment.CenterStart,
            ) {
                Box(Modifier.fillMaxWidth().padding(start = paddingStart, end = paddingEnd)) {
                    if (value.isEmpty() && placeholder.isNotEmpty()) {
                        Text(placeholder, style = uxText(fontSize, 400, UxColor.muted.copy(alpha = 0.75f)),
                            maxLines = 1)
                    }
                    inner()
                }
                if (trailing != null) Box(Modifier.align(Alignment.CenterEnd)) { trailing(focused) }
            }
        },
    )
}

/** `.choice`: small outlined decision button. */
@Composable
internal fun ReviewChoice(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    selected: Boolean = false,
    minHeight: Dp = 48.dp,
    fontSize: Float = 11f,
    horizontalPadding: Dp = 10.dp,
    verticalPadding: Dp = 7.dp,
    textAlign: TextAlign = TextAlign.Center,
    contentAlignment: Alignment = Alignment.Center,
    testTag: String? = null,
) {
    val shape = RoundedCornerShape(9.dp)
    Box(
        modifier.heightIn(min = minHeight)
            .background(if (selected) ReviewColor.selectedBg else UxColor.elevated, shape)
            .border(if (selected) 2.dp else 1.dp, if (selected) UxColor.gold else UxColor.outline, shape)
            .then(Modifier.quietReviewClick(onClick))
            .then(if (testTag != null) Modifier.testTag(testTag) else Modifier)
            .padding(horizontal = horizontalPadding, vertical = verticalPadding),
        contentAlignment = contentAlignment,
    ) {
        Text(text, style = uxText(fontSize, 700, if (selected) ReviewColor.selectedText else UxColor.text),
            textAlign = textAlign)
    }
}

@Composable
internal fun Modifier.quietReviewClick(onClick: () -> Unit): Modifier =
    this.then(Modifier.quietClick(onClick = onClick))

/**
 * Mock menu-photo crop (`.source-visual`). The prototype has no real photos: it draws a
 * paper-coloured crop with the scanned line framed, or the whole sheet when the line's
 * position is unknown. The real implementation will draw the photo crop here.
 */
@Composable
internal fun SourceVisual(
    raw: String,
    hasBox: Boolean,
    modifier: Modifier = Modifier,
    height: Dp,
    large: Boolean = false,
) {
    Box(
        modifier.fillMaxWidth().height(height)
            .clip(RoundedCornerShape(8.dp))
            .border(1.dp, ReviewColor.sourceBorder, RoundedCornerShape(8.dp)),
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val w = size.width
            val h = size.height
            fun cssLinear(angleDeg: Double): Pair<Offset, Offset> {
                val a = Math.toRadians(angleDeg)
                val dx = sin(a).toFloat()
                val dy = -cos(a).toFloat()
                val len = abs(w * dx) + abs(h * dy)
                val c = Offset(w / 2, h / 2)
                return Offset(c.x - dx * len / 2, c.y - dy * len / 2) to Offset(c.x + dx * len / 2, c.y + dy * len / 2)
            }
            val (start, end) = cssLinear(115.0)
            drawRect(Brush.linearGradient(
                0f to ReviewColor.paperA, 0.30f to ReviewColor.paperB, 0.90f to ReviewColor.paperC, 1f to ReviewColor.paperC,
                start = start, end = end,
            ))
            // repeating-linear-gradient(100deg, transparent 0 19px, line 20px 21px)
            val a = Math.toRadians(100.0)
            val dx = sin(a).toFloat()
            val dy = -cos(a).toFloat()
            val len = abs(w * dx) + abs(h * dy)
            val c = Offset(w / 2, h / 2)
            val origin = Offset(c.x - dx * len / 2, c.y - dy * len / 2)
            val px = density
            var t = 20f * px
            val perp = Offset(-dy, dx) * (w + h)
            while (t < len) {
                val p = origin + Offset(dx, dy) * t
                drawLine(ReviewColor.paperLine, p - perp, p + perp, strokeWidth = 1f * px)
                t += 21f * px
            }
        }
        if (hasBox) {
            Box(
                Modifier.fillMaxSize().padding(horizontal = 9.dp, vertical = 10.dp)
                    .rotate(-0.4f)
                    .background(ReviewColor.sourceFocusFill, RoundedCornerShape(3.dp))
                    .border(1.7.dp, ReviewColor.sourceFocusBorder, RoundedCornerShape(3.dp)),
                contentAlignment = Alignment.Center,
            ) {
                Text(raw, style = uxText(13f, 700, ReviewColor.sourceFocusText, lineHeight = 1.45f, serif = true,
                    letterSpacing = 0.15.sp), maxLines = 1, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(horizontal = 2.dp))
            }
        } else {
            BoxWithConstraints(Modifier.fillMaxSize()) {
                val side = maxWidth * (if (large) 0.09f else 0.16f)
                Column(
                    Modifier.fillMaxSize().padding(horizontal = side, vertical = if (large) 10.dp else 8.dp)
                        .rotate(-1f)
                        .background(ReviewColor.sheetPaper)
                        .border(1.dp, ReviewColor.sheetBorder),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(if (large) 12.dp else 3.dp, Alignment.CenterVertically),
                ) {
                    Text("WHISKY · DRINKS", style = uxText(if (large) 16f else 10f, 700, ReviewColor.sheetText,
                        serif = true, letterSpacing = 1.sp))
                    Text(raw, style = uxText(if (large) 12f else 8f, 700, ReviewColor.sheetText), maxLines = 1,
                        overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(horizontal = 4.dp))
                    Text(if (large) "— 메뉴판 모의 이미지 —" else "— 가격 및 상품 정보 —",
                        style = uxText(if (large) 12f else 8f, 700, ReviewColor.sheetText), maxLines = 1)
                }
            }
        }
    }
}

/** Native-looking 19dp checkbox with the gold accent (`.bottle-check input`). */
@Composable
internal fun ReviewCheckbox(checked: Boolean, modifier: Modifier = Modifier) {
    Box(
        modifier.size(19.dp)
            .background(if (checked) UxColor.gold else ReviewColor.checkboxOff, RoundedCornerShape(3.dp))
            .border(1.dp, if (checked) UxColor.gold else UxColor.muted, RoundedCornerShape(3.dp)),
        contentAlignment = Alignment.Center,
    ) {
        if (checked) com.zerotoone.bottlemap.ui.common.BmLineIcon(
            com.zerotoone.bottlemap.ui.common.BmLineIconId.CHECK, 15.dp, UxColor.goldOn)
    }
}
