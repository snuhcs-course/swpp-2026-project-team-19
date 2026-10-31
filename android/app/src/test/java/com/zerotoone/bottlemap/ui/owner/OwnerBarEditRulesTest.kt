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
        assertNotNull(barInfoError("A", "x".repeat(161), "서울", "", ""))
        assertNull(barInfoError("A", "소개", "서울", "02-1234-5678", "30"))
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
