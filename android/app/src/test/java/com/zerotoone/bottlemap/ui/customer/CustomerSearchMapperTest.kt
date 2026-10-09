// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.network.MatchedProductDto
import com.zerotoone.bottlemap.network.SearchBarsResponseDto
import com.zerotoone.bottlemap.network.SearchOptionDto
import com.zerotoone.bottlemap.network.SearchResultDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CustomerSearchMapperTest {
    @Test
    fun unknownProduct_mapsToUnknownEmptyState() {
        val response = SearchBarsResponseDto(
            query = "not-a-product",
            matchType = "none",
            matchedProducts = emptyList(),
            items = emptyList(),
            truncated = false,
        )

        val state = response.toUiState()

        assertEquals(
            CustomerSearchUiState.Empty(EmptySearchReason.UNKNOWN_PRODUCT),
            state,
        )
    }

    @Test
    fun knownProductWithoutBars_mapsToNoBarsEmptyState() {
        val response = SearchBarsResponseDto(
            query = "Deanston 12",
            matchType = "alias_exact",
            matchedProducts = listOf(matchedProduct(resultCount = 0)),
            items = emptyList(),
            truncated = false,
        )

        val state = response.toUiState()

        assertEquals(
            CustomerSearchUiState.Empty(EmptySearchReason.NO_BARS),
            state,
        )
    }

    @Test
    fun success_preservesNullablePourAndParsesFractionalTimestamp() {
        val response = SearchBarsResponseDto(
            query = "Deanston 12",
            matchType = "alias_exact",
            matchedProducts = listOf(matchedProduct(resultCount = 1)),
            items = listOf(
                SearchResultDto(
                    barId = "bar-1",
                    barName = "Test Bar",
                    address = "Gwanak-gu",
                    latitude = 37.0,
                    longitude = 126.0,
                    productId = "product-1",
                    productDisplayName = "Deanston 12 Year Old",
                    menuDisplayName = "딘스톤 12",
                    options = listOf(
                        SearchOptionDto(
                            optionLabel = "병",
                            pourMl = null,
                            priceKrw = 180000,
                            sortOrder = 1,
                        ),
                    ),
                    menuUpdatedAt = "2026-10-04T09:15:00.123456Z",
                ),
            ),
            truncated = true,
        )

        val state = response.toUiState() as CustomerSearchUiState.Success

        assertEquals(1, state.results.size)
        assertTrue(state.truncated)
        assertNull(state.results.single().options.single().pourMl)
        assertEquals("병", state.results.single().options.single().optionLabel)
        assertTrue(state.results.single().menuUpdatedText.startsWith("Updated "))
        assertTrue(state.results.single().menuUpdatedText.contains("2026"))
    }

    private fun matchedProduct(resultCount: Int) = MatchedProductDto(
        productId = "product-1",
        displayName = "Deanston 12 Year Old",
        brandName = "Deanston",
        ageYears = 12,
        editionName = null,
        resultCount = resultCount,
    )
}
