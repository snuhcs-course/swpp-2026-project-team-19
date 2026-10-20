package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.data.MapPlace
import com.zerotoone.bottlemap.data.MapPlaceSearchSource
import com.zerotoone.bottlemap.data.NearbyCoordinate
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MapPlaceSearchViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val station = MapPlace(
        name = "서울역", address = "서울특별시 용산구",
        coordinate = NearbyCoordinate(37.5547, 126.9707))
    private val shop = MapPlace(
        name = "편의점", address = "서울특별시 관악구",
        coordinate = NearbyCoordinate(37.478, 126.951))

    @Before fun setup() { Dispatchers.setMain(dispatcher) }
    @After fun cleanup() { Dispatchers.resetMain() }

    private class FakeSource : MapPlaceSearchSource {
        val queries = mutableListOf<String>()
        var response = emptyList<MapPlace>()
        var shouldFail = false

        override suspend fun search(query: String): List<MapPlace> {
            queries += query
            if (shouldFail) throw IllegalStateException("offline")
            return response
        }
    }

    @Test fun stationAndStoreLookupStaysInMapViewModelAndSelectsCoordinate() = runTest(dispatcher) {
        val source = FakeSource().apply { response = listOf(station, shop) }
        val vm = MapPlaceSearchViewModel(source)
        vm.search("  서울역  ")
        assertEquals(MapPlaceSearchState.Loading, vm.state.value)
        advanceUntilIdle()
        assertEquals(listOf("서울역"), source.queries)
        assertEquals(listOf(station, shop),
            (vm.state.value as MapPlaceSearchState.Results).places)
        assertTrue(vm.select(shop))
        assertEquals(shop, vm.selected.value)
        assertEquals(shop, vm.focus.value)
        vm.consumeFocus()
        assertNull(vm.focus.value)
        assertEquals(shop, vm.selected.value)
    }

    @Test fun emptyAndTooLongSearchNeverCallDeviceGeocoder() = runTest(dispatcher) {
        val source = FakeSource()
        val vm = MapPlaceSearchViewModel(source)
        vm.search("  ")
        assertTrue(vm.state.value is MapPlaceSearchState.Error)
        vm.search("가".repeat(101))
        assertTrue(vm.state.value is MapPlaceSearchState.Error)
        advanceUntilIdle()
        assertTrue(source.queries.isEmpty())
    }

    @Test fun emptyResultsHaveExplicitStateAndCannotSelectArbitraryPlace() = runTest(dispatcher) {
        val vm = MapPlaceSearchViewModel(FakeSource())
        vm.search("없는매장")
        advanceUntilIdle()
        assertEquals(emptyList<MapPlace>(),
            (vm.state.value as MapPlaceSearchState.Results).places)
        assertFalse(vm.select(station))
        assertNull(vm.selected.value)
    }

    @Test fun failureShowsRetryableErrorWithoutInventingPlaces() = runTest(dispatcher) {
        val source = FakeSource().apply { shouldFail = true }
        val vm = MapPlaceSearchViewModel(source)
        vm.search("강남역")
        advanceUntilIdle()
        assertTrue(vm.state.value is MapPlaceSearchState.Error)
        source.shouldFail = false
        source.response = listOf(station)
        vm.search("서울역")
        advanceUntilIdle()
        assertEquals(listOf(station), (vm.state.value as MapPlaceSearchState.Results).places)
    }

    @Test fun staleResponseCannotOverwriteLatestPlaceQuery() = runTest(dispatcher) {
        val first = CompletableDeferred<List<MapPlace>>()
        val second = CompletableDeferred<List<MapPlace>>()
        val source = object : MapPlaceSearchSource {
            override suspend fun search(query: String): List<MapPlace> =
                withContext(NonCancellable) {
                    if (query == "first") first.await() else second.await()
                }
        }
        val vm = MapPlaceSearchViewModel(source)
        vm.search("first")
        runCurrent()
        vm.search("second")
        runCurrent()
        second.complete(listOf(shop))
        runCurrent()
        assertEquals(listOf(shop), (vm.state.value as MapPlaceSearchState.Results).places)
        first.complete(listOf(station))
        advanceUntilIdle()
        assertEquals(listOf(shop), (vm.state.value as MapPlaceSearchState.Results).places)
    }

    @Test fun closeResultsCancelsSearchAndClearRemovesMapPin() = runTest(dispatcher) {
        val source = FakeSource().apply { response = listOf(station) }
        val vm = MapPlaceSearchViewModel(source)
        vm.search("서울역")
        advanceUntilIdle()
        assertTrue(vm.select(station))
        vm.dismissResults()
        assertEquals(MapPlaceSearchState.Idle, vm.state.value)
        assertEquals(station, vm.selected.value)
        vm.clear()
        assertNull(vm.selected.value)
        assertNull(vm.focus.value)
    }

    @Test fun repeatedOrInvalidResultCoordinatesAreDiscarded() = runTest(dispatcher) {
        val source = FakeSource().apply {
            response = listOf(
                station, station,
                MapPlace("invalid", "?", NearbyCoordinate(91.0, 128.0)),
                MapPlace("zero", "?", NearbyCoordinate(0.0, 0.0)),
                shop,
            )
        }
        val vm = MapPlaceSearchViewModel(source)
        vm.search("서울")
        advanceUntilIdle()
        assertEquals(listOf(station, shop),
            (vm.state.value as MapPlaceSearchState.Results).places)
    }
}
