package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.data.CustomerBarDetailSource
import com.zerotoone.bottlemap.network.BarMenuItemDto
import com.zerotoone.bottlemap.network.BarMenuOptionDto
import com.zerotoone.bottlemap.network.BarMenuResponseDto
import com.zerotoone.bottlemap.network.BottleMapApiException
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
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class BarDetailViewModelTest {
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
    fun settledValidSearchWithNoMatchesShowsCenteredEmptyHint() {
        val settled = BarAliasLookupState(query = "찾을수없는메뉴")
        assertTrue(barMenuSearchHasNoResults(
            "찾을수없는메뉴", true, false, null, settled))
        assertFalse(barMenuSearchHasNoResults(
            "", true, false, null, settled))
        assertFalse(barMenuSearchHasNoResults(
            "찾을수없는메뉴", false, false, null, settled))
        assertFalse(barMenuSearchHasNoResults(
            "찾을수없는메뉴", true, true, null, settled))
        assertFalse(barMenuSearchHasNoResults(
            "!!!", true, false, "검색할 수 있는 문자가 없어요.",
            BarAliasLookupState(query = "!!!", validationMessage = "invalid")))
        assertFalse(barMenuSearchHasNoResults(
            "찾을수없는메뉴", true, false, null, null)) // debouncing
        assertFalse(barMenuSearchHasNoResults(
            "찾을수없는메뉴", true, false, null,
            BarAliasLookupState(query = "찾을수없는메뉴", loading = true)))
        assertFalse(barMenuSearchHasNoResults(
            "찾을수없는메뉴", true, false, null,
            BarAliasLookupState(query = "찾을수없는메뉴", failed = true)))
        assertFalse(barMenuSearchHasNoResults(
            "찾을수없는메뉴", true, false, null,
            BarAliasLookupState(query = "이전검색어")))
    }

    @Test
    fun barDetailUnsearchableQueryShowsValidationNotNetworkRetry() {
        assertEquals("검색할 수 있는 문자가 없어요. 검색어를 다시 입력해 주세요.",
            barAliasLocalValidation("!!!"))
        assertEquals("검색할 수 있는 문자가 없어요. 검색어를 다시 입력해 주세요.",
            barAliasLocalValidation(" - - "))
        assertNull(barAliasLocalValidation(""))
        assertNull(barAliasLocalValidation("맥캘란 12"))
        assertNull(barAliasLocalValidation("a"))
        assertEquals("검색어는 100자 이내로 입력해 주세요.",
            barAliasLocalValidation("a".repeat(101)))
        val invalidQuery = BottleMapApiException(
            httpStatus = 422, code = "VALIDATION_FAILED", message = "Invalid query",
            fieldErrors = listOf(com.zerotoone.bottlemap.network.FieldErrorDto(
                "query", "NOT_SEARCHABLE", "Invalid text")))
        assertEquals("검색할 수 있는 문자가 없어요. 검색어를 다시 입력해 주세요.",
            barAliasServerValidation(invalidQuery))
        assertNull(barAliasServerValidation(BottleMapApiException(
            httpStatus = 503, code = "HTTP_503", message = "Temporary failure")))
    }

    @Test
    fun queryScopedValidationDoesNotRemainAfterNewSearchText() {
        val invalid = BarAliasLookupState(query = "!!!", validationMessage =
            "검색할 수 있는 문자가 없어요. 검색어를 다시 입력해 주세요.")
        assertEquals(invalid, queryScopedBarAlias(invalid, "!!!"))
        assertNull(queryScopedBarAlias(invalid, "아드벡"))
        assertNull(queryScopedBarAlias(invalid, ""))
        val retryable = BarAliasLookupState(query = "아드벡", failed = true)
        assertEquals(retryable, queryScopedBarAlias(retryable, "아드벡"))
        assertNull(queryScopedBarAlias(retryable, "!!!"))
    }

    @Test
    fun aliasFallbackTriggersOnlyForActualLocalMiss() {
        assertTrue(barAliasLookupNeeded("ardbeg10", hasLocalMatch = false))
        assertFalse(barAliasLookupNeeded("ardbeg10", hasLocalMatch = true))
        // §3.10 accepts one searchable character and no artificial 2-char limit.
        assertTrue(barAliasLookupNeeded("a", hasLocalMatch = false))
        assertFalse(barAliasLookupNeeded("  ", hasLocalMatch = false))
        assertFalse(barAliasLookupNeeded("!!!", hasLocalMatch = false))
    }

    @Test
    fun strippedPunctuationNeverMatchesEveryBarMenu() {
        assertFalse(barMenuMatchesQuery("라가불린 16", "라가불린", "---"))
        assertFalse(barMenuMatchesQuery("라가불린 16", "라가불린", " - - "))
        assertTrue(barMenuMatchesQuery("라가불린 16", "라가불린", ""))
        assertTrue(barMenuMatchesQuery("라가불린 16", "라가불린", "라가-불린"))
    }

    @Test
    fun aliasFallbackStatesDoNotLeakAcrossEditedQueries() {
        val failed = BarAliasLookupState(query = "ardbeg10", failed = true)
        assertEquals(failed, queryScopedBarAlias(failed, "ardbeg10"))
        assertNull(queryScopedBarAlias(failed, "lagavulin"))
        assertNull(queryScopedBarAlias(failed, ""))
        val loading = BarAliasLookupState(query = "ardbeg10", loading = true)
        assertTrue(queryScopedBarAlias(loading, "ardbeg10")!!.loading)
        val ready = BarAliasLookupState(query = "ardbeg10", productIds = setOf("p-1"))
        assertEquals(setOf("p-1"), queryScopedBarAlias(ready, "ardbeg10")!!.productIds)
        assertNull(queryScopedBarAlias(ready, "ardbeg10 16"))
    }

    @Test
    fun loadsGivenBarIdAndPreservesAllPublishedEntriesAndOptions() = runTest(dispatcher) {
        val fake = FakeSource { response(it) }
        val vm = BarDetailViewModel(fake)
        vm.load("bar-1")
        assertEquals(BarDetailUiState.Loading, vm.state.value)
        advanceUntilIdle()

        val result = vm.state.value as BarDetailUiState.Success
        assertEquals(listOf("bar-1"), fake.requests)
        assertEquals("관악 위스키 바", result.bar.name)
        assertEquals(2, result.bar.items.size)
        assertEquals("글렌피딕 12년", result.bar.items[0].menuDisplayName)
        assertEquals("잔 · 30 ml  ₩17,000", result.bar.items[0].options[0].text)
        assertEquals("병  ₩160,000", result.bar.items[0].options[1].text)
        assertEquals("Deanston 12", result.bar.items[1].menuDisplayName)
        assertTrue(result.bar.publishedAtText!!.contains("2026"))
        assertEquals(37.478321, result.bar.latitude!!, 0.000001)
        assertEquals(126.951234, result.bar.longitude!!, 0.000001)
    }

    @Test
    fun emptyMenuDistinguishesNoPublicationFromEmptyPublishedBoard() {
        val neverPublished = response("bar-1").copy(
            menuBoardId = null,
            publishedAt = null,
            items = emptyList(),
            phone = null,
        ).toBarDetailUiState() as BarDetailUiState.Empty
        assertEquals(EmptyMenuReason.NO_PUBLISHED_MENU, neverPublished.reason)
        assertNull(neverPublished.bar.publishedAtText)
        assertNull(neverPublished.bar.phone)

        val emptyPublished = response("bar-1").copy(items = emptyList())
            .toBarDetailUiState() as BarDetailUiState.Empty
        assertEquals(EmptyMenuReason.NO_CURRENT_ITEMS, emptyPublished.reason)
        assertTrue(emptyPublished.bar.publishedAtText!!.contains("2026"))
    }

    @Test
    fun nullableLabelsAndPourSizesDoNotInventValues() {
        assertEquals("₩18,000", formatBarMenuOption(null, null, 18_000))
        assertEquals("병  ₩160,000", formatBarMenuOption("병", null, 160_000))
        assertEquals("30 ml  ₩15,000", formatBarMenuOption(null, 30, 15_000))
        assertEquals("잔 · 30 ml  ₩17,000", formatBarMenuOption("잔", 30, 17_000))
        val invalidDate = response("bar-1").copy(publishedAt = "broken")
            .toBarDetailUiState() as BarDetailUiState.Success
        assertEquals("갱신일 확인 불가", invalidDate.bar.publishedAtText)
    }

    @Test
    fun networkFailureThenRetryPreservesBarIdAndSucceeds() = runTest(dispatcher) {
        var first = true
        val fake = FakeSource { id ->
            if (first) {
                first = false
                throw BottleMapApiException(code = "NETWORK_ERROR", message = "offline")
            }
            response(id)
        }
        val vm = BarDetailViewModel(fake)
        vm.load("bar-2")
        advanceUntilIdle()
        val error = vm.state.value as BarDetailUiState.Error
        assertTrue(error.canRetry)
        assertTrue(error.message.contains("네트워크"))
        vm.retry()
        assertEquals(BarDetailUiState.Loading, vm.state.value)
        advanceUntilIdle()
        assertTrue(vm.state.value is BarDetailUiState.Success)
        assertEquals(listOf("bar-2", "bar-2"), fake.requests)
    }

    @Test
    fun mismatchedResponseCannotReplaceSelectedBarAndRetryUsesOriginalId() = runTest(dispatcher) {
        var returnWrongBar = true
        val fake = FakeSource { requestedId ->
            if (returnWrongBar) {
                returnWrongBar = false
                response("different-bar")
            } else {
                response(requestedId)
            }
        }
        val vm = BarDetailViewModel(fake)
        vm.load("selected-bar")
        advanceUntilIdle()
        assertTrue(vm.state.value is BarDetailUiState.Error)

        vm.retry()
        advanceUntilIdle()
        val result = vm.state.value as BarDetailUiState.Success
        assertEquals("selected-bar", result.bar.barId)
        assertEquals(listOf("selected-bar", "selected-bar"), fake.requests)
    }

    @Test
    fun recreatedBarDetailViewModelCanReloadUsingRestoredRouteId() = runTest(dispatcher) {
        val fake = FakeSource { response(it) }
        val first = BarDetailViewModel(fake)
        first.load("bar-17")
        advanceUntilIdle()

        val recreated = BarDetailViewModel(fake)
        recreated.load("bar-17")
        advanceUntilIdle()

        assertEquals("bar-17", (recreated.state.value as BarDetailUiState.Success).bar.barId)
        assertEquals(listOf("bar-17", "bar-17"), fake.requests)
    }

    @Test
    fun serverUnavailableKeepsRecoverableRetryState() {
        val error = classifyBarDetailError(
            BottleMapApiException(
                code = "SERVICE_UNAVAILABLE",
                httpStatus = 503,
                message = "unavailable",
            ),
        )
        assertTrue(error.canRetry)
        assertTrue(error.message.contains("일시적으로"))
    }

    @Test
    fun barNotFoundShowsBackActionAndDisablesRetry() = runTest(dispatcher) {
        val fake = FakeSource {
            throw BottleMapApiException(
                httpStatus = 404, code = "BAR_NOT_FOUND", message = "not found",
            )
        }
        val vm = BarDetailViewModel(fake)
        vm.load("missing-bar")
        advanceUntilIdle()
        val error = vm.state.value as BarDetailUiState.Error
        assertFalse(error.canRetry)
        assertTrue(error.refreshResultsOnBack)
        vm.retry()
        advanceUntilIdle()
        assertEquals(listOf("missing-bar"), fake.requests)
    }

    @Test
    fun sameBarIdDoesNotRefetchAfterNavigationOrRecomposition() = runTest(dispatcher) {
        val fake = FakeSource { response(it) }
        val vm = BarDetailViewModel(fake)
        vm.load("bar-1")
        advanceUntilIdle()
        vm.load("bar-1")
        advanceUntilIdle()
        assertEquals(listOf("bar-1"), fake.requests)
    }

    @Test
    fun oldResponseCannotOverwriteNewBar() = runTest(dispatcher) {
        val gate = CompletableDeferred<BarMenuResponseDto>()
        val fake = FakeSource {
            if (it == "old-bar") gate.await() else response(it)
        }
        val vm = BarDetailViewModel(fake)
        vm.load("old-bar")
        runCurrent()
        vm.load("new-bar")
        advanceUntilIdle()
        assertEquals("new-bar", (vm.state.value as BarDetailUiState.Success).bar.barId)
        gate.complete(response("old-bar"))
        advanceUntilIdle()
        assertEquals("new-bar", (vm.state.value as BarDetailUiState.Success).bar.barId)
    }

    private class FakeSource(
        val respond: suspend (String) -> BarMenuResponseDto,
    ) : CustomerBarDetailSource {
        val requests = mutableListOf<String>()
        override suspend fun getPublishedBarMenu(barId: String): BarMenuResponseDto {
            requests.add(barId)
            return respond(barId)
        }
    }

    private fun response(barId: String): BarMenuResponseDto = BarMenuResponseDto(
        barId = barId,
        name = "관악 위스키 바",
        address = "서울특별시 관악구",
        latitude = 37.478321,
        longitude = 126.951234,
        phone = null,
        menuBoardId = "board-1",
        publishedAt = "2026-10-04T09:15:00Z",
        items = listOf(
            BarMenuItemDto(
                menuBoardEntryId = "entry-1",
                barMenuItemId = "item-1",
                productId = "canonical-1",
                displayName = "글렌피딕 12년",
                sortOrder = 1,
                options = listOf(
                    BarMenuOptionDto("option-1", "잔", 30, 17_000, 1),
                    BarMenuOptionDto("option-2", "병", null, 160_000, 2),
                ),
            ),
            BarMenuItemDto(
                menuBoardEntryId = "entry-2",
                barMenuItemId = "item-2",
                productId = "canonical-2",
                displayName = "Deanston 12",
                sortOrder = 2,
                options = listOf(
                    BarMenuOptionDto("option-3", null, 15, 8_000, 1),
                ),
            ),
        ),
    )
}
