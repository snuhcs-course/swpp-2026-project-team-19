package com.zerotoone.bottlemap.ui.customer

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** UAT 4.3: bar-local menu query should not require the displayed spacing. */
class CustomerP18BarMenuSearchUatTest {
    @Test fun ardbeg10MatchesDisplayedArdbeg10WithSpace() {
        assertTrue(p18BarMenuMatchesQuery("Ardbeg 10", "Ardbeg", "ardbeg10"))
        assertTrue(p18BarMenuMatchesQuery("Ardbeg-10", null, "ARDBEG 10"))
        assertFalse(p18BarMenuMatchesQuery("Ardbeg 17", "Ardbeg", "ardbeg10"))
    }

    @Test fun existingPartialAndBrandMatchingStillWork() {
        assertTrue(p18BarMenuMatchesQuery("위스키 한 잔", "아드벡", "아드벡"))
        assertTrue(p18BarMenuMatchesQuery("Ardbeg 10", "Ardbeg", ""))
        assertTrue(p18BarMenuMatchesQuery("Ardbeg 10", "Ardbeg", "  "))
        assertFalse(p18BarMenuMatchesQuery("Ardbeg 10", "Ardbeg", "Lagavulin"))
    }
}
