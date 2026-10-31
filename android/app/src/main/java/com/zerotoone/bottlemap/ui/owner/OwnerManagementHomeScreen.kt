package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.ui.platform.LocalDensity
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
            Modifier.fillMaxSize().padding(horizontal = 11.dp, vertical = 13.dp),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                OwnerManagerIcon(icon)
                Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            }
            Row(verticalAlignment = Alignment.Bottom) {
                Text(
                    footer, style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f)
                )
                Text("›", style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
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
                        val scale = LocalDensity.current.fontScale
                        val equalHeight = maxOf(180.dp, (maxWidth - 9.dp) / 2f, (170f * scale).dp)
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
                                    Modifier.fillMaxSize().padding(horizontal = 11.dp, vertical = 13.dp),
                                    verticalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                                        Row(verticalAlignment = Alignment.Top) {
                                            OwnerManagerIcon(BmIconId.UPDATED)
                                            Spacer(Modifier.width(5.dp))
                                            Text(
                                                homeExceptionHeading(exception),
                                                modifier = Modifier.weight(1f),
                                                style = MaterialTheme.typography.labelMedium,
                                                fontWeight = FontWeight.Bold,
                                                softWrap = true
                                            )
                                            if (exception != null) {
                                                TextButton(
                                                    onClick = {
                                                        try {
                                                            viewModel.cancelOperatingException(bar.barId, exception.exceptionId)
                                                            error = null
                                                        } catch (e: Exception) { error = e.message }
                                                    },
                                                    contentPadding = PaddingValues(0.dp),
                                                    modifier = Modifier.size(30.dp)
                                                ) { Text("×", color = MaterialTheme.colorScheme.error) }
                                            }
                                        }
                                        Text(
                                            homeOperatingState(bar, now),
                                            style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                    Row(
                                        Modifier.fillMaxWidth().clickable(onClick = onStatus)
                                            .defaultMinSize(minHeight = 40.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text("영업 상태 변경", modifier = Modifier.weight(1f),
                                            style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        Text("›", style = MaterialTheme.typography.titleLarge,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                }
                            }
                        }
                    }
                    Surface(shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.surface) {
                        Column(Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 8.dp),
                            verticalArrangement = Arrangement.spacedBy(9.dp)) {
                            Row(
                                Modifier.fillMaxWidth().clickable(onClick = onMenu)
                                    .defaultMinSize(minHeight = 54.dp),
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
                                Text("메뉴 확인 ${ageDays?.let { "${it}일 경과" } ?: "미확인"}",
                                    modifier = Modifier.weight(1f),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                                OutlinedButton(onClick = {
                                    try {
                                        viewModel.confirmMenuInformation(bar.barId, System.currentTimeMillis())
                                        error = null
                                    } catch (e: Exception) { error = e.message }
                                }, contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp)) {
                                    Text("지금도 맞아요", style = MaterialTheme.typography.labelSmall)
                                }
                            }
                            LinearProgressIndicator(
                                progress = { freshness / 100f },
                                modifier = Modifier.fillMaxWidth().height(5.dp),
                                color = MaterialTheme.colorScheme.primary,
                                trackColor = MaterialTheme.colorScheme.surfaceVariant
                            )
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
            if (selected == null) {
                Text("관리할 매장이 없어요.")
            } else {
                val bar = selected.second
                listOf(
                    Triple("off", "오늘 휴무", BmIconId.ERROR),
                    Triple("hours", "오늘만 영업시간 변경", BmIconId.UPDATED),
                    Triple("range", "기간 임시 휴업", BmIconId.UPDATED)
                ).forEach { (key, label, icon) ->
                    Surface(
                        modifier = Modifier.fillMaxWidth().clickable { choice = key; error = null },
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
                        OutlinedButton(onClick = { dateTarget = "start" }, modifier = Modifier.fillMaxWidth()) {
                            Text("시작 ${if (startDay == Long.MIN_VALUE) "선택" else ownerDate(startDay)}")
                        }
                        OutlinedButton(onClick = { dateTarget = "end" }, modifier = Modifier.fillMaxWidth()) {
                            Text("종료 ${if (endDay == Long.MIN_VALUE) "선택" else ownerDate(endDay)}")
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
    OwnerCalendarDialog(
        visible = dateTarget.isNotEmpty(),
        onDismiss = { dateTarget = "" },
        onSelectDateUtcMillis = { value ->
            val day = Instant.ofEpochMilli(value).atZone(ZoneOffset.UTC).toLocalDate().toEpochDay()
            if (day < today) error = "과거 날짜는 선택할 수 없어요."
            else if (dateTarget == "start") { startDay = day; if (endDay < day) endDay = day }
            else endDay = day
        }
    )
}

@Composable
fun OwnerMenuQuickEntryScreen(
    state: MockOwnerLoadState,
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
            if (selected == null) {
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
                        OwnerActionButton("작업 확인하기", { onExistingJob(job.status) },
                            Modifier.fillMaxWidth(), secondary = true)
                    }
                    MockImportStatus.READY_FOR_REVIEW -> {
                        OwnerStatusLabel("메뉴판 확인 준비 완료", OwnerStatusTone.ATTENTION)
                        OwnerActionButton("추가할 메뉴 확인하기", { onExistingJob(job.status) },
                            Modifier.fillMaxWidth(), secondary = true)
                    }
                    MockImportStatus.FAILED -> {
                        OwnerStatusLabel("메뉴판 분석 실패", OwnerStatusTone.ERROR)
                        OwnerActionButton("작업 확인하기", { onExistingJob(job.status) },
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
