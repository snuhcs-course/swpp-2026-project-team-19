package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.gestures.snapping.rememberSnapFlingBehavior
import androidx.compose.foundation.gestures.snapping.SnapPosition
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.runtime.snapshotFlow
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.remember
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import java.time.LocalDate
import java.time.YearMonth
import java.time.DayOfWeek
import java.time.format.DateTimeFormatter
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.key
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.Color
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.zerotoone.bottlemap.data.owner.*
import com.zerotoone.bottlemap.ui.common.*
import com.zerotoone.bottlemap.ui.theme.BottleMapSpacing
import java.time.Instant
import java.time.ZoneOffset
import java.util.UUID

private fun activeBar(state: MockOwnerLoadState): Pair<MockOwnerSnapshot, MockBar>? {
    val snapshot = when (state) {
        is MockOwnerLoadState.Ready -> state.snapshot
        is MockOwnerLoadState.Empty -> state.snapshot
        else -> return null
    }
    val bar = snapshot.bars.firstOrNull { it.barId == snapshot.selectedBarId }
        ?: snapshot.bars.firstOrNull() ?: return null
    return snapshot to bar
}

@Composable
private fun OwnerManagerIcon(icon: BmIconId) {
    Box(
        modifier = Modifier.size(32.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(8.dp)),
        contentAlignment = Alignment.Center
    ) { BmIcon(icon, null, Modifier.size(21.dp), tint = MaterialTheme.colorScheme.primary) }
}

@Composable
private fun OwnerQuickCard(
    modifier: Modifier, icon: BmIconId, title: String, footer: String, onClick: () -> Unit,
) {
    Surface(
        modifier = modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surface
    ) {
        Column(
            Modifier.fillMaxSize().padding(horizontal = 10.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                OwnerManagerIcon(icon)
                Text(title, modifier = Modifier.weight(1f), style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold, maxLines = 1)
            }
            OwnerManagerFooter(footer, onClick)
        }
    }
}

