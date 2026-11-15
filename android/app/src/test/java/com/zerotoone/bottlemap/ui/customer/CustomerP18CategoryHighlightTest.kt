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
        assertTrue("whisky" in expanded)
        assertTrue("whiskey" in expanded)
        assertTrue("food" in expanded)
        assertTrue("gin" in expanded)
        assertTrue("rum" in expanded)
    }

    @Test fun onlyTheHighlightedNonWhiskyCategoryIsInitiallyExpanded() {
        for(target in listOf("brandy","gin","rum","wine","beer","food","other")) {
            val collapsed = p18InitiallyCollapsedCategories(target.uppercase())
            assertFalse(target in collapsed)
            assertTrue("whisky" in collapsed)
            assertTrue("whiskey" in collapsed)
        }
        val whisky = p18InitiallyCollapsedCategories("whisky")
        assertFalse("whisky" in whisky)
        assertTrue("brandy" in whisky)
    }

    @Test fun whiskySearchDoesNotChangeOtherCategoryState() {
        assertEquals(p18InitiallyCollapsedCategories(null) + "whiskey",
            p18InitiallyCollapsedCategories("whisky"))
    }

    @Test fun normalBarVisitDoesNotSelectProductlessCategoryAsSearchHighlight() {
        val rows = listOf(
            BarMenuItemUiModel(menuBoardEntryId = "other-first", productId = null,
                menuDisplayName = "칵테일", options = emptyList(), category = "cocktail"),
            BarMenuItemUiModel(menuBoardEntryId = "whisky", productId = "whisky-a",
                menuDisplayName = "위스키", options = emptyList(), category = "whisky"),
        )
        val ordinary = p18HighlightedCategory(rows, null)
        assertNull(ordinary)
        assertEquals(p18InitiallyCollapsedCategories(null),
            p18InitiallyCollapsedCategories(ordinary))
        assertFalse("whisky" in p18InitiallyCollapsedCategories(ordinary))
        assertTrue("cocktail" in p18InitiallyCollapsedCategories(ordinary))

        assertNull(p18HighlightedCategory(rows, "missing-id"))
        assertEquals("whisky", p18HighlightedCategory(rows, "whisky-a"))
        assertNull(p18HighlightedCategory(rows, ""))
    }
}
