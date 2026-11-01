package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockExceptionKind
import com.zerotoone.bottlemap.data.owner.MockImportStatus
import com.zerotoone.bottlemap.data.owner.MockMenuImport
import com.zerotoone.bottlemap.data.owner.MockOperatingException
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

/** Pure projections from the shared Mock snapshot; never a second store of Owner data. */
internal val ownerSeoulZone: ZoneId = ZoneId.of("Asia/Seoul")
private val ownerDateFormat = DateTimeFormatter.ofPattern("MM.dd")

internal fun ownerToday(atEpochMs: Long): LocalDate =
    Instant.ofEpochMilli(atEpochMs).atZone(ownerSeoulZone).toLocalDate()

internal fun ownerDate(epochDay: Long): String =
    LocalDate.ofEpochDay(epochDay).format(ownerDateFormat)

internal fun homeOperatingException(bar: MockBar, atEpochMs: Long): MockOperatingException? {
    val day = ownerToday(atEpochMs).toEpochDay()
    val now = Instant.ofEpochMilli(atEpochMs).atZone(ownerSeoulZone)
    val minute = now.hour * 60 + now.minute
    return bar.exceptions.lastOrNull { day in it.fromEpochDay..it.toEpochDay }
        ?: bar.exceptions.lastOrNull {
            it.kind == MockExceptionKind.CUSTOM_HOURS && it.closesNextDay &&
                it.toEpochDay == day - 1 && it.closeMinutes != null &&
                minute < it.closeMinutes
        }
        ?: bar.exceptions.filter {
            it.kind == MockExceptionKind.VACATION && it.fromEpochDay > day
        }.minByOrNull { it.fromEpochDay }
}

internal fun homeExceptionHeading(exception: MockOperatingException?): String = when (exception?.kind) {
    MockExceptionKind.CLOSED_TODAY -> "오늘 임시 휴무"
    MockExceptionKind.CUSTOM_HOURS -> "오늘 영업시간 변경"
    MockExceptionKind.VACATION -> "${ownerDate(exception.fromEpochDay)} ~\n${ownerDate(exception.toEpochDay)}\n임시 휴업"
    null -> "정상 영업"
}

/** Registration headline must not claim a future vacation has already closed the bar. */
internal fun registrationOperatingLabel(
    exception: MockOperatingException?, atEpochMs: Long,
): String = when {
    exception?.kind == MockExceptionKind.VACATION ->
        if (exception.fromEpochDay > ownerToday(atEpochMs).toEpochDay())
            "임시 휴업 예정" else "임시 휴무"
    else -> homeExceptionHeading(exception)
}

internal fun homeOperatingState(bar: MockBar, atEpochMs: Long): String {
    val now = Instant.ofEpochMilli(atEpochMs).atZone(ownerSeoulZone)
    val day = now.toLocalDate().toEpochDay()
    val exception = homeOperatingException(bar, atEpochMs)?.takeIf {
        (day in it.fromEpochDay..it.toEpochDay) ||
            (it.kind == MockExceptionKind.CUSTOM_HOURS && it.closesNextDay &&
                it.toEpochDay == day - 1)
    }
    if (exception?.kind == MockExceptionKind.CLOSED_TODAY ||
        exception?.kind == MockExceptionKind.VACATION) return "임시 휴무"
    val todayMinute = now.hour * 60 + now.minute
    val today = now.dayOfWeek.value
    val previous = if (today == 1) 7 else today - 1
    val previousShift = bar.weeklyHours.firstOrNull { it.isoDayOfWeek == previous }
    val overnight = previousShift != null && !previousShift.closed &&
        previousShift.closesNextDay && previousShift.closeMinutes != null &&
        todayMinute < previousShift.closeMinutes
    val regular = bar.weeklyHours.firstOrNull { it.isoDayOfWeek == today }
    // A shift starting *today* cannot make the bar open this morning.
    // Yesterday's overnight shift is evaluated separately.
    val previousTemporary = exception?.takeIf {
        it.kind == MockExceptionKind.CUSTOM_HOURS &&
            (day - 1) in it.fromEpochDay..it.toEpochDay && it.closesNextDay
    }
    if (previousTemporary?.closeMinutes != null &&
        todayMinute < previousTemporary.closeMinutes) return "영업 중"

    val todayTemporary = exception?.takeIf {
        it.kind == MockExceptionKind.CUSTOM_HOURS &&
            day in it.fromEpochDay..it.toEpochDay
    }
    val open = todayTemporary?.openMinutes ?: regular?.takeUnless { it.closed }?.openMinutes
    val close = todayTemporary?.closeMinutes ?: regular?.takeUnless { it.closed }?.closeMinutes
    val endsNextDay = todayTemporary?.closesNextDay ?: (regular?.closesNextDay == true)
    if (open == null || close == null) {
        return if (overnight) "영업 중"
        else if (bar.weeklyHours.isEmpty()) "영업시간 정보 없음" else "영업 종료"
    }
    val currentlyOpen = if (endsNextDay) todayMinute >= open
        else todayMinute in open until close
    return if (overnight || currentlyOpen) "영업 중" else "영업 종료"
}

internal fun latestOwnerImport(jobs: List<MockMenuImport>, barId: String): MockMenuImport? =
    // Import jobs are appended when created; recovery must not resurrect an older failure
    // after a newer job has already been published.
    jobs.lastOrNull { it.barId == barId }

internal fun ownerJobTitle(status: MockImportStatus): String = when (status) {
    MockImportStatus.PROCESSING -> "AI 분석 중"
    MockImportStatus.READY_FOR_REVIEW -> "메뉴판 확인 준비 완료"
    MockImportStatus.FAILED -> "메뉴판 분석 실패"
    MockImportStatus.APPLIED -> "게시 완료"
}

internal fun ownerJobDescription(status: MockImportStatus): String = when (status) {
    MockImportStatus.PROCESSING -> "다른 작업을 계속할 수 있어요"
    MockImportStatus.READY_FOR_REVIEW -> "추가할 메뉴를 확인해 주세요"
    MockImportStatus.FAILED -> "작업을 확인해 주세요"
    MockImportStatus.APPLIED -> "메뉴가 게시됐어요"
}

internal fun ownerMenuFreshness(bar: MockBar, atEpochMs: Long): Pair<Long?, Int> {
    val mostRecent = listOfNotNull(bar.lastMenuPublishedAtEpochMs, bar.lastVerifiedAtEpochMs)
        .maxOrNull() ?: return null to 0
    val elapsed = ChronoUnit.DAYS.between(ownerToday(mostRecent), ownerToday(atEpochMs))
        .coerceAtLeast(0)
    return elapsed to (100 - elapsed.coerceAtMost(45) * 100 / 45).toInt()
}

/** Resolve the actual day at Apply time, not the day captured on screen entry. */
internal fun ownerQuickApplyDay(nowEpochMs: Long): Long =
    ownerToday(nowEpochMs).toEpochDay()

internal fun validQuickVacationAtApply(startDay: Long, endDay: Long, today: Long): Boolean =
    startDay >= today && endDay >= startDay

internal fun ownerDisplayDate(epochMs: Long?): String = epochMs?.let {
    ownerToday(it).format(ownerDateFormat)
} ?: "없음"
