package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.ui.common.servingDisplayLabel
import org.junit.Assert.assertEquals
import org.junit.Test

/** Regression rules shared with Owner customer preview (API §3.9, 3.14). */
class CustomerP18ParityTest {
    @Test fun publishedPourMlOverridesGenericGlassLabel() {
        assertEquals("30ml",servingDisplayLabel(30,"잔"))
        assertEquals("45ml",servingDisplayLabel(45,null))
    }

    @Test fun bottleIsEnglishButUnknownGlassVolumeIsNeverInvented() {
        assertEquals("Bottle",servingDisplayLabel(null,"병"))
        assertEquals("Bottle",servingDisplayLabel(null,"bottle"))
        assertEquals("잔",servingDisplayLabel(null,"잔"))
        assertEquals("",servingDisplayLabel(null,null))
    }

    @Test fun previewSectionsAreMutuallyExclusiveAndToggleOff() {
        assertEquals("hours",p18NextExpandedPanel("","hours"))
        assertEquals("address",p18NextExpandedPanel("hours","address"))
        assertEquals("phone",p18NextExpandedPanel("address","phone"))
        assertEquals("",p18NextExpandedPanel("phone","phone"))
    }

    @Test fun secondPinTapCancelsSelectionButDifferentPinSwitches() {
        assertEquals("bar-a",p18ToggleSelectedBar(null,"bar-a"))
        assertEquals(null,p18ToggleSelectedBar("bar-a","bar-a"))
        assertEquals("bar-b",p18ToggleSelectedBar("bar-a","bar-b"))
    }
}
