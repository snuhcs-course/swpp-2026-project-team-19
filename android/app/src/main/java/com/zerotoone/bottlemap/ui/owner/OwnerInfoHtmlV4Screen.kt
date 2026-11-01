package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.activity.compose.BackHandler
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.data.owner.MockOwnerSnapshot
import com.zerotoone.bottlemap.data.owner.MockWeeklyHours
import com.zerotoone.bottlemap.ui.common.OwnerActionButton
import com.zerotoone.bottlemap.ui.common.OwnerHeader
import com.zerotoone.bottlemap.ui.common.OwnerLoading
import com.zerotoone.bottlemap.ui.common.OwnerTextInput
import com.zerotoone.bottlemap.ui.theme.BottleMapSpacing

/** Baseline suggestions transcribed from the final ACTION_FIRST_v4 HTML, not a server vocabulary. */
internal val OWNER_HTML_V4_TAGS = listOf(
    "위스키 전문", "칵테일", "혼술바", "조용한 분위기", "안주",
    "클래식 인테리어", "데이트", "바 좌석", "단체석",
)
private val WEEKDAY = listOf("월", "화", "수", "목", "금", "토", "일")

internal fun ownerInfoBar(state: MockOwnerLoadState): Pair<MockOwnerSnapshot, MockBar>? {
    val snapshot = when (state) {
        is MockOwnerLoadState.Ready -> state.snapshot
        is MockOwnerLoadState.Empty -> state.snapshot
        else -> return null
    }
    return snapshot to (snapshot.bars.firstOrNull { it.barId == snapshot.selectedBarId }
        ?: snapshot.bars.firstOrNull() ?: return null)
}

private fun encodeWeekday(v: MockWeeklyHours): String =
    listOf(v.isoDayOfWeek, v.closed, v.openMinutes ?: -1,
        v.closeMinutes ?: -1, v.closesNextDay).joinToString("|")

private fun decodeWeekday(v: String): MockWeeklyHours? = try {
    val parts = v.split("|")
    MockWeeklyHours(parts[0].toInt(), parts[1].toBoolean(),
        parts[2].toInt().takeIf { it >= 0 },
        parts[3].toInt().takeIf { it >= 0 },
        parts[4].toBoolean())
} catch (_: RuntimeException) { null }

private fun shortTime(v: Int?): String =
    if (v == null) "설정" else "%02d:%02d".format(v / 60, v % 60)

