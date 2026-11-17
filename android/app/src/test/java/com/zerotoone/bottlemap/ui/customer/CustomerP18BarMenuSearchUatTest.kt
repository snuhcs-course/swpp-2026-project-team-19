package com.zerotoone.bottlemap.ui.customer

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** UAT 4.3: only case/spacing/dashes are normalized; no server embedding calls. */
class CustomerP18BarMenuSearchUatTest {
    @Test fun ardbeg10MatchesMenuWithSpace() {
        assertTrue(barMenuMatchesQuery("Ardbeg 10", "Ardbeg", "ardbeg10"))
        assertTrue(barMenuMatchesQuery("ARDBEG-10", null, "Ardbeg 10"))
        assertFalse(barMenuMatchesQuery("Ardbeg 17", "Ardbeg", "ardbeg10"))
    }

    @Test fun existingPartialAndBrandMatchingStayIntact() {
        assertTrue(barMenuMatchesQuery("위스키 한 잔", "아드벡", "아드벡"))
        assertTrue(barMenuMatchesQuery("Ardbeg 10", null, ""))
        assertTrue(barMenuMatchesQuery("Ardbeg 10", null, " "))
        assertFalse(barMenuMatchesQuery("Ardbeg 10", "Ardbeg", "Lagavulin"))
    }
}
