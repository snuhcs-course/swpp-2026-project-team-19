package com.zerotoone.bottlemap.ui.common

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
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
}
