package com.zerotoone.bottlemap.telemetry

import org.junit.Assert.*
import org.junit.Test

class AnalyticsCollectionTest {
    /** Models the SDK's documented/logged rejection while measurement is disabled. */
    private class DisabledByDefaultAnalytics {
        var consentGranted = false
        var enabled = false
        val properties = mutableMapOf<String, String>()
        var ignoredProperties = 0
        fun setProperty(value: String) {
            if (enabled) properties["release_channel"] = value else ignoredProperties++
        }
        fun optOut() { enabled = false; consentGranted = false; properties.clear() }
        fun enable(channel: String) = enableConsentedAnalytics(
            grantConsent = { consentGranted = true },
            enableCollection = {
                assertTrue("Consent must be applied before collection starts", consentGranted)
                enabled = true
            },
            setReleaseChannel = { setProperty(channel) },
        )
    }
    @Test fun firstOptInSetsDevAfterCollectionIsEnabled() {
        val analytics = DisabledByDefaultAnalytics()
        analytics.enable("dev")
        assertEquals("dev", analytics.properties["release_channel"])
        assertEquals(0, analytics.ignoredProperties)
    }
    @Test fun optOutResetThenReenableRestoresChannelWithoutChangingItToRelease() {
        val analytics = DisabledByDefaultAnalytics()
        analytics.enable("dev")
        analytics.optOut()
        assertTrue(analytics.properties.isEmpty())
        analytics.enable("dev")
        assertEquals(mapOf("release_channel" to "dev"), analytics.properties)
        assertEquals(0, analytics.ignoredProperties)
    }
    @Test fun restartingWithStoredConsentReappliesTheBuildsChannel() {
        for (channel in listOf("dev", "alpha", "beta", "release")) {
            val analytics = DisabledByDefaultAnalytics()
            analytics.properties["release_channel"] = "previous_build"
            analytics.enable(channel)
            assertEquals(channel, analytics.properties["release_channel"])
            assertEquals(0, analytics.ignoredProperties)
        }
    }
}
