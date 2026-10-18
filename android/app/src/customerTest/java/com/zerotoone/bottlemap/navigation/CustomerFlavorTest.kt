package com.zerotoone.bottlemap.navigation

import com.zerotoone.bottlemap.BuildConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class CustomerFlavorTest {
    @Test fun customerStartsWithoutRoleSelectionAndIsNotDeveloper() {
        assertEquals("customer", variantStartDestination)
        assertFalse(BuildConfig.DEVELOPER_BUILD)
    }
}