@Composable
private fun OwnerManagerFooter(label: String, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().height(36.dp).clickable(onClick = onClick),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(3.dp)
    ) {
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2)
        Text("›", style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun OwnerManagementHomeScreen(
    state: MockOwnerLoadState,
    viewModel: OwnerMockViewModel,
    onRetry: () -> Unit,
    onBack: () -> Unit,
    onPreview: () -> Unit,
    onInfo: () -> Unit,
    onStatus: () -> Unit,
    onMenu: () -> Unit,
    onJob: (MockImportStatus) -> Unit,
) {
    val selected = activeBar(state)
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    val now = System.currentTimeMillis()
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("매장 관리", onBack)
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(horizontal = BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            when {
                state == MockOwnerLoadState.Loading -> OwnerLoading("매장 정보 불러오는 중")
                state is MockOwnerLoadState.Error -> {
                    Text(state.message, color = MaterialTheme.colorScheme.error)
                    OwnerActionButton("다시 시도", onRetry)
                }
                selected == null -> {
                    Text("관리할 매장이 없어요.", style = MaterialTheme.typography.titleMedium)
                    OwnerActionButton("돌아가기", onBack)
                }
                else -> {
                    val (snapshot, bar) = selected
                    val exception = homeOperatingException(bar, now)
                    val job = latestOwnerImport(snapshot.imports, bar.barId)
                    val (ageDays, freshness) = ownerMenuFreshness(bar, now)
                    Row(
                        Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(
                            bar.name, modifier = Modifier.weight(1f),
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold
                        )
                        OutlinedButton(
                            onClick = onPreview,
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)
                        ) {
                            BmIcon(BmIconId.SEARCH, null, Modifier.size(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("미리보기", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                    BoxWithConstraints(Modifier.fillMaxWidth()) {
                        // Compact cards with a shared height; never force an unnecessary square.
                        val equalHeight = if (androidx.compose.ui.platform.LocalDensity.current.fontScale > 1.25f) 152.dp else 130.dp
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(9.dp)
                        ) {
                            OwnerQuickCard(
                                Modifier.weight(1f).height(equalHeight),
                                BmIconId.MANAGE_BAR, "매장 정보 관리", "사진 · 소개 · 영업시간", onInfo
                            )
                            Surface(
                                modifier = Modifier.weight(1f).height(equalHeight),
                                shape = RoundedCornerShape(12.dp),
                                color = MaterialTheme.colorScheme.surface
                            ) {
                                Column(
                                    Modifier.fillMaxSize().padding(horizontal = 10.dp, vertical = 10.dp),
                                    verticalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                                        Row(
                                            Modifier.fillMaxWidth(),
                                            verticalAlignment = Alignment.CenterVertically,
                                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                                        ) {
                                            OwnerManagerIcon(BmIconId.UPDATED)
                                            // All status labels share one compact single-line font size.
                                            Text(
                                                if (exception?.kind == MockExceptionKind.VACATION) "임시 휴무"
                                                else homeExceptionHeading(exception),
                                                modifier = Modifier.weight(1f),
                                                fontSize = 10.sp,
                                                fontWeight = FontWeight.Bold,
                                                maxLines = 1
                                            )
                                            if (exception != null) {
                                                Text(
                                                    "×", fontSize = 29.sp,
                                                    color = MaterialTheme.colorScheme.error,
                                                    modifier = Modifier.width(22.dp)
                                                        .clickable {
                                                            try {
                                                                viewModel.cancelOperatingException(bar.barId, exception.exceptionId)
                                                                error = null
                                                            } catch (e: Exception) { error = e.message }
                                                        },
                                                    textAlign = TextAlign.Center
                                                )
                                            }
                                        }
                                        val statusDetail = when (exception?.kind) {
                                            MockExceptionKind.VACATION ->
                                                "${ownerDate(exception.fromEpochDay)} ~ ${ownerDate(exception.toEpochDay)}"
                                            MockExceptionKind.CUSTOM_HOURS ->
                                                "%02d:%02d ~ %s%02d:%02d".format(
                                                    (exception.openMinutes ?: 0) / 60,
                                                    (exception.openMinutes ?: 0) % 60,
                                                    if (exception.closesNextDay) "익일 " else "",
                                                    (exception.closeMinutes ?: 0) / 60,
                                                    (exception.closeMinutes ?: 0) % 60
                                                )
                                            else -> null
                                        }
                                        if (statusDetail != null) {
                                            Text(statusDetail,
                                                modifier = Modifier.padding(start = 36.dp),
                                                fontSize = 11.sp, fontWeight = FontWeight.Bold,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                maxLines = 1
                                            )
                                        }
                                    }
                                    OwnerManagerFooter("영업 상태 변경", onStatus)
                                }
                            }
                        }
                    }
                    Surface(shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.surface) {
                        Column(Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 5.dp),
                            verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Row(
                                Modifier.fillMaxWidth().clickable(onClick = onMenu)
                                    .defaultMinSize(minHeight = 43.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(9.dp)
                            ) {
                                OwnerManagerIcon(BmIconId.MANAGE_BAR)
                                Column(Modifier.weight(1f)) {
                                    Text("메뉴 관리", style = MaterialTheme.typography.titleMedium)
                                    Text(
                                        "게시된 메뉴 ${snapshot.menuItems.count { it.barId == bar.barId }}개 · " +
                                            "최근 갱신 ${ownerDisplayDate(listOfNotNull(
                                                bar.lastMenuPublishedAtEpochMs, bar.lastVerifiedAtEpochMs
                                            ).maxOrNull())}",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                                Text("›", style = MaterialTheme.typography.titleLarge)
                            }
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(buildAnnotatedString {
                                    append("메뉴 확인 ")
                                    withStyle(SpanStyle(color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)) { append(ageDays?.toString() ?: "-") }
                                    append(if (ageDays == null) " 미확인" else "일 경과")
                                }, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                                OutlinedButton(onClick = {
                                    try {
                                        viewModel.confirmMenuInformation(bar.barId, System.currentTimeMillis())
                                        error = null
                                    } catch (e: Exception) { error = e.message }
                                }, modifier = Modifier.height(30.dp),
                                    border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary),
                                    contentPadding = PaddingValues(horizontal = 9.dp, vertical = 0.dp)) {
                                    Text("지금도 맞아요", style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.primary)
                                }
                            }
                            // Material3's stop indicator can show a dot at the right even for 0%.
                            // Draw from x=0 to guarantee a strictly left-to-right fill.
                            val gaugeFraction = (freshness / 100f).coerceIn(0f, 1f)
                            val gaugeTrack = MaterialTheme.colorScheme.surfaceVariant
                            val gaugeFill = MaterialTheme.colorScheme.primary
                            Canvas(Modifier.fillMaxWidth().height(5.dp)) {
                                drawRoundRect(gaugeTrack, cornerRadius = androidx.compose.ui.geometry.CornerRadius(size.height / 2f))
                                if (gaugeFraction > 0f) {
                                    drawRoundRect(gaugeFill,
                                        size = androidx.compose.ui.geometry.Size(size.width * gaugeFraction, size.height),
                                        cornerRadius = androidx.compose.ui.geometry.CornerRadius(size.height / 2f))
                                }
                            }
                            Spacer(Modifier.height(5.dp))
                            Text("마지막 메뉴 게시 ${ownerDisplayDate(bar.lastMenuPublishedAtEpochMs)} · " +
                                    "판매 정보 확인 ${ownerDisplayDate(bar.lastVerifiedAtEpochMs)}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                            if (job != null) {
                                HorizontalDivider()
                                Row(
                                    Modifier.fillMaxWidth().clickable { onJob(job.status) }
                                        .defaultMinSize(minHeight = 52.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    BmIcon(
                                        if (job.status == MockImportStatus.FAILED) BmIconId.ERROR
                                        else if (job.status == MockImportStatus.READY_FOR_REVIEW) BmIconId.REVIEW
                                        else BmIconId.UPDATED,
                                        null, Modifier.size(24.dp),
                                        tint = MaterialTheme.colorScheme.primary
                                    )
                                    Column(Modifier.weight(1f)) {
                                        Text(ownerJobTitle(job.status), style = MaterialTheme.typography.labelLarge)
                                        Text(ownerJobDescription(job.status),
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                    Text("확인 ›", style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.primary)
                                }
                            }
                        }
                    }
                    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OwnerOperatingQuickScreen(
    state: MockOwnerLoadState,
    viewModel: OwnerMockViewModel,
    onBack: () -> Unit
) {
    val selected = activeBar(state)
    var choice by rememberSaveable { mutableStateOf("") }
    var note by rememberSaveable { mutableStateOf("") }
    var startHour by rememberSaveable { mutableIntStateOf(18) }
    var startMinute by rememberSaveable { mutableIntStateOf(0) }
    var endHour by rememberSaveable { mutableIntStateOf(21) }
    var endMinute by rememberSaveable { mutableIntStateOf(30) }
    var nextDay by rememberSaveable { mutableStateOf(false) }
    var openWheel by rememberSaveable { mutableStateOf("") }
    var startDay by rememberSaveable { mutableLongStateOf(Long.MIN_VALUE) }
    var endDay by rememberSaveable { mutableLongStateOf(Long.MIN_VALUE) }
    var dateTarget by rememberSaveable { mutableStateOf("") }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    val today = ownerToday(System.currentTimeMillis()).toEpochDay()
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("영업 상태 변경", onBack)
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (state == MockOwnerLoadState.Loading) {
                OwnerLoading("영업 상태 불러오는 중")
            } else if (state is MockOwnerLoadState.Error) {
                Text(state.message, color = MaterialTheme.colorScheme.error)
                OwnerActionButton("다시 시도", viewModel::retry)
            } else if (selected == null) {
                Text("관리할 매장이 없어요.")
            } else {
                val bar = selected.second
                listOf(
                    Triple("off", "오늘 휴무", BmIconId.ERROR),
                    Triple("hours", "오늘만 영업시간 변경", BmIconId.UPDATED),
                    Triple("range", "기간 임시 휴업", BmIconId.UPDATED)
                ).forEach { (key, label, icon) ->
                    Surface(
                        modifier = Modifier.fillMaxWidth().clickable { choice = key; error = null; if (key == "range") dateTarget = "start" else dateTarget = "" },
                        shape = RoundedCornerShape(10.dp),
                        color = if (choice == key) MaterialTheme.colorScheme.surfaceVariant
                            else MaterialTheme.colorScheme.surface
                    ) {
                        Row(Modifier.defaultMinSize(minHeight = 54.dp).padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            BmIcon(icon, null, Modifier.size(22.dp), tint = MaterialTheme.colorScheme.primary)
                            Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
                            Text("›")
                        }
                    }
                }
                if (choice.isNotEmpty()) {
                    if (choice == "hours") {
                        listOf("open" to "영업 시작", "close" to "영업 종료").forEach { (key, label) ->
                            TextButton(onClick = { openWheel = if (openWheel == key) "" else key }) {
                                Text(
                                    "$label: " + (if (key == "open")
                                        "%02d:%02d".format(startHour, startMinute)
                                    else "%02d:%02d".format(endHour, endMinute))
                                )
                            }
                            if (openWheel == key) {
                                OwnerTimeWheel(
                                    hour = if (key == "open") startHour else endHour,
                                    minute = if (key == "open") startMinute else endMinute,
                                    onTimeChange = { hour, minute ->
                                        if (key == "open") { startHour = hour; startMinute = minute }
                                        else { endHour = hour; endMinute = minute }
                                    }
                                )
                            }
                        }
                        TextButton(onClick = { nextDay = !nextDay }) {
                            Text(if (nextDay) "영업 종료: 다음 날 새벽 ✓" else "영업 종료: 오늘 · 다음 날로 변경")
                        }
                    }
                    if (choice == "range") {
                        if (dateTarget.isNotEmpty()) {
                            key(dateTarget) {
                                val calendar = rememberDatePickerState()
                                DatePicker(state = calendar, modifier = Modifier.fillMaxWidth())
                                LaunchedEffect(calendar.selectedDateMillis) {
                                    calendar.selectedDateMillis?.let { millis ->
                                        val day = Instant.ofEpochMilli(millis).atZone(ZoneOffset.UTC).toLocalDate().toEpochDay()
                                        if (day < today) {
                                            error = "과거 날짜는 선택할 수 없어요."
                                        } else if (dateTarget == "start") {
                                            startDay = day
                                            if (endDay < day) endDay = Long.MIN_VALUE
                                            dateTarget = "end"
                                            error = null
                                        } else if (day < startDay) {
                                            error = "종료일은 시작일 이후여야 해요."
                                        } else {
                                            endDay = day
                                            dateTarget = ""
                                            error = null
                                        }
                                    }
                                }
                            }
                        }
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = MaterialTheme.colorScheme.surface,
                            tonalElevation = 1.dp
                        ) {
                            Row(
                                Modifier.fillMaxWidth().padding(8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(6.dp)
                            ) {
                                OutlinedButton(
                                    onClick = { dateTarget = "start" },
                                    modifier = Modifier.weight(1f),
                                    contentPadding = PaddingValues(horizontal = 4.dp)
                                ) { Text(if (startDay == Long.MIN_VALUE) "시작 일자" else ownerDate(startDay), maxLines = 1) }
                                Text("~", style = MaterialTheme.typography.titleMedium)
                                OutlinedButton(
                                    onClick = { dateTarget = if (startDay == Long.MIN_VALUE) "start" else "end" },
                                    modifier = Modifier.weight(1f),
                                    contentPadding = PaddingValues(horizontal = 4.dp)
                                ) { Text(if (endDay == Long.MIN_VALUE) "종료 일자" else ownerDate(endDay), maxLines = 1) }
                            }
                        }
                    }
                    OwnerTextInput(
                        label = "고객 안내 (선택)", value = note,
                        onValueChange = { note = it.take(80) },
                        placeholder = "예: 내부 사정으로 조기 마감합니다"
                    )
                    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                    OwnerActionButton(
                        label = when (choice) {
                            "off" -> "휴무 적용"
                            "hours" -> "변경 적용"
                            else -> "휴업 적용"
                        },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = choice != "range" ||
                            (startDay >= today && endDay >= startDay),
                        onClick = {
                            try {
                                val kind = when (choice) {
                                    "off" -> MockExceptionKind.CLOSED_TODAY
                                    "hours" -> MockExceptionKind.CUSTOM_HOURS
                                    else -> MockExceptionKind.VACATION
                                }
                                require(choice != "range" || (startDay >= today && endDay >= startDay))
                                viewModel.applyOperatingException(
                                    bar.barId, MockOperatingException(
                                        exceptionId = "quick-" + UUID.randomUUID().toString(),
                                        kind = kind,
                                        fromEpochDay = if (choice == "range") startDay else today,
                                        toEpochDay = if (choice == "range") endDay else today,
                                        note = note.trim().ifBlank { null },
                                        openMinutes = if (choice == "hours") startHour * 60 + startMinute else null,
                                        closeMinutes = if (choice == "hours") endHour * 60 + endMinute else null,
                                        closesNextDay = if (choice == "hours") nextDay else false
                                    )
                                )
                                error = null
                                onBack()
                            } catch (e: Exception) { error = e.message ?: "일정을 저장하지 못했어요." }
                        }
                    )
                }
            }
        }
    }
}

@Composable
fun OwnerMenuQuickEntryScreen(
    state: MockOwnerLoadState,
    onRetry: () -> Unit,
    onBack: () -> Unit,
    onNewPhoto: () -> Unit,
    onExistingJob: (MockImportStatus) -> Unit
) {
    val selected = activeBar(state)
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("메뉴 관리", onBack)
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (state == MockOwnerLoadState.Loading) {
                OwnerLoading("메뉴 정보 불러오는 중")
            } else if (state is MockOwnerLoadState.Error) {
                Text(state.message, color = MaterialTheme.colorScheme.error)
                OwnerActionButton("다시 시도", onRetry)
            } else if (selected == null) {
                Text("관리할 매장이 없어요.")
            } else {
                val (snapshot, bar) = selected
                val job = latestOwnerImport(snapshot.imports, bar.barId)
                Text("최근 갱신 ${ownerDisplayDate(listOfNotNull(
                    bar.lastMenuPublishedAtEpochMs, bar.lastVerifiedAtEpochMs
                ).maxOrNull())}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("사진으로 메뉴 추가", style = MaterialTheme.typography.titleMedium)
                when (job?.status) {
                    MockImportStatus.PROCESSING -> {
                        OwnerStatusLabel("AI 분석 중 · 등록 불가", OwnerStatusTone.ATTENTION)
                        OwnerActionButton("작업 확인하기", { onExistingJob(MockImportStatus.PROCESSING) },
                            Modifier.fillMaxWidth(), secondary = true)
                    }
                    MockImportStatus.READY_FOR_REVIEW -> {
                        OwnerStatusLabel("메뉴판 확인 준비 완료", OwnerStatusTone.ATTENTION)
                        OwnerActionButton("추가할 메뉴 확인하기", { onExistingJob(MockImportStatus.READY_FOR_REVIEW) },
                            Modifier.fillMaxWidth(), secondary = true)
                    }
                    MockImportStatus.FAILED -> {
                        OwnerStatusLabel("메뉴판 분석 실패", OwnerStatusTone.ERROR)
                        OwnerActionButton("작업 확인하기", { onExistingJob(MockImportStatus.FAILED) },
                            Modifier.fillMaxWidth(), secondary = true)
                    }
                    else -> OwnerActionButton(
                        "메뉴판 사진으로 추가하기", onNewPhoto, Modifier.fillMaxWidth(), secondary = true
                    )
                }
                HorizontalDivider()
                Text("현재 게시 메뉴", style = MaterialTheme.typography.titleMedium)
                Text("게시된 메뉴 ${snapshot.menuItems.count { it.barId == bar.barId }}개")
                OwnerStatusLabel("메뉴 상세 편집은 다음 단계에서 구현합니다.", OwnerStatusTone.NEUTRAL)
            }
        }
    }
}
