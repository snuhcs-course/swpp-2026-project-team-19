package com.zerotoone.bottlemap.navigation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OwnerNavigationContractTest {
    @Test fun unifiedBuildStillStartsWithCustomer() {
        assertEquals("customer", variantStartDestination)
        assertEquals("owner", OwnerRoutes.GRAPH)
    }

    @Test fun allOwnerPreviewRoutesAreUniqueAndNamed() {
        val pages = OwnerPage.entries
        assertEquals(pages.size, pages.map { it.route }.toSet().size)
        assertTrue(pages.all { it.route.startsWith("owner/ux/") && it.title.isNotBlank() })
    }

    @Test fun groupedRoutesIncludeHoursTagsPhotosAndReview() {
        OwnerFlowGroup.entries.forEach { group ->
            val first = OwnerPage.entries.first { it.group == group }
            assertEquals(first.route, OwnerRoutes.groupStart(group))
            assertTrue(OwnerPage.entries.any { it.group == group && it.next() == null })
        }
        assertTrue(OwnerPage.entries.any { it.htmlId == "photoEdit" })
        assertTrue(OwnerPage.entries.any { it.htmlId == "s13sum" })
        assertTrue(OwnerPage.entries.any { it.htmlId == "hours" })
        assertTrue(OwnerPage.entries.any { it.htmlId == "tags" })
    }
}
