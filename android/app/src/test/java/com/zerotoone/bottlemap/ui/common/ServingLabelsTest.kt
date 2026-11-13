package com.zerotoone.bottlemap.ui.common

import org.junit.Assert.assertEquals
import org.junit.Test

class ServingLabelsTest {
    @Test fun bottleLabelsAlwaysRenderBottleEvenWithLegacyVolume() {
        assertEquals("Bottle", servingDisplayLabel(null, "병"))
        assertEquals("Bottle", servingDisplayLabel(700, "병"))
        assertEquals("Bottle", servingDisplayLabel(500, "병 500ml"))
        assertEquals("Bottle", servingDisplayLabel(500, "Bottle 500ml"))
        assertEquals("Bottle", servingDisplayLabel(700, "bottle"))
        assertEquals("Bottle", servingDisplayLabel(null, "BOTTLE"))
    }

    @Test fun glassAndUnknownLabelsKeepTheirMeaning() {
        assertEquals("30ml", servingDisplayLabel(30, "잔"))
        assertEquals("30ml", servingDisplayLabel(30, "샷"))
        assertEquals("잔", servingDisplayLabel(null, "잔"))
        assertEquals("", servingDisplayLabel(null, null))
    }
}