/**
 * ACTION_FIRST_v4 management/info is a single editor:
 * photos are managed in the dedicated immediate-save screen, while basic fields,
 * weekly schedule and tags remain one uncommitted draft until "저장하기".
 * Both toolbar and system Back discard this form (HTML has no discard dialog).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun OwnerInfoHtmlV4Screen(
    state: MockOwnerLoadState,
    viewModel: OwnerMockViewModel,
    onBack: () -> Unit,
    onPhotos: () -> Unit,
) {
    val selected = ownerInfoBar(state)
    val bar = selected?.second
    var name by rememberSaveable(bar?.barId) { mutableStateOf(bar?.name.orEmpty()) }
    var intro by rememberSaveable(bar?.barId) { mutableStateOf(bar?.description.orEmpty()) }
    var address by rememberSaveable(bar?.barId) { mutableStateOf(bar?.address.orEmpty()) }
    var phone by rememberSaveable(bar?.barId) { mutableStateOf(bar?.phone.orEmpty()) }
    var pour by rememberSaveable(bar?.barId) {
        mutableStateOf(bar?.defaultPourMl?.toString().orEmpty())
    }
    var selectedTags by rememberSaveable(bar?.barId) { mutableStateOf(bar?.tags.orEmpty()) }
    var storedHours by rememberSaveable(bar?.barId) {
        mutableStateOf(bar?.weeklyHours?.map(::encodeWeekday).orEmpty())
    }
    val weekly = storedHours.mapNotNull(::decodeWeekday)
    fun setDay(day: Int, value: MockWeeklyHours?) {
        storedHours = (weekly.filterNot { it.isoDayOfWeek == day } + listOfNotNull(value))
            .sortedBy { it.isoDayOfWeek }.map(::encodeWeekday)
    }

    var wheelDay by rememberSaveable { mutableStateOf(0) }
    var wheelPart by rememberSaveable { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf("") }
    var mapVisible by rememberSaveable { mutableStateOf(false) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var discardPrompt by rememberSaveable { mutableStateOf(false) }
    val hasEdits = bar != null && (
        name != bar.name || intro != bar.description.orEmpty() ||
        address != bar.address || phone != bar.phone.orEmpty() ||
        pour != bar.defaultPourMl?.toString().orEmpty() ||
        selectedTags != bar.tags || weekly != bar.weeklyHours
    )
    fun requestExit() { if (hasEdits) discardPrompt = true else onBack() }
    BackHandler { requestExit() }
    if (discardPrompt) {
        AlertDialog(
            onDismissRequest = { discardPrompt = false },
            containerColor = V4Color.surface,
            titleContentColor = V4Color.text,
            textContentColor = V4Color.sub,
            title = { Text("변경을 취소할까요?") },
            text = { Text("저장하지 않은 수정 사항은 사라집니다.") },
            confirmButton = { TextButton(onClick = { discardPrompt = false; onBack() }) {
                Text("변경 취소", color = V4Color.primary)
            } },
            dismissButton = { TextButton(onClick = { discardPrompt = false }) {
                Text("계속 편집", color = V4Color.text)
            } },
        )
    }

    val candidates = (OWNER_HTML_V4_TAGS + selected?.first?.bars.orEmpty().flatMap { it.tags })
        .distinctBy { it.lowercase() }
        .filterNot { candidate -> selectedTags.any { it.equals(candidate, ignoreCase = true) } }
        .filter { it.contains(query.trim(), ignoreCase = true) }
        .take(7)
    val canCreate = query.trim().isNotEmpty() &&
        (OWNER_HTML_V4_TAGS + selected?.first?.bars.orEmpty().flatMap { it.tags })
            .none { it.equals(query.trim(), ignoreCase = true) }
    val validation = barInfoError(name, intro, address, phone, pour)
        ?: weeklyHoursError(weekly)
    Column(Modifier.fillMaxSize().background(V4Color.background)) {
        OwnerHeader("매장 정보 관리", ::requestExit)
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 21.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("매장 정보 관리", fontSize = 24.sp, color = V4Color.text,
                fontFamily = FontFamily.Serif, fontWeight = FontWeight.Bold,
                lineHeight = 32.sp)
            if (bar == null) {
                when (state) {
                    is MockOwnerLoadState.Error -> {
                        Text(state.message, color = MaterialTheme.colorScheme.error)
                        OwnerActionButton("다시 시도", viewModel::retry)
                    }
                    MockOwnerLoadState.Loading -> OwnerLoading("매장 정보 불러오는 중")
                    else -> Text("관리할 매장이 없어요.")
                }
            } else {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("매장 사진", fontSize = 16.sp, color = V4Color.text,
                        fontWeight = FontWeight.Bold)
                    TextButton(onClick = onPhotos) { Text("편집 ›", color = V4Color.primary, fontSize = 12.sp) }
                }
                if (bar.gallery.isEmpty()) {
                    Text("등록된 사진이 없습니다.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        bar.gallery.forEach { photo ->
                            Box(Modifier.size(153.dp, 108.dp).clip(RoundedCornerShape(12.dp))) {
                                OwnerStoredPhoto(photo.uri, Modifier.fillMaxSize())
                            }
                        }
                    }
                }

                V4FormField("매장명", name, { name = it; error = null },
                    testTag = "owner-info-name")
                V4FormField("한 줄 소개", intro, {
                    intro = it.take(100); error = null
                }, singleLine = false)
                V4FormField("매장 기본 잔 용량 (ml)", pour, {
                    pour = it.filter(Char::isDigit).take(3); error = null
                }, placeholder = "예: 30", keyboardType = KeyboardType.Number)
                V4FormField("전화번호", phone, { phone = it.take(30); error = null },
                    keyboardType = KeyboardType.Phone)
                V4FormField("주소", address, { address = it; error = null })
                Box(Modifier.fillMaxWidth().height(38.dp)
                    .background(V4Color.elevated, RoundedCornerShape(8.dp))
                    .border(1.dp, V4Color.line, RoundedCornerShape(8.dp))
                    .clickable { mapVisible = !mapVisible },
                    contentAlignment = Alignment.Center) {
                    Text("⌖  " + (if (mapVisible) "위치 접기" else "위치 확인"),
                        color = V4Color.text, fontSize = 12.sp)
                }
                if (mapVisible) {
                    Box(Modifier.fillMaxWidth().height(155.dp)
                        .background(V4Color.surface, RoundedCornerShape(8.dp)),
                        contentAlignment = Alignment.Center) {
                        Text("위치 미리보기", color = V4Color.sub, fontSize = 12.sp)
                    }
                }

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("정규 영업시간", fontSize = 16.sp, color = V4Color.text,
                        fontWeight = FontWeight.Bold)
                    TextButton(onClick = {
                        storedHours = copyMondayToWeekdays(weekly).map(::encodeWeekday)
                        error = null
                    }) { Text("평일에 복사", color = V4Color.primary, fontSize = 12.sp) }
                }

                WEEKDAY.forEachIndexed { index, dayName ->
                    val day = index + 1
                    val setting = weekly.firstOrNull { it.isoDayOfWeek == day }
                    Column(Modifier.fillMaxWidth()) {
                        BoxWithConstraints {
                            val wrapControls = maxWidth < 335.dp
                            Column {
                                Row(Modifier.fillMaxWidth().heightIn(min = 49.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                                    Text(dayName, fontSize = 13.sp, color = V4Color.text,
                                        fontWeight = FontWeight.Bold, modifier = Modifier.width(22.dp))
                                    V4CompactCheck("휴무", setting?.closed == true) { isClosed ->
                                        setDay(day, if (isClosed) MockWeeklyHours(day, true) else null)
                                        error = null
                                    }
                                    if (!wrapControls && setting?.closed != true) {
                                        Spacer(Modifier.weight(1f))
                                        V4HoursControls(
                                            setting = setting, day = day,
                                            onTime = { side -> wheelDay = day; wheelPart = side },
                                            onNextDay = { checked ->
                                                setDay(day, (setting ?: MockWeeklyHours(day, false))
                                                    .copy(closesNextDay = checked))
                                            })
                                    }
                                }
                                if (wrapControls && setting?.closed != true) {
                                    Row(Modifier.fillMaxWidth().padding(bottom = 8.dp),
                                        horizontalArrangement = Arrangement.End) {
                                        V4HoursControls(
                                            setting = setting, day = day,
                                            onTime = { side -> wheelDay = day; wheelPart = side },
                                            onNextDay = { checked ->
                                                setDay(day, (setting ?: MockWeeklyHours(day, false))
                                                    .copy(closesNextDay = checked))
                                            })
                                    }
                                }
                            }
                        }
                        if (wheelDay == day && setting?.closed != true) {
                            val current = if (wheelPart == "open") setting?.openMinutes
                                else setting?.closeMinutes
                            val selectedMinute = current ?: 18 * 60
                            Column(
                                Modifier.fillMaxWidth().background(
                                    V4Color.surface, RoundedCornerShape(10.dp)).padding(10.dp),
                                verticalArrangement = Arrangement.spacedBy(7.dp),
                            ) {
                                Text(dayName + "요일 " +
                                    (if (wheelPart == "open") "시작" else "종료") + " 시간 · 5분 단위",
                                    fontSize = 11.sp, color = V4Color.sub)
                                key(day, wheelPart) {
                                    OwnerQuickTimeWheel(selectedMinute / 60, selectedMinute % 60) {
                                        hour, minute ->
                                        val old = setting ?: MockWeeklyHours(day, closed = false)
                                        setDay(day, if (wheelPart == "open")
                                            old.copy(openMinutes = hour * 60 + minute)
                                        else old.copy(closeMinutes = hour * 60 + minute))
                                        wheelDay = 0
                                        wheelPart = ""
                                        error = null
                                    }
                                }
                            }
                        }
                        Spacer(Modifier.fillMaxWidth().height(1.dp).background(V4Color.line))
                    }
                }
                Spacer(Modifier.height(2.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("매장 태그", color = V4Color.text, fontSize = 16.sp,
                        fontWeight = FontWeight.Bold)
                    Text(selectedTags.size.toString() + "/5",
                        style = MaterialTheme.typography.labelMedium)
                }
                if (selectedTags.isEmpty()) {
                    Text("선택한 태그가 없습니다.", style = MaterialTheme.typography.bodySmall)
                } else {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        selectedTags.forEach { tag ->
                            OutlinedButton(
                                modifier = Modifier.widthIn(max = 250.dp),
                                onClick = {
                                    selectedTags = selectedTags.filterNot { it == tag }
                                    error = null
                                },
                                contentPadding = PaddingValues(horizontal = 9.dp, vertical = 2.dp),
                            ) { Text(tag + " ×", style = MaterialTheme.typography.labelSmall,
                                    maxLines = 2, overflow = TextOverflow.Ellipsis) }
                        }
                    }
                }
                OutlinedTextField(
                    value = query, onValueChange = { query = it.take(24) },
                    label = { Text("태그 검색 또는 새 태그 입력") },
                    singleLine = true, modifier = Modifier.fillMaxWidth()
                        .testTag("owner-tag-search"),
                )
                if (candidates.isEmpty() && query.isNotBlank()) {
                    Text("검색 결과가 없습니다.", style = MaterialTheme.typography.labelSmall)
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    candidates.forEach { candidate ->
                        OutlinedButton(
                            modifier = Modifier.widthIn(max = 250.dp),
                            onClick = {
                                val next = toggleBarTag(selectedTags, candidate)
                                if (next == null) error = "태그는 최대 5개까지 등록할 수 있어요."
                                else { selectedTags = next; query = ""; error = null }
                            },
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 1.dp),
                        ) {
                            Text(candidate + " ＋", style = MaterialTheme.typography.labelSmall,
                                maxLines = 2, overflow = TextOverflow.Ellipsis)
                        }
                    }
                    if (canCreate) {
                        OutlinedButton(
                            modifier = Modifier.widthIn(max = 250.dp),
                            onClick = {
                                val next = toggleBarTag(selectedTags, query)
                                if (next == null) error = "태그는 최대 5개까지 등록할 수 있어요."
                                else { selectedTags = next; query = ""; error = null }
                            },
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 1.dp),
                        ) {
                            Text("“" + query.trim() + "” 새 태그 등록 ＋",
                                style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }

                validation?.let {
                    Text(it, color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall)
                }
                error?.let {
                    Text(it, color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall)
                }
                OwnerActionButton("저장하기", {
                    try {
                        val modified = withBarInfo(bar, name, intro, address, phone, pour)
                            .copy(tags = selectedTags)
                        viewModel.saveBar(withWeeklyHours(modified, weekly))
                        onBack()
                    } catch (e: Exception) {
                        error = e.message ?: "저장에 실패했습니다. 다시 시도해 주세요."
                    }
                }, Modifier.fillMaxWidth().testTag("owner-info-save"),
                    enabled = validation == null)
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}


@Composable
private fun V4HoursControls(
    setting: MockWeeklyHours?,
    day: Int,
    onTime: (String) -> Unit,
    onNextDay: (Boolean) -> Unit,
) {
    Row(verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        V4HourButton(setting?.openMinutes?.let { "%02d:%02d".format(it/60,it%60) } ?: "설정",
            onClick = { onTime("open") })
        Text("–", color = V4Color.text, fontSize = 13.sp)
        V4HourButton(setting?.closeMinutes?.let { "%02d:%02d".format(it/60,it%60) } ?: "설정",
            onClick = { onTime("close") })
        V4CompactCheck("익일", setting?.closesNextDay == true, onNextDay)
    }
}
