package com.zerotoone.bottlemap.navigation

import com.zerotoone.bottlemap.BuildConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

/** Regression for the removed developer/customer flavor split. */
class UnifiedBuildRegressionTest {
    @Test fun unifiedBuildStartsInCustomerWithoutModeSelection() {
        assertEquals("customer", variantStartDestination)
        assertFalse(variantStartDestination == "mode-selection")
        assertEquals("com.zerotoone.bottlemap", BuildConfig.APPLICATION_ID)
    }
}
