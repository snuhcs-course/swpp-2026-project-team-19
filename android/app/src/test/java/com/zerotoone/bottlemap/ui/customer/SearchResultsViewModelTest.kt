// AI-assisted test draft (2026-10-13, I2-P13/P14). Human test execution pending.
package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.data.CustomerSearchSource
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.FieldErrorDto
import com.zerotoone.bottlemap.network.MatchedProductDto
import com.zerotoone.bottlemap.network.SearchBarsResponseDto
import com.zerotoone.bottlemap.network.SearchOptionDto
import com.zerotoone.bottlemap.network.SearchResultDto
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
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
    fun koreanQueryIsSentWithoutClientSideAliasMatching() = runTest(dispatcher) {
        val fake = FakeSource { query -> response(query, withBar = false) }
        val vm = SearchResultsViewModel(fake)
        vm.search("  딘스톤 12  ")
        advanceUntilIdle()
        assertEquals(listOf("딘스톤 12"), fake.requests)
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
    fun barNotFoundRefreshesResultsWithoutChangingSearchQuery() = runTest(dispatcher) {
        val fake = FakeSource { response(it, withBar = true) }
        val vm = SearchResultsViewModel(fake)
        vm.search("Deanston 12")
        advanceUntilIdle()
        assertEquals(1, fake.requests.size)

        // Normal screen re-entry should not launch another search.
        vm.search("Deanston 12")
        advanceUntilIdle()
        assertEquals(1, fake.requests.size)

        // Only the BAR_NOT_FOUND navigation event requests a fresh result list.
        vm.refreshAfterMissingBar()
        advanceUntilIdle()
        assertEquals(listOf("Deanston 12", "Deanston 12"), fake.requests)
        assertTrue(vm.state.value is CustomerSearchUiState.Success)
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
    fun invalidQueryInvalidatesEvenAnUncancellableOlderRequest() = runTest(dispatcher) {
        val gate = CompletableDeferred<SearchBarsResponseDto>()
        val fake = FakeSource { query ->
            if (query == "first") {
                // Simulate a callback that returns despite request cancellation.
                withContext(NonCancellable) { gate.await() }
            } else response(query)
        }
        val vm = SearchResultsViewModel(fake)

        vm.search("first")
        runCurrent()
        vm.search("   ")
        assertEquals(CustomerSearchUiState.InvalidQuery("BLANK"), vm.state.value)
        gate.complete(response("first", withBar = true))
        advanceUntilIdle()

        assertEquals(CustomerSearchUiState.InvalidQuery("BLANK"), vm.state.value)
        assertEquals(listOf("first"), fake.requests)
    }

    @Test
    fun duplicateSearchDuringLoadingDoesNotSendSecondRequest() = runTest(dispatcher) {
        val gate = CompletableDeferred<SearchBarsResponseDto>()
        val fake = FakeSource { gate.await() }
        val vm = SearchResultsViewModel(fake)
        vm.search("Deanston 12")
        runCurrent()
        vm.search("  Deanston 12  ")
        runCurrent()
        assertEquals(listOf("Deanston 12"), fake.requests)
        gate.complete(response("Deanston 12", withBar = true))
        advanceUntilIdle()
        assertTrue(vm.state.value is CustomerSearchUiState.Success)
    }

    @Test
    fun recreatedResultsViewModelCanReloadFromRestoredQueryRoute() = runTest(dispatcher) {
        val fake = FakeSource { response(it, withBar = true) }
        val first = SearchResultsViewModel(fake)
        first.search("Ardbeg 10")
        advanceUntilIdle()

        // NavHost persists the query in its route; a new VM can re-fetch
        // after process recreation instead of parceling the entire result.
        val recreated = SearchResultsViewModel(fake)
        recreated.search("Ardbeg 10")
        advanceUntilIdle()

        assertTrue(recreated.state.value is CustomerSearchUiState.Success)
        assertEquals(listOf("Ardbeg 10", "Ardbeg 10"), fake.requests)
    }

    @Test
    fun serverErrorUsesApiCodeNotHttpStatus() {
        assertTrue(
            searchErrorMessage(
                BottleMapApiException(
                    httpStatus = 400,
                    code = "SERVICE_UNAVAILABLE",
                    message = "internal",
                ),
            ).contains("서버"),
        )
        assertTrue(
            searchErrorMessage(
                BottleMapApiException(
                    httpStatus = 503,
                    code = "UNEXPECTED_CODE",
                    message = "internal",
                ),
            ).contains("다시 시도"),
        )
    }

    @Test
    fun backendQueryValidationCodesReturnToInputWithoutRetry() = runTest(dispatcher) {
        for (fieldCode in listOf("MISSING", "BLANK", "STRING_TOO_LONG", "NOT_SEARCHABLE")) {
            val fake = FakeSource {
                throw BottleMapApiException(
                    httpStatus = 422,
                    code = "VALIDATION_FAILED",
                    message = "input error",
                    fieldErrors = listOf(
                        FieldErrorDto(
                            path = "query",
                            code = fieldCode,
                            message = "validation error",
                        ),
                    ),
                )
            }
            val vm = SearchResultsViewModel(fake)
            vm.search("!!!")
            advanceUntilIdle()
            assertEquals(CustomerSearchUiState.InvalidQuery(fieldCode), vm.state.value)
            vm.retry()
            advanceUntilIdle()
            assertEquals(listOf("!!!"), fake.requests)
            assertTrue(searchValidationMessage(fieldCode).isNotBlank())
        }
    }

    @Test
    fun unknownValidationFieldIsNotRetryable() = runTest(dispatcher) {
        val fake = FakeSource {
            throw BottleMapApiException(
                httpStatus = 422,
                code = "VALIDATION_FAILED",
                message = "input error",
                fieldErrors = listOf(
                    FieldErrorDto(path = "limit", code = "LESS_THAN_EQUAL", message = "invalid"),
                ),
            )
        }
        val vm = SearchResultsViewModel(fake)
        vm.search("Deanston 12")
        advanceUntilIdle()
        assertEquals(
            CustomerSearchUiState.Error("검색 요청의 입력값을 확인해 주세요.", canRetry = false),
            vm.state.value,
        )
        vm.retry()
        advanceUntilIdle()
        assertEquals(listOf("Deanston 12"), fake.requests)
    }

    @Test
    fun inputValidationStillRunsLocally() {
        val vm = SearchResultsViewModel(FakeSource { response(it) })
        vm.search("   ")
        assertEquals(CustomerSearchUiState.InvalidQuery("BLANK"), vm.state.value)
        vm.search("a".repeat(101))
        assertEquals(CustomerSearchUiState.InvalidQuery("STRING_TOO_LONG"), vm.state.value)
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
