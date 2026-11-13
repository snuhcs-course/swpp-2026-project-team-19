package com.zerotoone.bottlemap.data.owner

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OwnerServingIdentityTest {
    @Test fun koreanAndEnglishBottleShareTheSameIdentity() {
        assertEquals("Bottle", canonicalServingLabel("병"))
        assertEquals("Bottle", canonicalServingLabel(" bottle "))
        assertEquals("Bottle", canonicalServingLabel("병 500ml"))
        assertEquals("Bottle", canonicalServingLabel("Bottle 700ml"))
        assertEquals("Bottle", canonicalServingLabel("병(330ml)"))
        assertTrue(isBottleServingLabel("병"))
        assertTrue(isBottleServingLabel("BOTTLE"))
        assertEquals(servingIdentityKey(null, "병"), servingIdentityKey(null, "Bottle"))
        assertEquals(servingIdentityKey(700, "병"), servingIdentityKey(null, "Bottle"))
    }

    @Test fun glassIdentityIsOnlyPourVolumeRegardlessOfLabel() {
        assertFalse(isBottleServingLabel("잔"))
        assertFalse(isBottleServingLabel("샷"))
        assertEquals("잔", canonicalServingLabel("잔"))
        assertEquals(servingIdentityKey(30, "잔"), servingIdentityKey(30, "샷"))
        assertTrue(servingIdentityKey(30, "잔") != servingIdentityKey(60, "잔"))
    }

    @Test fun missingOrCustomNonBottleLabelsAreNotInvented() {
        assertEquals(null, canonicalServingLabel(null))
        assertEquals("하프잔", canonicalServingLabel(" 하프잔 "))
        assertEquals("ml:unspecified", servingIdentityKey(null, null))
        assertEquals(servingIdentityKey(null, "잔"), servingIdentityKey(null, "샷"))
    }
}
