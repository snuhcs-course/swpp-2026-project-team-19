package com.zerotoone.bottlemap.ui.customer

import org.junit.Assert.*
import org.junit.Test

class CustomerP18CategoryHighlightTest {
    @Test fun defaultAccordionRemainsUnchangedWithoutProductSearch() {
        val default = p18InitiallyCollapsedCategories(null)
        assertTrue("brandy" in default)
        assertTrue("cocktail" in default)
        assertTrue("food" in default)
        assertFalse("whisky" in default)
    }

    @Test fun onlySearchHitNonWhiskyCategoryOpens() {
        val expanded = p18InitiallyCollapsedCategories("Brandy")
        assertFalse("brandy" in expanded)
        assertTrue("food" in expanded)
        assertTrue("gin" in expanded)
        assertTrue("rum" in expanded)
    }

    @Test fun whiskySearchDoesNotChangeOtherCategoryState() {
        assertEquals(p18InitiallyCollapsedCategories(null),
            p18InitiallyCollapsedCategories("whisky"))
    }
}
