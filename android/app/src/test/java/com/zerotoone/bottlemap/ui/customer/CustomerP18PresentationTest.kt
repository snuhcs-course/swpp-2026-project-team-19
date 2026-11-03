package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.network.SearchOptionDto
import com.zerotoone.bottlemap.network.SearchResultDto
import org.junit.Assert.assertEquals
import org.junit.Test

/** Independent P18 HTML component oracle: 30ml preferred; nearest volume and larger tie. */
class CustomerP18PresentationTest {
    private fun option(ml: Int?, price: Int, order: Int = 0) =
        SearchOptionDto(pourMl = ml, priceKrw = price, sortOrder = order)

    private fun bar(name: String, distance: Int?, price: Int, updated: String) =
        SearchResultDto(
            barId = name, barName = name, address = "서울", latitude = 37.48,
            longitude = 126.95, distanceMeters = distance, productId = "p",
            productDisplayName = "Glenfiddich 12", menuDisplayName = "12년",
            options = listOf(option(30, price)), menuUpdatedAt = updated,
        )

    @Test fun representativeThirtyMillilitersBeatsCheaperFifteen() {
        val options = listOf(option(15, 9000), option(30, 17000), option(45, 24000))
        assertEquals(30, p18Representative(options)?.pourMl)
        assertEquals(17000, p18Representative(options)?.priceKrw)
    }

    @Test fun representativeTiePrefersLargerVolume() {
        val options = listOf(option(25, 13000), option(35, 19000))
        assertEquals(35, p18Representative(options)?.pourMl)
    }

    @Test fun priceSortUsesVisibleServingPriceNotPricePerMilliliter() {
        val bars = listOf(
            bar("A", 350, 17000, "2026-10-18T10:00:00Z"),
            bar("B", 410, 15000, "2026-10-04T10:00:00Z"),
        )
        assertEquals(listOf("B", "A"), p18Sorted(bars, P18Sort.PRICE, true).map { it.barName })
        assertEquals(listOf("A", "B"), p18Sorted(bars, P18Sort.DISTANCE, true).map { it.barName })
    }

    @Test fun updateSortPlacesNewestFirst() {
        val bars = listOf(
            bar("old", null, 9000, "2026-10-01T10:00:00Z"),
            bar("new", null, 17000, "2026-10-18T10:00:00Z"),
        )
        assertEquals(listOf("new", "old"), p18Sorted(bars, P18Sort.UPDATED, false).map { it.barName })
    }

    @Test fun distanceFormattingMatchesPdf() {
        assertEquals("350m", p18Distance(350))
        assertEquals("1.8km", p18Distance(1800))
    }
}
