package com.zerotoone.bottlemap.navigation

import com.zerotoone.bottlemap.BuildConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DeveloperFlavorTest {
    @Test fun developerPreservesOwnerSelectionRoute() {
        assertEquals("mode-selection", variantStartDestination)
        assertTrue(BuildConfig.DEVELOPER_BUILD)
    }
}
