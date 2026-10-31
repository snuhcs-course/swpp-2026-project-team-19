package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.*
import java.time.LocalDate
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

    @Test fun activeMenuJobTakesPrecedenceOverPriorPublishedJob() {
        val applied = MockMenuImport("applied", "bar", MockImportStatus.APPLIED, 1, emptyList())
        val processing = MockMenuImport("new", "bar", MockImportStatus.PROCESSING, 1, emptyList())
        assertEquals(processing, latestOwnerImport(listOf(applied, processing), "bar"))
        assertEquals(applied, latestOwnerImport(listOf(applied), "bar"))
        assertEquals("AI 분석 중", ownerJobTitle(MockImportStatus.PROCESSING))
        assertEquals("메뉴판 확인 준비 완료", ownerJobTitle(MockImportStatus.READY_FOR_REVIEW))
        assertEquals("메뉴판 분석 실패", ownerJobTitle(MockImportStatus.FAILED))
        assertEquals("게시 완료", ownerJobTitle(MockImportStatus.APPLIED))
        assertNull(latestOwnerImport(listOf(applied), "other-bar"))
    }
}
