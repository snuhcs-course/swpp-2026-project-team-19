package com.zerotoone.bottlemap.data.owner

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OwnerServingIdentityTest {
    @Test fun koreanAndEnglishBottleShareTheSameIdentity() {
        assertEquals("Bottle", canonicalServingLabel("병"))
        assertEquals("Bottle", canonicalServingLabel(" bottle "))
        assertTrue(isBottleServingLabel("병"))
        assertTrue(isBottleServingLabel("BOTTLE"))
        assertEquals(servingIdentityKey(null, "병"), servingIdentityKey(null, "Bottle"))
        assertEquals(servingIdentityKey(700, "병"), servingIdentityKey(null, "Bottle"))
    }

    @Test fun samePourDoesNotEraseDistinctGlassOptionNames() {
        assertFalse(isBottleServingLabel("잔"))
        assertFalse(isBottleServingLabel("샷"))
        assertEquals("잔", canonicalServingLabel("잔"))
        assertTrue(servingIdentityKey(30, "잔") != servingIdentityKey(30, "샷"))
        assertTrue(servingIdentityKey(30, "잔") != servingIdentityKey(60, "잔"))
    }

    @Test fun missingOrCustomNonBottleLabelsAreNotInvented() {
        assertEquals(null, canonicalServingLabel(null))
        assertEquals("하프잔", canonicalServingLabel(" 하프잔 "))
        assertEquals("label:|ml:none", servingIdentityKey(null, null))
    }
}
