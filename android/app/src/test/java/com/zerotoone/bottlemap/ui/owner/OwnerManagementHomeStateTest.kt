package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.*
import java.time.LocalDate
import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OwnerManagementHomeStateTest {
    private val day = LocalDate.of(2026, 10, 31)
    private fun time(hour: Int, minute: Int = 0): Long =
        day.atTime(hour, minute).atZone(ownerSeoulZone).toInstant().toEpochMilli()

    @Test fun dateRangeIsStableAndFutureVacationIsVisibleOnHome() {
        val vacation = MockOperatingException(
            "vac", MockExceptionKind.VACATION, day.plusDays(3).toEpochDay(),
            day.plusDays(6).toEpochDay()
        )
        val bar = MockBar("bar", "테스트", "서울", exceptions = listOf(vacation))
        assertEquals(vacation, homeOperatingException(bar, time(12)))
        assertTrue(homeExceptionHeading(vacation).contains("임시 휴업"))
        assertTrue(homeExceptionHeading(vacation).contains("\n"))
        assertEquals("임시 휴업 예정", registrationOperatingLabel(vacation, time(12)))
        val duringVacation = day.plusDays(3).atTime(12, 0)
            .atZone(ownerSeoulZone).toInstant().toEpochMilli()
        assertEquals("임시 휴무", registrationOperatingLabel(vacation, duringVacation))
        assertEquals("정상 영업", registrationOperatingLabel(null, time(12)))
        assertNull(homeOperatingException(bar, day.plusDays(8).atStartOfDay(ownerSeoulZone)
            .toInstant().toEpochMilli()))
    }

    @Test fun operatingStateUsesKoreaTimeAndCurrentOverride() {
        val regular = MockWeeklyHours(6, closed = false, openMinutes = 18 * 60, closeMinutes = 23 * 60)
        val bar = MockBar("bar", "Test", "Address", weeklyHours = listOf(regular))
        assertEquals("영업 종료", homeOperatingState(bar, time(15)))
        assertEquals("영업 중", homeOperatingState(bar, time(20)))
        val closed = MockOperatingException(
            "off", MockExceptionKind.CLOSED_TODAY, day.toEpochDay(), day.toEpochDay())
        assertEquals("임시 휴무", homeOperatingState(bar.copy(exceptions = listOf(closed)), time(20)))
        val custom = MockOperatingException(
            "hours", MockExceptionKind.CUSTOM_HOURS, day.toEpochDay(), day.toEpochDay(),
            openMinutes = 10 * 60, closeMinutes = 12 * 60
        )
        assertEquals("영업 종료", homeOperatingState(bar.copy(exceptions = listOf(custom)), time(20)))
        assertEquals("오늘 영업시간 변경", homeExceptionHeading(custom))
    }

    @Test fun multiDayCustomHoursApplyEveryDayAndOvernightAfterFinalDay() {
        val start = day.toEpochDay()
        val schedule = MockOperatingException(
            "multi-day", MockExceptionKind.CUSTOM_HOURS,
            start, start + 2, openMinutes = 19 * 60, closeMinutes = 2 * 60,
            closesNextDay = true
        )
        val bar = MockBar("b", "바", "서울", exceptions = listOf(schedule))
        fun at(offset: Long, hour: Int): Long =
            day.plusDays(offset).atTime(hour, 0)
                .atZone(ownerSeoulZone).toInstant().toEpochMilli()
        assertEquals("영업 종료", homeOperatingState(bar, at(0, 12)))
        assertEquals("영업 중", homeOperatingState(bar, at(0, 20)))
        assertEquals("영업 중", homeOperatingState(bar, at(1, 1)))
        assertEquals("영업 종료", homeOperatingState(bar, at(1, 12)))
        assertEquals("영업 중", homeOperatingState(bar, at(1, 20)))
        assertEquals("영업 중", homeOperatingState(bar, at(2, 20)))
        assertEquals("영업 중", homeOperatingState(bar, at(3, 1)))
        assertEquals("영업시간 정보 없음", homeOperatingState(bar, at(3, 3)))
    }

    @Test fun previewOvernightCloseTimeUsesTodayForOngoingMultiDayShift() {
        val start = day.toEpochDay()
        val custom = MockOperatingException(
            "overnight-range", MockExceptionKind.CUSTOM_HOURS,
            start, start + 2, openMinutes = 19 * 60, closeMinutes = 2 * 60,
            closesNextDay = true
        )
        val bar = MockBar("bar", "바", "서울", exceptions = listOf(custom))
        fun at(offset: Long, hour: Int) = day.plusDays(offset).atTime(hour, 0)
            .atZone(ownerSeoulZone).toInstant().toEpochMilli()
        assertEquals("익일 02:00 종료", ownerPreviewNextText(bar, at(0, 20)))
        assertEquals("02:00 종료", ownerPreviewNextText(bar, at(1, 1)))
        assertEquals("02:00 종료", ownerPreviewNextText(bar, at(2, 1)))
        assertEquals("02:00 종료", ownerPreviewNextText(bar, at(3, 1)))
        assertEquals("익일 02:00 종료", ownerPreviewNextText(bar, at(2, 20)))
    }

    @Test fun yesterdayTemporaryOvernightHoursRemainVisibleAfterMidnight() {
        val yesterday = day.minusDays(1)
        val hours = MockOperatingException(
            "overnight", MockExceptionKind.CUSTOM_HOURS,
            yesterday.toEpochDay(), yesterday.toEpochDay(),
            openMinutes = 19 * 60, closeMinutes = 2 * 60, closesNextDay = true
        )
        val bar = MockBar("bar", "테스트", "서울", exceptions = listOf(hours))
        assertEquals(hours, homeOperatingException(bar, time(1)))
        assertEquals("영업 중", homeOperatingState(bar, time(1)))
        assertNull(homeOperatingException(bar, time(3)))
    }

    @Test fun regularOvernightDoesNotOpenBeforeTonightWhenYesterdayWasClosed() {
        val currentDay = MockWeeklyHours(6, closed = false, openMinutes = 18 * 60,
            closeMinutes = 2 * 60, closesNextDay = true)
        val fridayClosed = MockWeeklyHours(5, closed = true)
        val bar = MockBar("b", "바", "서울", weeklyHours = listOf(currentDay, fridayClosed))
        assertEquals("영업 종료", homeOperatingState(bar, time(1)))
        assertEquals("영업 중", homeOperatingState(bar, time(19)))
        val nextMorning = day.plusDays(1).atTime(1, 0).atZone(ownerSeoulZone)
            .toInstant().toEpochMilli()
        assertEquals("영업 중", homeOperatingState(bar, nextMorning))
        val afterClose = day.plusDays(1).atTime(3, 0).atZone(ownerSeoulZone)
            .toInstant().toEpochMilli()
        assertEquals("영업 종료", homeOperatingState(bar, afterClose))
    }

    @Test fun previousDayOverrideSuppressesStaleRegularOvernightShift() {
        // Friday's regular hours cross midnight. Saturday at 01:00 must
        // reflect Friday's active override, not Friday's regular template.
        val friday = day.minusDays(1).toEpochDay()
        val regular = MockWeeklyHours(5, false, 18 * 60, 4 * 60, closesNextDay = true)
        val saturday = MockWeeklyHours(6, false, 19 * 60, 23 * 60)
        val base = MockBar("b", "바", "서울", weeklyHours = listOf(regular, saturday))
        assertEquals("영업 중", homeOperatingState(base, time(1)))

        val shortened = MockOperatingException(
            "short", MockExceptionKind.CUSTOM_HOURS, friday, friday,
            openMinutes = 18 * 60, closeMinutes = 23 * 60
        )
        assertEquals("영업 종료",
            homeOperatingState(base.copy(exceptions = listOf(shortened)), time(1)))
        assertEquals("영업 중",
            homeOperatingState(base.copy(exceptions = listOf(shortened)), time(20)))

        val closed = MockOperatingException(
            "closed", MockExceptionKind.CLOSED_TODAY, friday, friday
        )
        assertEquals("영업 종료",
            homeOperatingState(base.copy(exceptions = listOf(closed)), time(1)))

        val vacation = MockOperatingException(
            "vacation", MockExceptionKind.VACATION, friday, friday
        )
        assertEquals("영업 종료",
            homeOperatingState(base.copy(exceptions = listOf(vacation)), time(1)))

        // A temporary overnight shift takes precedence over the original
        // 04:00 regular close, and must stop being open at its own 02:00 close.
        val shortenedOvernight = shortened.copy(
            closeMinutes = 2 * 60, closesNextDay = true)
        val override = base.copy(exceptions = listOf(shortenedOvernight))
        assertEquals("영업 중", homeOperatingState(override, time(1)))
        assertEquals("영업 종료", homeOperatingState(override, time(3)))
    }

    @Test fun completedTemporaryDayReturnsToRegularSchedule() {
        val ended = MockOperatingException(
            "ended", MockExceptionKind.CLOSED_TODAY, day.minusDays(1).toEpochDay(),
            day.minusDays(1).toEpochDay(), note = "어제 휴무"
        )
        val bar = MockBar("b", "바", "서울",
            weeklyHours = listOf(MockWeeklyHours(6, false, 18 * 60, 23 * 60)),
            exceptions = listOf(ended))
        assertNull(homeOperatingException(bar, time(20)))
        assertEquals("영업 중", homeOperatingState(bar, time(20)))
    }

    @Test fun menuFreshnessUsesLatestOfPublishedAndVerifiedButKeepsThemIndependent() {
        val withoutTimes = MockBar("bar", "Test", "Address")
        assertEquals(null, ownerMenuFreshness(withoutTimes, time(20)).first)
        assertEquals(0, ownerMenuFreshness(withoutTimes, time(20)).second)
        val postedAt = day.minusDays(20).atStartOfDay(ownerSeoulZone).toInstant().toEpochMilli()
        val checkedAt = day.minusDays(3).atStartOfDay(ownerSeoulZone).toInstant().toEpochMilli()
        val bar = withoutTimes.copy(
            lastMenuPublishedAtEpochMs = postedAt, lastVerifiedAtEpochMs = checkedAt)
        assertEquals(3L, ownerMenuFreshness(bar, time(20)).first)
        assertEquals(94, ownerMenuFreshness(bar, time(20)).second)
        assertEquals("10.11", ownerDisplayDate(postedAt))
        assertEquals("10.28", ownerDisplayDate(checkedAt))
    }

    @Test fun freshnessStartsFullAndDropsFromLeftToRightOverTime() {
        val confirmed = day.atStartOfDay(ownerSeoulZone).toInstant().toEpochMilli()
        val bar = MockBar("bar", "Test", "Address", lastVerifiedAtEpochMs = confirmed)
        assertEquals(100, ownerMenuFreshness(bar, time(20)).second)
        val later = day.plusDays(45).atStartOfDay(ownerSeoulZone).toInstant().toEpochMilli()
        assertEquals(0, ownerMenuFreshness(bar, later).second)
        val novemberFifth = LocalDate.of(2026, 11, 5)
        assertEquals("11.05", ownerDate(novemberFifth.toEpochDay()))
    }

    @Test fun vacationCalendarSelectsStartThenEndWithoutChangingRepository() {
        val unset = Long.MIN_VALUE
        val first = updateQuickVacationDates(unset, unset, 21000L, "start")
        assertEquals(21000L to unset, first)
        val second = updateQuickVacationDates(first!!.first, first.second, 21005L, "end")
        assertEquals(21000L to 21005L, second)
        assertEquals(null, updateQuickVacationDates(21000L, 21005L, 20999L, "end"))
        assertEquals(21001L to 21005L,
            updateQuickVacationDates(21000L, 21005L, 21001L, "start"))
        assertEquals(21006L to unset,
            updateQuickVacationDates(21000L, 21005L, 21006L, "start"))
    }

    @Test fun applyDateIsCalculatedAtTapTimeAcrossSeoulMidnight() {
        val before = day.atTime(23, 59).atZone(ownerSeoulZone).toInstant().toEpochMilli()
        val after = day.plusDays(1).atTime(0, 1)
            .atZone(ownerSeoulZone).toInstant().toEpochMilli()
        assertEquals(day.toEpochDay(), ownerQuickApplyDay(before))
        assertEquals(day.plusDays(1).toEpochDay(), ownerQuickApplyDay(after))
        assertTrue(validQuickVacationAtApply(day.toEpochDay(), day.plusDays(2).toEpochDay(),
            ownerQuickApplyDay(before)))
        assertFalse(validQuickVacationAtApply(day.toEpochDay(), day.plusDays(2).toEpochDay(),
            ownerQuickApplyDay(after)))
    }

    @Test fun activeMenuJobTakesPrecedenceOverPriorPublishedJob() {
        val applied = MockMenuImport("applied", "bar", MockImportStatus.APPLIED, 1, emptyList())
        val processing = MockMenuImport("new", "bar", MockImportStatus.PROCESSING, 1, emptyList())
        assertEquals(processing, latestOwnerImport(listOf(applied, processing), "bar"))
        assertEquals(applied, latestOwnerImport(listOf(applied), "bar"))
        val failed = MockMenuImport("old-failed", "bar", MockImportStatus.FAILED, 1, emptyList())
        assertEquals(applied, latestOwnerImport(listOf(failed, applied), "bar"))
        assertEquals(processing, latestOwnerImport(listOf(failed, applied, processing), "bar"))
        assertEquals("AI 분석 중", ownerJobTitle(MockImportStatus.PROCESSING))
        assertEquals("메뉴판 확인 준비 완료", ownerJobTitle(MockImportStatus.READY_FOR_REVIEW))
        assertEquals("메뉴판 분석 실패", ownerJobTitle(MockImportStatus.FAILED))
        assertEquals("게시 완료", ownerJobTitle(MockImportStatus.APPLIED))
        assertNull(latestOwnerImport(listOf(applied), "other-bar"))
    }
}
