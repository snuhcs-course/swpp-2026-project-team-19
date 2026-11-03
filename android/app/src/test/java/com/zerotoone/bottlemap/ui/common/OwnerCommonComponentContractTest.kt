package com.zerotoone.bottlemap.ui.common

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class OwnerCommonComponentContractTest {
    @Test fun timeWheelAcceptsOnlyFiveMinuteSteps() {
        assertTrue(validOwnerTime(0, 0))
        assertTrue(validOwnerTime(23, 55))
        assertFalse(validOwnerTime(24, 0))
        assertFalse(validOwnerTime(-1, 5))
        assertFalse(validOwnerTime(10, 60))
        assertFalse(validOwnerTime(10, 7))
    }
    @Test fun sequentialHourThenMinuteKeepsNewHour() {
        val nextHour = changedOwnerTime(18, 0, selectedHour = 19)
        assertEquals(19 to 0, nextHour)
        assertEquals(19 to 5, changedOwnerTime(nextHour!!.first, nextHour.second, selectedMinute = 5))
    }

    @Test fun sequentialMinuteThenHourKeepsNewMinute() {
        val nextMinute = changedOwnerTime(18, 0, selectedMinute = 10)
        assertEquals(18 to 10, nextMinute)
        assertEquals(20 to 10, changedOwnerTime(nextMinute!!.first, nextMinute.second, selectedHour = 20))
    }

    @Test fun invalidOrUnchangedWheelSelectionDoesNotEmit() {
        assertNull(changedOwnerTime(18, 0, selectedMinute = 7))
        assertNull(changedOwnerTime(18, 0, selectedHour = 24))
        assertNull(changedOwnerTime(18, 0, selectedHour = 18))
        assertEquals(0 to 55, changedOwnerTime(0, 0, selectedMinute = 55))
    }
}
