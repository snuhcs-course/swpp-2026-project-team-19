// AI-assisted test draft (2026-10-13, I2-P13/P14). Human test execution pending.
package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.data.CustomerSearchSource
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.MatchedProductDto
import com.zerotoone.bottlemap.network.SearchBarsResponseDto
import com.zerotoone.bottlemap.network.SearchOptionDto
import com.zerotoone.bottlemap.network.SearchResultDto
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class SearchResultsViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun cleanup() {
        Dispatchers.resetMain()
    }

    @Test
    fun requestUsesTrimmedQueryAndTransitionsLoadingToSuccess() = runTest(dispatcher) {
        val fake = FakeSource { response("Deanston 12", withBar = true) }
        val vm = SearchResultsViewModel(fake)

        vm.search("  Deanston 12  ")
        assertEquals(CustomerSearchUiState.Loading, vm.state.value)
        advanceUntilIdle()

        assertEquals(listOf("Deanston 12"), fake.requests)
        assertTrue(vm.state.value is CustomerSearchUiState.Success)
        assertEquals(1, (vm.state.value as CustomerSearchUiState.Success).results.size)
    }

    @Test
    fun noMatchAndNoSellingBarHaveDistinctEmptyStates() = runTest(dispatcher) {
        val fake = FakeSource { query -> response(query, matched = false) }
        val vm = SearchResultsViewModel(fake)
        vm.search("unknown")
        advanceUntilIdle()
        assertEquals(
            CustomerSearchUiState.Empty(EmptySearchReason.UNKNOWN_PRODUCT),
            vm.state.value,
        )

        fake.respond = { query -> response(query, withBar = false) }
        vm.search("known")
        advanceUntilIdle()
        assertEquals(
            CustomerSearchUiState.Empty(EmptySearchReason.NO_BARS),
            vm.state.value,
        )
    }

    @Test
    fun networkErrorThenRetryKeepsQueryAndSucceeds() = runTest(dispatcher) {
        var shouldFail = true
        val fake = FakeSource { query ->
            if (shouldFail) {
                shouldFail = false
                throw BottleMapApiException(code = "NETWORK_ERROR", message = "offline")
            }
            response(query, withBar = true)
        }
        val vm = SearchResultsViewModel(fake)

        vm.search("Ardbeg 10")
        advanceUntilIdle()
        assertTrue(vm.state.value is CustomerSearchUiState.Error)
        assertTrue((vm.state.value as CustomerSearchUiState.Error).message.contains("네트워크"))

        vm.retry()
        assertEquals(CustomerSearchUiState.Loading, vm.state.value)
        advanceUntilIdle()
        assertTrue(vm.state.value is CustomerSearchUiState.Success)
        assertEquals(listOf("Ardbeg 10", "Ardbeg 10"), fake.requests)
    }

    @Test
    fun oldResponseCannotOverrideNewerSearch() = runTest(dispatcher) {
        val gate = CompletableDeferred<SearchBarsResponseDto>()
        val fake = FakeSource { query ->
            if (query == "first") gate.await() else response(query, withBar = false)
        }
        val vm = SearchResultsViewModel(fake)

        vm.search("first")
        runCurrent()
        vm.search("second")
        advanceUntilIdle()
        assertEquals(
            CustomerSearchUiState.Empty(EmptySearchReason.NO_BARS),
            vm.state.value,
        )
        gate.complete(response("first", withBar = true))
        advanceUntilIdle()
        assertEquals(
            CustomerSearchUiState.Empty(EmptySearchReason.NO_BARS),
            vm.state.value,
        )
    }

    @Test
    fun serverErrorIsUserFriendly() {
        assertTrue(
            searchErrorMessage(
                BottleMapApiException(httpStatus = 503, code = "HTTP_503", message = "internal"),
            ).contains("서버"),
        )
    }

    private class FakeSource(
        var respond: suspend (String) -> SearchBarsResponseDto,
    ) : CustomerSearchSource {
        val requests = mutableListOf<String>()

        override suspend fun searchBars(query: String): SearchBarsResponseDto {
            requests.add(query)
            return respond(query)
        }
    }

    private fun response(
        query: String,
        matched: Boolean = true,
        withBar: Boolean = false,
    ): SearchBarsResponseDto = SearchBarsResponseDto(
        query = query,
        matchType = if (matched) "alias_exact" else "none",
        matchedProducts = if (matched) listOf(
            MatchedProductDto(
                productId = "product-1",
                displayName = "Deanston 12",
                brandName = "Deanston",
                resultCount = if (withBar) 1 else 0,
            ),
        ) else emptyList(),
        items = if (withBar) listOf(
            SearchResultDto(
                barId = "bar-1",
                barName = "Test Bar",
                address = "Gwanak-gu",
                latitude = 37.0,
                longitude = 126.0,
                productId = "product-1",
                productDisplayName = "Deanston 12",
                menuDisplayName = "Deanston 12",
                options = listOf(
                    SearchOptionDto(priceKrw = 15000, pourMl = null, sortOrder = 1),
                ),
                menuUpdatedAt = "2026-10-04T09:15:00Z",
            ),
        ) else emptyList(),
        truncated = false,
    )
}
