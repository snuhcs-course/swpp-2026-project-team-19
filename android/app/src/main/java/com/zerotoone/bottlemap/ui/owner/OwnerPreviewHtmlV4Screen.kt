package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.weight
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.input.pointer.consume
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
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
@Composable
fun OwnerPreviewHtmlV4Screen(
    state: MockOwnerLoadState,
    viewModel: OwnerMockViewModel,
    onBack: () -> Unit,
) {
    val bar = ownerInfoBar(state)?.second
    var photoIndex by rememberSaveable(bar?.barId) { mutableIntStateOf(0) }
    var fullImage by rememberSaveable { mutableStateOf(false) }
    var expanded by rememberSaveable { mutableStateOf("") }
    var noteVisible by rememberSaveable { mutableStateOf(false) }
    var menuSearch by rememberSaveable { mutableStateOf("") }
    var drag by remember { mutableFloatStateOf(0f) }
    val clipboard = LocalClipboardManager.current
    val now = System.currentTimeMillis()
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
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("고객 페이지 미리보기", onBack)
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(horizontal = BottleMapSpacing.screenHorizontal),
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
                Text(bar.name, style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold)
                Box(
                    Modifier.fillMaxWidth().height(185.dp)
                        .clip(RoundedCornerShape(11.dp))
                        .background(MaterialTheme.colorScheme.surfaceVariant)
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
                    Text(it, style = MaterialTheme.typography.bodySmall)
                }
                if (bar.tags.isNotEmpty()) {
                    Text(bar.tags.take(5).joinToString("  ·  "),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary)
                }
                Row(Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { if (!activeException?.note.isNullOrBlank())
                        noteVisible = !noteVisible
                    }) {
                        Text(homeOperatingState(bar, now),
                            color = MaterialTheme.colorScheme.primary,
                            fontWeight = FontWeight.Bold)
                    }
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = {
                        expanded = if (expanded == "hours") "" else "hours"
                    }) { Text(if (expanded == "hours") "시간 접기 ⌃" else "영업시간 ⌄") }
                    TextButton(onClick = {
                        expanded = if (expanded == "address") "" else "address"
                    }) { Text("지도") }
                    TextButton(onClick = {
                        expanded = if (expanded == "phone") "" else "phone"
                    }) { Text("전화") }
                }
                if (noteVisible && !activeException?.note.isNullOrBlank()) {
                    Text("고객 안내: " + activeException?.note.orEmpty(),
                        modifier = Modifier.fillMaxWidth()
                            .background(MaterialTheme.colorScheme.surfaceVariant,
                                RoundedCornerShape(9.dp)).padding(12.dp))
                }
                when (expanded) {
                    "hours" -> {
                        val days = listOf("월", "화", "수", "목", "금", "토", "일")
                        days.forEachIndexed { index, label ->
                            val setting = bar.weeklyHours.firstOrNull {
                                it.isoDayOfWeek == index + 1
                            }
                            Row(Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween) {
                                Text(label)
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
                                })
                            }
                        }
                    }
                    "address" -> {
                        Text("위치 미리보기는 지도 연동 계약 확정 후 제공됩니다.",
                            style = MaterialTheme.typography.bodySmall)
                        Row(Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(bar.address, modifier = Modifier.weight(1f))
                            TextButton(onClick = {
                                clipboard.setText(AnnotatedString(bar.address))
                            }) { Text("복사") }
                        }
                    }
                    "phone" -> {
                        Row(Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(bar.phone ?: "전화번호 정보 없음",
                                modifier = Modifier.weight(1f))
                            TextButton(onClick = {
                                clipboard.setText(AnnotatedString(bar.phone.orEmpty()))
                            }, enabled = !bar.phone.isNullOrBlank()) { Text("복사") }
                        }
                    }
                }
                val preview = viewModel.preview(bar.barId, now)
                Text("메뉴", style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold)
                OutlinedTextField(
                    value = menuSearch,
                    onValueChange = { menuSearch = it },
                    label = { Text("메뉴 검색") },
                    modifier = Modifier.fillMaxWidth())
                val visible = preview?.visibleMenu.orEmpty().filter { menu ->
                    val product = preview?.products?.firstOrNull {
                        it.productId == menu.productId
                    }
                    product?.displayName.orEmpty().contains(menuSearch.trim(),
                        ignoreCase = true)
                }
                if (visible.isEmpty()) {
                    Text(if (menuSearch.isBlank()) "등록된 메뉴가 없어요."
                    else "검색 결과가 없어요.", style = MaterialTheme.typography.bodySmall)
                }
                visible.forEach { menu ->
                    val product = preview?.products?.firstOrNull {
                        it.productId == menu.productId
                    }
                    Column(Modifier.fillMaxWidth()
                        .background(MaterialTheme.colorScheme.surface,
                            RoundedCornerShape(10.dp)).padding(11.dp)) {
                        Text(product?.displayName ?: "상품 정보 없음",
                            style = MaterialTheme.typography.titleSmall)
                        menu.options.forEach { option ->
                            val detail = (option.pourMl?.let { it.toString() + "ml · " }
                                ?: option.label?.let { it + " · " }.orEmpty())
                            Text(detail + option.displayPrice(now).toString() + "원",
                                style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}
