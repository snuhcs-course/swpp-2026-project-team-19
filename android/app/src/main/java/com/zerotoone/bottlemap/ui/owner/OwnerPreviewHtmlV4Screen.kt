package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.sp
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.zerotoone.bottlemap.data.owner.MockExceptionKind
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.ui.common.OwnerHeader
import com.zerotoone.bottlemap.ui.common.OwnerLoading
import com.zerotoone.bottlemap.ui.theme.BottleMapSpacing

/**
 * Customer-side MOCK preview, not the API-backed customer detail screen.
 * All text, hero ordering, photo URIs, schedule, tags and menu come from
 * the existing shared owner snapshot. Mirrors ACTION_FIRST_v4 preview hierarchy.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun OwnerPreviewHtmlV4Screen(
    state: MockOwnerLoadState,
    viewModel: OwnerMockViewModel,
    onBack: () -> Unit,
    onManage: () -> Unit = onBack,
) {
    val bar = ownerInfoBar(state)?.second
    var photoIndex by rememberSaveable(bar?.barId) { mutableIntStateOf(0) }
    var fullImage by rememberSaveable { mutableStateOf(false) }
    var expanded by rememberSaveable { mutableStateOf("") }
    var noteVisible by rememberSaveable { mutableStateOf(false) }
    var drag by remember { mutableFloatStateOf(0f) }
    val clipboard = LocalClipboardManager.current
    val now = rememberOwnerNow()
    val activeException = bar?.let { homeOperatingException(it, now) }?.takeIf {
        ownerToday(now).toEpochDay() in it.fromEpochDay..it.toEpochDay ||
            (it.kind == MockExceptionKind.CUSTOM_HOURS && it.closesNextDay &&
                it.toEpochDay == ownerToday(now).toEpochDay() - 1)
    }
    val photoCount = bar?.gallery?.size ?: 0
    val safeIndex = if (photoCount == 0) 0 else photoIndex.mod(photoCount)
    fun select(index: Int) {
        if (photoCount > 0) photoIndex = (index + photoCount).mod(photoCount)
    }
    if (fullImage && bar != null && bar.gallery.isNotEmpty()) {
        Dialog(
            onDismissRequest = { fullImage = false },
            properties = DialogProperties(usePlatformDefaultWidth = false),
        ) {
            Column(
                Modifier.fillMaxWidth().fillMaxHeight(0.85f).padding(16.dp)
                    .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp))
                    .padding(12.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = { fullImage = false }) { Text("닫기 ×") }
                }
                Box(Modifier.fillMaxWidth().weight(1f).clip(RoundedCornerShape(9.dp))) {
                    OwnerStoredPhoto(bar.gallery[safeIndex].uri, Modifier.fillMaxSize(),
                        ContentScale.Fit)
                }
                Row(Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { select(photoIndex - 1) }, enabled = photoCount > 1) {
                        Text("‹ 이전")
                    }
                    Text((safeIndex + 1).toString() + " / " + photoCount)
                    TextButton(onClick = { select(photoIndex + 1) }, enabled = photoCount > 1) {
                        Text("다음 ›")
                    }
                }
            }
        }
    }
    Column(Modifier.fillMaxSize().background(V4Color.background)) {
        V4Toolbar(null, onBack)
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 13.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (bar == null) {
                when (state) {
                    is MockOwnerLoadState.Error -> {
                        Text(state.message, color = MaterialTheme.colorScheme.error)
                        TextButton(onClick = viewModel::retry) { Text("다시 시도") }
                    }
                    MockOwnerLoadState.Loading -> OwnerLoading("고객 미리보기 불러오는 중")
                    else -> Text("관리할 매장이 없어요.")
                }
            } else {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(bar.name, color = V4Color.text, fontSize = 22.sp,
                        fontFamily = FontFamily.Serif, fontWeight = FontWeight.Bold,
                        modifier = Modifier.weight(1f))
                    Box(Modifier.background(V4Color.background, RoundedCornerShape(8.dp))
                        .border(1.dp, V4Color.line, RoundedCornerShape(8.dp))
                        .clickable(onClick = onManage)
                        .padding(horizontal = 10.dp, vertical = 9.dp)
                        .testTag("owner-preview-manage"), contentAlignment = Alignment.Center) {
                        Text("← 관리", fontSize = 11.sp, color = V4Color.sub)
                    }
                }
                Box(
                    Modifier.fillMaxWidth().height(185.dp)
                        .clip(RoundedCornerShape(11.dp))
                        .background(Color(0xFF4A382A))
                        .pointerInput(photoCount, safeIndex) {
                            detectHorizontalDragGestures(
                                onDragStart = { drag = 0f },
                                onHorizontalDrag = { change, delta ->
                                    drag += delta
                                    change.consume()
                                },
                                onDragEnd = {
                                    if (drag > 55f) select(photoIndex - 1)
                                    if (drag < -55f) select(photoIndex + 1)
                                    drag = 0f
                                },
                            )
                        }
                        .clickable(enabled = photoCount > 0) { fullImage = true }
                        .testTag("owner-customer-hero"),
                ) {
                    if (photoCount > 0) {
                        OwnerStoredPhoto(bar.gallery[safeIndex].uri, Modifier.fillMaxSize(),
                            ContentScale.Fit)
                    } else {
                        Text("매장 사진이 없어요.", modifier = Modifier.align(Alignment.Center))
                    }
                    Text((if (photoCount == 0) 0 else safeIndex + 1).toString() +
                        "/" + photoCount,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.align(Alignment.BottomEnd)
                            .background(MaterialTheme.colorScheme.surface)
                            .padding(5.dp))
                }
                if (photoCount > 1) {
                    Row(Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center) {
                        bar.gallery.forEachIndexed { index, _ ->
                            TextButton(onClick = { select(index) }) {
                                Text(if (safeIndex == index) "●" else "○",
                                    color = if (safeIndex == index)
                                        MaterialTheme.colorScheme.primary
                                    else MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
                bar.description?.takeIf { it.isNotBlank() }?.let {
                    Text(it, color = V4Color.sub, fontSize = 12.sp)
                }
                if (bar.tags.isNotEmpty()) {
                    FlowRow(Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        bar.tags.take(5).forEach { tag ->
                            Box(Modifier.background(V4Color.elevated,
                                RoundedCornerShape(50))
                                .border(1.dp, V4Color.line, RoundedCornerShape(50))
                                .padding(horizontal = 9.dp, vertical = 4.dp)) {
                                Text(tag, color = V4Color.text, fontSize = 11.sp)
                            }
                        }
                    }
                }
                Row(Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(7.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Row(Modifier.weight(1f),
                        horizontalArrangement = Arrangement.spacedBy(5.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Text(homeOperatingState(bar, now),
                            color = V4Color.positive, fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.clickable {
                                if (!activeException?.note.isNullOrBlank())
                                    noteVisible = !noteVisible
                            })
                        ownerPreviewNextText(bar, now).takeIf { it.isNotEmpty() }?.let {
                            Text(it, color = V4Color.sub, fontSize = 11.sp,
                                maxLines = 1)
                        }
                        Canvas(Modifier.size(22.dp)
                            .clickable { expanded = if (expanded == "hours") "" else "hours" }
                            .semantics { contentDescription = "전체 영업시간 보기" }
                            .testTag("owner-preview-hours-toggle")) {
                            val leftY = if (expanded == "hours") 0.65f else 0.35f
                            val centerY = if (expanded == "hours") 0.35f else 0.65f
                            val stroke = 2.dp.toPx()
                            drawLine(V4Color.primary,
                                Offset(size.width * .18f, size.height * leftY),
                                Offset(size.width * .50f, size.height * centerY),
                                strokeWidth = stroke, cap = StrokeCap.Round)
                            drawLine(V4Color.primary,
                                Offset(size.width * .50f, size.height * centerY),
                                Offset(size.width * .82f, size.height * leftY),
                                strokeWidth = stroke, cap = StrokeCap.Round)
                        }
                    }
                    V4PreviewSmallButton("지도", "location") {
                        expanded = if (expanded == "address") "" else "address"
                    }
                    V4PreviewSmallButton("전화", "phone") {
                        expanded = if (expanded == "phone") "" else "phone"
                    }
                }
                if (noteVisible && !activeException?.note.isNullOrBlank()) {
                    Text("고객 안내: " + activeException?.note.orEmpty(),
                        modifier = Modifier.fillMaxWidth()
                            .background(MaterialTheme.colorScheme.surfaceVariant,
                                RoundedCornerShape(9.dp)).padding(12.dp))
                }
                when (expanded) {
                    "hours" -> {
                        Column(Modifier.fillMaxWidth().background(V4Color.surface,
                            RoundedCornerShape(9.dp)).padding(horizontal = 12.dp, vertical = 10.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            val days = listOf("월", "화", "수", "목", "금", "토", "일")
                            days.forEachIndexed { index, label ->
                                val setting = bar.weeklyHours.firstOrNull {
                                    it.isoDayOfWeek == index + 1
                                }
                                Row(Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween) {
                                    Text(label, color = V4Color.sub, fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold)
                                    Text(when {
                                        setting == null -> "미설정"
                                        setting.closed -> "휴무"
                                        else -> {
                                            val start = setting.openMinutes
                                            val end = setting.closeMinutes
                                            if (start == null || end == null) "미설정"
                                            else "%02d:%02d – %s%02d:%02d".format(
                                                start / 60, start % 60,
                                                if (setting.closesNextDay) "익일 " else "",
                                                end / 60, end % 60)
                                        }
                                    }, color = V4Color.text, fontSize = 11.sp)
                                }
                            }
                        }
                    }
                    "address" -> {
                        Column(Modifier.fillMaxWidth().background(V4Color.surface,
                            RoundedCornerShape(9.dp)).padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Box(Modifier.fillMaxWidth().height(190.dp)
                                .clip(RoundedCornerShape(9.dp))
                                .background(Color(0xFF7D7060)), contentAlignment = Alignment.Center) {
                                Canvas(Modifier.fillMaxSize()) {
                                    drawLine(Color(0xFFD8D0C6),
                                        Offset(size.width * -.1f, size.height * 1.18f),
                                        Offset(size.width * 1.1f, size.height * -.1f),
                                        strokeWidth = 34.dp.toPx())
                                    drawLine(Color(0xFFD8D0C6),
                                        Offset(size.width * .45f, size.height * -.2f),
                                        Offset(size.width * .28f, size.height * 1.2f),
                                        strokeWidth = 24.dp.toPx())
                                }
                                Box(Modifier.background(V4Color.background, RoundedCornerShape(50))
                                    .border(2.dp, V4Color.primary, RoundedCornerShape(50))
                                    .padding(horizontal = 11.dp, vertical = 6.dp)) {
                                    Text(bar.name, color = V4Color.text, fontSize = 12.sp,
                                        fontWeight = FontWeight.Medium)
                                }
                            }
                            Row(Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(9.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                V4PreviewGlyph("location", Modifier.size(17.dp), accent = true)
                                Text(bar.address, color = V4Color.text, fontSize = 12.sp,
                                    modifier = Modifier.weight(1f))
                                V4PreviewCopy("복사", { clipboard.setText(AnnotatedString(bar.address)) })
                            }
                        }
                    }
                    "phone" -> {
                        Row(Modifier.fillMaxWidth()
                            .background(V4Color.surface, RoundedCornerShape(9.dp))
                            .padding(horizontal = 14.dp, vertical = 12.dp),
                            horizontalArrangement = Arrangement.spacedBy(9.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            V4PreviewGlyph("phone", Modifier.size(17.dp), accent = true)
                            Text(bar.phone ?: "전화번호 정보 없음",
                                color = V4Color.text, fontSize = 12.sp,
                                modifier = Modifier.weight(1f))
                            V4PreviewCopy("복사", {
                                clipboard.setText(AnnotatedString(bar.phone.orEmpty()))
                            }, enabled = !bar.phone.isNullOrBlank())
                        }
                    }
                }
                val preview = viewModel.preview(bar.barId, now)
                OwnerPreviewV4Menu(
                    bar = bar,
                    preview = preview,
                    brandCatalog = ownerInfoBar(state)?.first?.brands.orEmpty(),
                    nowEpochMs = now,
                )
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}


@Composable
private fun V4PreviewSmallButton(label: String, kind: String, onClick: () -> Unit) {
    Row(Modifier.background(V4Color.surface, RoundedCornerShape(7.dp))
        .border(1.dp, V4Color.line, RoundedCornerShape(7.dp))
        .clickable(onClick = onClick)
        .padding(horizontal = 7.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        V4PreviewGlyph(kind, Modifier.size(15.dp))
        Text(label, fontSize = 11.sp, color = V4Color.text, maxLines = 1)
    }
}

@Composable
private fun V4PreviewCopy(label: String, onClick: () -> Unit, enabled: Boolean = true) {
    Box(Modifier.background(V4Color.elevated, RoundedCornerShape(7.dp))
        .border(1.dp, V4Color.line, RoundedCornerShape(7.dp))
        .clickable(enabled = enabled, onClick = onClick)
        .padding(horizontal = 10.dp, vertical = 7.dp)) {
        Text(label, fontSize = 11.sp,
            color = if (enabled) V4Color.primary else V4Color.sub)
    }
}

/** Matching line-art glyphs for HTML-v4. The supplied brand-logo ZIP has no map/phone icons. */
@Composable
private fun V4PreviewGlyph(kind: String, modifier: Modifier = Modifier, accent: Boolean = false) {
    Canvas(modifier) {
        val u = size.minDimension / 24f
        val tint = if (accent) V4Color.primary else V4Color.sub
        val path = Path()
        if (kind == "location") {
            path.moveTo(12*u, 22*u)
            path.cubicTo(9*u, 18*u, 4*u, 13*u, 4*u, 9*u)
            path.cubicTo(4*u, 4*u, 7*u, 2*u, 12*u, 2*u)
            path.cubicTo(17*u, 2*u, 20*u, 4*u, 20*u, 9*u)
            path.cubicTo(20*u, 13*u, 15*u, 18*u, 12*u, 22*u)
            drawPath(path, tint, style = Stroke(
                width = 1.8.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
            drawCircle(tint, radius = 2.5*u, center = Offset(12*u, 9*u),
                style = Stroke(width = 1.8.dp.toPx()))
        } else {
            // Curves reproduce the handset from HTML's BM_PATHS.phone.
            path.moveTo(5*u, 4.5f*u)
            path.lineTo(8.5f*u, 8*u)
            path.lineTo(6.8f*u, 10*u)
            path.cubicTo(8.4f*u, 13.6f*u, 10.4f*u, 15.6f*u, 14*u, 17.2f*u)
            path.lineTo(16*u, 15.5f*u)
            path.lineTo(19.5f*u, 19*u)
            path.cubicTo(20.6f*u, 20.3f*u, 19.1f*u, 21.7f*u, 17.5f*u, 21*u)
            path.cubicTo(10*u, 20*u, 4*u, 14*u, 3*u, 6.5f*u)
            path.cubicTo(2.7f*u, 4.7f*u, 3.5f*u, 3.8f*u, 5*u, 4.5f*u)
            path.close()
            drawPath(path, tint, style = Stroke(
                width = 1.8.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        }
    }
}
