// AI-assisted with ChatGPT/GPT-6 (Hojin Nam, 2026-10-18, I2-P38). Temporary verification only; never merge.
package com.zerotoone.bottlemap.ci

import org.junit.Assert.assertEquals
import org.junit.Test

class IntentionalCiFailureTest {
    @Test
    fun intentionallyFailsToProveRequiredAndroidChecksEnforceJUnitFailures() {
        assertEquals("CI must report an intentional failure", 1, 2)
    }
}
