package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockExceptionKind
import java.time.Instant

/**
 * ACTION_FIRST_v4 customer status companion text. Use the same Seoul clock and
 * persisted weekly/temporary schedules as homeOperatingState, never a second state.
 */
internal fun ownerPreviewNextText(bar: MockBar, atEpochMs: Long): String {
    val clock = Instant.ofEpochMilli(atEpochMs).atZone(ownerSeoulZone)
    val minute = clock.hour * 60 + clock.minute
    val day = clock.toLocalDate().toEpochDay()
    val weekday = clock.dayOfWeek.value
    val state = homeOperatingState(bar, atEpochMs)
    val todayException = bar.exceptions.lastOrNull {
        day in it.fromEpochDay..it.toEpochDay
    }
    if (todayException?.kind == MockExceptionKind.CLOSED_TODAY ||
        todayException?.kind == MockExceptionKind.VACATION) return ""
    fun formatClose(close: Int, overnight: Boolean): String =
        (if (overnight) "익일 " else "") +
            "%02d:%02d 종료".format(close / 60, close % 60)
    val prevDay = if (weekday == 1) 7 else weekday - 1
    val prevException = bar.exceptions.lastOrNull { it.toEpochDay == day - 1 }
    val prevRegular = bar.weeklyHours.firstOrNull { it.isoDayOfWeek == prevDay }
    val prevClosed = prevException?.kind == MockExceptionKind.CLOSED_TODAY ||
        prevException?.kind == MockExceptionKind.VACATION
    val previousClose = if (prevClosed) null else
        if (prevException?.kind == MockExceptionKind.CUSTOM_HOURS &&
            prevException.closesNextDay) prevException.closeMinutes
        else prevRegular?.takeIf { !it.closed && it.closesNextDay }?.closeMinutes
    if (state == "영업 중" && previousClose != null && minute < previousClose)
        return formatClose(previousClose, false)

    val todayHours = bar.weeklyHours.firstOrNull { it.isoDayOfWeek == weekday }
    val open = if (todayException?.kind == MockExceptionKind.CUSTOM_HOURS)
        todayException.openMinutes else todayHours?.takeUnless { it.closed }?.openMinutes
    val close = if (todayException?.kind == MockExceptionKind.CUSTOM_HOURS)
        todayException.closeMinutes else todayHours?.takeUnless { it.closed }?.closeMinutes
    val nextDay = if (todayException?.kind == MockExceptionKind.CUSTOM_HOURS)
        todayException.closesNextDay else todayHours?.closesNextDay == true
    if (state == "영업 중" && close != null) return formatClose(close, nextDay)
    if (open != null && minute < open) return "%02d:%02d 시작".format(open / 60, open % 60)
    return ""
}
