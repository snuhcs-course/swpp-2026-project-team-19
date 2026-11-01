package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockPhoto
import com.zerotoone.bottlemap.data.owner.MockPhotoKind
import com.zerotoone.bottlemap.data.owner.MockWeeklyHours
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OwnerBarEditRulesTest {
    private val bar = MockBar("bar", "Before", "Seoul")

    @Test fun basicFieldsValidateAndNeverClearUnrelatedData() {
        assertNotNull(barInfoError("", "", "서울", "", ""))
        assertNotNull(barInfoError("A", "", "", "", ""))
        assertNotNull(barInfoError("A", "", "서울", "1234X", ""))
        assertNotNull(barInfoError("A", "", "서울", "", "0"))
        assertNotNull(barInfoError("A", "x".repeat(101), "서울", "", ""))
        assertNull(barInfoError("A", "소개", "서울", "02-1234-5678", "30"))
        assertNotNull(barInfoError("A", "소개", "서울", "", "1000"))
        assertNull(barInfoError("A".repeat(150), "소개", "서울", "", ""))
        val photo = MockPhoto("p1", "content://bar/cover", MockPhotoKind.BAR_GALLERY)
        val updated = withBarInfo(
            bar.copy(gallery = listOf(photo), tags = listOf("몰트")),
            " 바 이름 ", " 조용한 바 ", " 서울시 관악구 ", "02-1234-5678", "45"
        )
        assertEquals("바 이름", updated.name)
        assertEquals("조용한 바", updated.description)
        assertEquals("서울시 관악구", updated.address)
        assertEquals(45, updated.defaultPourMl)
        assertEquals(listOf(photo), updated.gallery)
        assertEquals(listOf("몰트"), updated.tags)
    }

    @Test fun photoOrderAndCoverAndZeroPhotos() {
        val photos = (1..3).map {
            MockPhoto("p$it", "content://photo/$it", MockPhotoKind.BAR_GALLERY)
        }
        assertEquals(listOf("p2", "p1", "p3"), moveBarPhoto(photos, 0, 1).map { it.photoId })
        assertEquals(listOf("p3", "p1", "p2"), makeCoverPhoto(photos, 2).map { it.photoId })
        assertEquals(photos, moveBarPhoto(photos, 0, -1))
        assertEquals(photos, makeCoverPhoto(photos, 10))
        assertTrue(moveBarPhoto(emptyList(), 0, -1).isEmpty())
    }

    @Test fun tagSearchSelectionToggleRejectsSixthAndLongTags() {
        val five = listOf("바", "몰트", "싱글몰트", "칵테일", "하이볼")
        assertNull(toggleBarTag(five, "추가"))
        assertNull(toggleBarTag(emptyList(), "한".repeat(25)))
        assertEquals(five.filterNot { it == "몰트" }, toggleBarTag(five, " 몰트 "))
        assertEquals(listOf("싱글몰트"), toggleBarTag(emptyList(), " 싱글몰트 "))
        assertTrue(toggleBarTag(listOf("몰트"), "몰트")!!.isEmpty())
    }

    @Test fun creatingTagDoesNotDeselectMatchingUnsavedDraftTag() {
        val available = listOf("몰트", "위스키")
        val draftSelected = listOf("수제 맥주", "몰트")
        assertFalse(canCreateOwnerTagDraft("수제 맥주", available, draftSelected))
        assertFalse(canCreateOwnerTagDraft(" 수제 맥주 ", available, draftSelected))
        assertFalse(canCreateOwnerTagDraft("수제 맥주".uppercase(), available, draftSelected))
        assertFalse(canCreateOwnerTagDraft("몰트", available, emptyList()))
        assertFalse(canCreateOwnerTagDraft("  ", available, emptyList()))
        assertTrue(canCreateOwnerTagDraft("새로운 태그", available, draftSelected))
    }

    @Test fun htmlV4PhotoArrowsProtectCoverAndChangeSecondaryOrder() {
        val images = (1..3).map {
            MockPhoto("p" + it, "content://photo/" + it, MockPhotoKind.BAR_GALLERY)
        }
        assertEquals(images, moveSecondaryBarPhoto(images, 0, 1))
        assertEquals(images, moveSecondaryBarPhoto(images, 1, -1))
        assertEquals(listOf("p1", "p3", "p2"),
            moveSecondaryBarPhoto(images, 1, 1).map { it.photoId })
        assertEquals(listOf("p3", "p1", "p2"),
            makeCoverPhoto(images, 2).map { it.photoId })
    }

    @Test fun htmlV4MondayCopyAppliesOnlyTuesdayToFridayAndKeepsWeekend() {
        val monday = MockWeeklyHours(1, closed = false,
            openMinutes = 18 * 60, closeMinutes = 60, closesNextDay = true)
        val saturday = MockWeeklyHours(6, closed = true)
        val copied = copyMondayToWeekdays(listOf(monday, saturday))
        assertEquals(listOf(1, 2, 3, 4, 5, 6), copied.map { it.isoDayOfWeek })
        assertTrue(copied.filter { it.isoDayOfWeek in 2..5 }
            .all { it.openMinutes == 18 * 60 && it.closeMinutes == 60 && it.closesNextDay })
        assertEquals(saturday, copied.last())
        val unset = copyMondayToWeekdays(listOf(saturday))
        assertEquals(listOf(saturday), unset)
        // Regression: Monday is absent, but edits for Tue-Fri already exist.
        // Copying from an unset day must not silently erase those drafts.
        val tuesday = MockWeeklyHours(2, false, 18 * 60, 23 * 60)
        val wednesday = MockWeeklyHours(3, true)
        val friday = MockWeeklyHours(5, false, 20 * 60, 23 * 60)
        val existing = listOf(tuesday, wednesday, friday, saturday)
        assertEquals(existing, copyMondayToWeekdays(existing))
    }

    @Test fun holidayToggleKeepsPreviouslyEnteredHoursInDraft() {
        val prior = MockWeeklyHours(2, false, 19 * 60, 2 * 60, closesNextDay = true)
        val closed = toggleWeeklyDayClosed(prior, 2, true)
        assertEquals(true, closed?.closed)
        assertEquals(prior.openMinutes, closed?.openMinutes)
        assertEquals(prior.closeMinutes, closed?.closeMinutes)
        assertEquals(prior.closesNextDay, closed?.closesNextDay)
        assertEquals(prior, toggleWeeklyDayClosed(closed, 2, false))

        // A weekday that was not configured before checking "휴무"
        // returns to the unset state rather than inventing incomplete hours.
        val unsetClosed = toggleWeeklyDayClosed(null, 3, true)
        assertEquals(MockWeeklyHours(3, true), unsetClosed)
        assertNull(toggleWeeklyDayClosed(unsetClosed, 3, false))

        // Partially entered times must also survive a reversible checkbox.
        val partial = MockWeeklyHours(4, false, openMinutes = 18 * 60)
        assertEquals(partial,
            toggleWeeklyDayClosed(toggleWeeklyDayClosed(partial, 4, true), 4, false))
    }

    @Test fun weeklyHourValidationSeparatesUnsetClosedRegularAndOvernight() {
        val normal = MockWeeklyHours(1, false, 18 * 60, 23 * 60)
        val overnight = MockWeeklyHours(2, false, 18 * 60, 2 * 60, closesNextDay = true)
        assertTrue(validWeeklyHourDraft(normal))
        assertTrue(validWeeklyHourDraft(overnight))
        assertTrue(validWeeklyHourDraft(MockWeeklyHours(3, true)))
        assertFalse(validWeeklyHourDraft(normal.copy(closeMinutes = 18 * 60)))
        assertFalse(validWeeklyHourDraft(normal.copy(closeMinutes = 18 * 60 + 3)))
        assertFalse(validWeeklyHourDraft(normal.copy(closeMinutes = 2 * 60)))
        assertNotNull(weeklyHoursError(listOf(normal, normal)))
        assertNull(weeklyHoursError(emptyList()))
        val saved = withWeeklyHours(bar, listOf(overnight, normal))
        assertEquals(listOf(1, 2), saved.weeklyHours.map { it.isoDayOfWeek })
        assertTrue(saved.exceptions.isEmpty())
    }
}
