package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockWeeklyHours
import com.zerotoone.bottlemap.data.owner.MockOperatingException
import com.zerotoone.bottlemap.data.owner.MockExceptionKind
import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Test

class OwnerPreviewV4StatusTest {
    private val monday = LocalDate.of(2026, 11, 2)
    private fun at(day: LocalDate, hour: Int, minute: Int = 0): Long =
        day.atTime(hour, minute).atZone(ownerSeoulZone).toInstant().toEpochMilli()

    @Test fun showsHTMLNextDayClosingNextToGreenStatus() {
        val bar = MockBar("bar", "바", "서울",
            weeklyHours = listOf(MockWeeklyHours(
                isoDayOfWeek = 1, closed = false,
                openMinutes = 18 * 60, closeMinutes = 2 * 60,
                closesNextDay = true)))
        assertEquals("영업 중", homeOperatingState(bar, at(monday, 20)))
        assertEquals("익일 02:00 종료", ownerPreviewNextText(bar, at(monday, 20)))
        assertEquals("02:00 종료", ownerPreviewNextText(bar, at(monday.plusDays(1), 1)))
        assertEquals("18:00 시작", ownerPreviewNextText(bar, at(monday, 17)))
    }

    @Test fun todayClosedHidesNextOpeningText() {
        val bar = MockBar("bar", "바", "서울",
            weeklyHours = listOf(MockWeeklyHours(1, false, 18 * 60, 22 * 60)),
            exceptions = listOf(MockOperatingException("off",
                MockExceptionKind.CLOSED_TODAY, monday.toEpochDay(), monday.toEpochDay())))
        assertEquals("임시 휴무", homeOperatingState(bar, at(monday, 19)))
        assertEquals("", ownerPreviewNextText(bar, at(monday, 19)))
        assertEquals("18:00 시작", ownerPreviewNextText(
            bar, at(monday.plusDays(7), 17)))
    }

    @Test fun categoryLabelsUseHTMLKoreanGroups() {
        assertEquals("위스키", ownerV4Category("whisky"))
        assertEquals("브랜디", ownerV4Category("brandy"))
        assertEquals("칵테일", ownerV4Category("cocktail"))
    }
}
