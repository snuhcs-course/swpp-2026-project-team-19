package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.snapping.rememberSnapFlingBehavior
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter

/** Visual wheel values are a draft until the "시간 선택 완료" action is tapped. */
@Composable
internal fun OwnerQuickTimeWheel(
    hour: Int,
    minute: Int,
    onConfirm: (Int, Int) -> Unit
) {
    var draftHour by rememberSaveable(hour) { mutableIntStateOf(hour) }
    var draftMinute by rememberSaveable(minute) { mutableIntStateOf(minute) }
    val hourScroll = rememberLazyListState(initialFirstVisibleItemIndex = hour)
    val minuteScroll = rememberLazyListState(initialFirstVisibleItemIndex = minute / 5)
    LaunchedEffect(hourScroll) {
        snapshotFlow { hourScroll.firstVisibleItemIndex }.collect { draftHour = it.coerceIn(0, 23) }
    }
    LaunchedEffect(minuteScroll) {
        snapshotFlow { minuteScroll.firstVisibleItemIndex }.collect {
            draftMinute = (it * 5).coerceIn(0, 55)
        }
    }
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(12.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.fillMaxWidth().height(132.dp), contentAlignment = Alignment.Center) {
                Surface(
                    modifier = Modifier.fillMaxWidth(0.76f).height(44.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.18f),
                    shape = RoundedCornerShape(9.dp),
                    border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.5f))
                ) {}
                Row(
                    Modifier.fillMaxWidth(0.76f).height(132.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center
                ) {
                    LazyColumn(
                        modifier = Modifier.weight(1f).fillMaxHeight(),
                        state = hourScroll,
                        flingBehavior = rememberSnapFlingBehavior(hourScroll),
                        contentPadding = PaddingValues(vertical = 44.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        items(24) { value ->
                            Box(Modifier.fillMaxWidth().height(44.dp), contentAlignment = Alignment.Center) {
                                Text("%02d".format(value), textAlign = TextAlign.Center,
                                    style = if (value == draftHour) MaterialTheme.typography.titleLarge
                                        else MaterialTheme.typography.bodyLarge,
                                    fontWeight = if (value == draftHour) FontWeight.Bold else FontWeight.Normal,
                                    color = if (value == draftHour) MaterialTheme.colorScheme.onSurface
                                        else MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                    Text(":", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    LazyColumn(
                        modifier = Modifier.weight(1f).fillMaxHeight(),
                        state = minuteScroll,
                        flingBehavior = rememberSnapFlingBehavior(minuteScroll),
                        contentPadding = PaddingValues(vertical = 44.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        items(12) { index ->
                            val value = index * 5
                            Box(Modifier.fillMaxWidth().height(44.dp), contentAlignment = Alignment.Center) {
                                Text("%02d".format(value), textAlign = TextAlign.Center,
                                    style = if (value == draftMinute) MaterialTheme.typography.titleLarge
                                        else MaterialTheme.typography.bodyLarge,
                                    fontWeight = if (value == draftMinute) FontWeight.Bold else FontWeight.Normal,
                                    color = if (value == draftMinute) MaterialTheme.colorScheme.onSurface
                                        else MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
            Text("선택: %02d:%02d".format(draftHour, draftMinute),
                modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center,
                style = MaterialTheme.typography.labelMedium)
            OutlinedButton(
                onClick = { onConfirm(draftHour, draftMinute) },
                modifier = Modifier.fillMaxWidth().height(40.dp),
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                shape = RoundedCornerShape(8.dp)
            ) { Text("시간 선택 완료", fontWeight = FontWeight.Bold) }
        }
    }
}

@Composable
internal fun OwnerClockIcon() {
    val tint = MaterialTheme.colorScheme.primary
    Canvas(Modifier.size(16.dp)) {
        val line = 1.6.dp.toPx()
        drawCircle(tint, radius = size.minDimension * 0.39f, style = Stroke(width = line))
        drawLine(tint, center,
            androidx.compose.ui.geometry.Offset(center.x, center.y - size.height * 0.22f), strokeWidth = line)
        drawLine(tint, center,
            androidx.compose.ui.geometry.Offset(center.x + size.width * 0.17f, center.y), strokeWidth = line)
    }
}

/** Single inline month calendar (kept visible after the end date is selected). */
@Composable
internal fun OwnerVacationCalendar(
    today: Long,
    startDay: Long,
    endDay: Long,
    selectedTarget: String,
    onSelectTarget: (String) -> Unit,
    onPick: (Long) -> Unit
) {
    var visibleMonth by rememberSaveable {
        mutableLongStateOf(LocalDate.ofEpochDay(
            if (startDay == Long.MIN_VALUE) today else startDay
        ).withDayOfMonth(1).toEpochDay())
    }
    val month = YearMonth.from(LocalDate.ofEpochDay(visibleMonth))
    val firstColumn = month.atDay(1).dayOfWeek.value - 1
    val weeks = (firstColumn + month.lengthOfMonth() + 6) / 7
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(12.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(
                    onClick = { visibleMonth = month.minusMonths(1).atDay(1).toEpochDay() },
                    modifier = Modifier.size(36.dp), contentPadding = PaddingValues(0.dp)
                ) { Text("‹", style = MaterialTheme.typography.headlineSmall) }
                Text("%d년 %d월".format(month.year, month.monthValue),
                    style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                TextButton(
                    onClick = { visibleMonth = month.plusMonths(1).atDay(1).toEpochDay() },
                    modifier = Modifier.size(36.dp), contentPadding = PaddingValues(0.dp)
                ) { Text("›", style = MaterialTheme.typography.headlineSmall) }
            }
            Row(Modifier.fillMaxWidth()) {
                listOf("월", "화", "수", "목", "금", "토", "일").forEach { weekday ->
                    Box(Modifier.weight(1f).height(28.dp), contentAlignment = Alignment.Center) {
                        Text(weekday, style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            repeat(weeks) { week ->
                Row(Modifier.fillMaxWidth()) {
                    repeat(7) { weekday ->
                        val number = week * 7 + weekday - firstColumn + 1
                        Box(Modifier.weight(1f).height(40.dp), contentAlignment = Alignment.Center) {
                            if (number in 1..month.lengthOfMonth()) {
                                val epoch = month.atDay(number).toEpochDay()
                                val selected = epoch == startDay || epoch == endDay
                                val inRange = startDay != Long.MIN_VALUE &&
                                    endDay != Long.MIN_VALUE && epoch in startDay..endDay
                                Box(
                                    Modifier.fillMaxSize().padding(horizontal = 1.dp)
                                        .then(if (inRange) Modifier.background(
                                            MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                                            RoundedCornerShape(6.dp)
                                        ) else Modifier)
                                        .ownerQuietClick(enabled = epoch >= today) { onPick(epoch) },
                                    contentAlignment = Alignment.Center
                                ) {
                                    Box(
                                        Modifier.size(32.dp).background(
                                            if (selected) MaterialTheme.colorScheme.primary else Color.Transparent,
                                            RoundedCornerShape(9.dp)
                                        ), contentAlignment = Alignment.Center
                                    ) {
                                        Text(number.toString(),
                                            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
                                            style = MaterialTheme.typography.bodySmall,
                                            color = when {
                                                selected -> MaterialTheme.colorScheme.onPrimary
                                                epoch < today -> MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f)
                                                else -> MaterialTheme.colorScheme.onSurface
                                            })
                                    }
                                }
                            }
                        }
                    }
                }
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Row(Modifier.fillMaxWidth().padding(top = 5.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(
                    Triple("start", "시작", startDay),
                    Triple("end", "종료", endDay)
                ).forEach { (target, label, date) ->
                    Surface(
                        modifier = Modifier.weight(1f).ownerQuietClick { onSelectTarget(target) },
                        shape = RoundedCornerShape(8.dp),
                        color = if (selectedTarget == target)
                            MaterialTheme.colorScheme.primary.copy(alpha = 0.15f)
                        else MaterialTheme.colorScheme.surface,
                        border = if (selectedTarget == target)
                            BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.4f))
                        else null
                    ) {
                        Text(
                            label + " " + (if (date == Long.MIN_VALUE) "선택"
                                else LocalDate.ofEpochDay(date)
                                    .format(DateTimeFormatter.ofPattern("yyyy.MM.dd"))),
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 12.dp),
                            textAlign = TextAlign.Center,
                            style = MaterialTheme.typography.labelSmall,
                            maxLines = 1
                        )
                    }
                }
            }
        }
    }
}

/** Pure range transition; the repository is changed only by the Apply action. */
internal fun updateQuickVacationDates(
    start: Long, end: Long, picked: Long, target: String
): Pair<Long, Long>? = when (target) {
    "start" -> picked to (if (end >= picked) end else Long.MIN_VALUE)
    "end" -> if (start != Long.MIN_VALUE && picked >= start) start to picked else null
    else -> null
}
