package com.zerotoone.bottlemap.ui.owner

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Regression: an empty initial live cache must not send an approved Owner to registration. */
class OwnerEntryRoutingTest {
    @Test fun firstProductionEntryStaysOnOwnerDashboardWhenCacheIsEmpty() {
        assertFalse(shouldAutoOpenOwnerRegistrationIntro(
            usesProductionOwnerApi = true, startRegistration = false,
            barCount = 0, applicationCount = 0, hasDraft = false,
        ))
    }

    @Test fun productionEntryKeepsDashboardWhenOwnedBarsArrive() {
        assertFalse(shouldAutoOpenOwnerRegistrationIntro(
            usesProductionOwnerApi = true, startRegistration = false,
            barCount = 1, applicationCount = 0, hasDraft = false,
        ))
    }

    @Test fun mockOnboardingIntroBehaviorIsUnchanged() {
        assertTrue(shouldAutoOpenOwnerRegistrationIntro(
            usesProductionOwnerApi = false, startRegistration = false,
            barCount = 0, applicationCount = 0, hasDraft = false,
        ))
        assertFalse(shouldAutoOpenOwnerRegistrationIntro(
            usesProductionOwnerApi = false, startRegistration = false,
            barCount = 1, applicationCount = 0, hasDraft = false,
        ))
        assertFalse(shouldAutoOpenOwnerRegistrationIntro(
            usesProductionOwnerApi = false, startRegistration = true,
            barCount = 0, applicationCount = 0, hasDraft = false,
        ))
    }
}
