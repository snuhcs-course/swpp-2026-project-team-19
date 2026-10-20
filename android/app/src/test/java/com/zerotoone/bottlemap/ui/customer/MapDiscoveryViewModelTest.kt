package com.zerotoone.bottlemap.ui.customer

import androidx.lifecycle.SavedStateHandle
import com.zerotoone.bottlemap.data.MapBar
import com.zerotoone.bottlemap.data.MapBarsSource
import com.zerotoone.bottlemap.data.MapBounds
import com.zerotoone.bottlemap.data.NearbyBar
import com.zerotoone.bottlemap.data.NearbyBarsSource
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.data.NearbyLocationSource
import com.zerotoone.bottlemap.data.mapBoundsFromCorners
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
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
class MapDiscoveryViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val user = NearbyCoordinate(37.478, 126.951)
    private val moved = NearbyCoordinate(37.485, 126.960)
    private val a = MapBounds(37.475, 126.947, 37.480, 126.955)
    private val b = MapBounds(37.480, 126.955, 37.495, 126.975)

    @Before fun setup() { Dispatchers.setMain(dispatcher) }
    @After fun cleanup() { Dispatchers.resetMain() }

    private fun nearby(id: String) =
        NearbyBar(id, "Bar " + id, "Address", user, 8.0)
    private fun mapped(id: String, at: NearbyCoordinate = moved) =
        MapBar(id, "Bar " + id, "Address", at)

    private class NearbyFake : NearbyBarsSource {
        val calls = mutableListOf<Pair<NearbyCoordinate, Int>>()
        var current: List<NearbyBar> = emptyList()
        override suspend fun listNearbyBars(origin: NearbyCoordinate): List<NearbyBar> =
            listNearbyBars(origin, 1000)
        override suspend fun listNearbyBars(origin: NearbyCoordinate, radiusMeters: Int): List<NearbyBar> {
            calls += origin to radiusMeters
            return current
        }
    }

    private class MapFake : MapBarsSource {
        val calls = mutableListOf<MapBounds>()
        var bars: List<MapBar> = emptyList()
        var fail = false
        override suspend fun listMapBars(bounds: MapBounds): List<MapBar> {
            calls += bounds
            if (fail) throw IllegalStateException("offline")
            return bars
        }
    }

    private fun vm(nearby: NearbyBarsSource, map: MapBarsSource,
                   handle: SavedStateHandle = SavedStateHandle()) =
        NearbyBarsViewModel(
            object : NearbyLocationSource {
                override suspend fun currentLocation(): NearbyCoordinate = user
            }, nearby, handle, map)

    @Test fun mapUsesBoundsAndCarouselRemainsIndependent1000m() = runTest(dispatcher) {
        val near = NearbyFake().apply { current = listOf(nearby("near")) }
        val map = MapFake().apply { bars = listOf(mapped("far")) }
        val model = vm(near, map)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        assertEquals(listOf(user to 1000), near.calls)
        assertEquals(emptyList<MapBounds>(), map.calls)
        model.onViewportChanged(MapViewport(b))
        advanceUntilIdle()
        assertEquals(listOf(b), map.calls)
        assertEquals(listOf("near"), (model.state.value as NearbyUiState.Success).bars.map { it.barId })
        assertEquals(listOf("far"), model.markers.value.map { it.barId })
        assertEquals(b, (model.map.value as MapDiscoveryState.Ready).bounds)
    }

    @Test fun cameraMovesDebounceAndQueryLatestOnly() = runTest(dispatcher) {
        val map = MapFake()
        val model = vm(NearbyFake(), map)
        model.updatePermission(NearbyPermission.APPROXIMATE)
        advanceUntilIdle()
        model.onViewportChanged(MapViewport(a))
        advanceTimeBy(100)
        model.onViewportChanged(MapViewport(b))
        advanceUntilIdle()
        assertEquals(listOf(b), map.calls)
    }

    @Test fun sameViewportSkipsButNewZoomFetches() = runTest(dispatcher) {
        val map = MapFake()
        val model = vm(NearbyFake(), map)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        model.onViewportChanged(MapViewport(a))
        advanceUntilIdle()
        model.onViewportChanged(MapViewport(a.copy(south = a.south + 0.00001)))
        advanceUntilIdle()
        assertEquals(1, map.calls.size)
        model.onViewportChanged(MapViewport(b))
        advanceUntilIdle()
        assertEquals(2, map.calls.size)
    }

    @Test fun oversizedAreaSkipsApiShowsZoomInAndKeepsPriorMarkers() = runTest(dispatcher) {
        val map = MapFake().apply { bars = listOf(mapped("one")) }
        val model = vm(NearbyFake(), map)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        model.onViewportChanged(MapViewport(a))
        advanceUntilIdle()
        val tooWide = MapBounds(37.3, 126.80, 37.501, 126.96)
        model.onViewportChanged(MapViewport(tooWide))
        advanceUntilIdle()
        assertEquals(MapDiscoveryState.TooWide, model.map.value)
        assertEquals(listOf(a), map.calls)
        assertEquals(listOf("one"), model.markers.value.map { it.barId })
        map.bars = listOf(mapped("two"))
        model.onViewportChanged(MapViewport(b))
        advanceUntilIdle()
        assertEquals(listOf(a, b), map.calls)
        assertEquals(listOf("two"), model.markers.value.map { it.barId })
    }

    @Test fun partialCarouselNotNeededToSelectMapBar() = runTest(dispatcher) {
        val map = MapFake().apply { bars = listOf(mapped("remote")) }
        val model = vm(NearbyFake(), map)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        assertEquals(NearbyUiState.Empty, model.state.value)
        model.onViewportChanged(MapViewport(b))
        advanceUntilIdle()
        assertTrue(model.selectBar("remote"))
        assertFalse(model.selectBar("unknown"))
        assertEquals("remote", model.selectedBarId.value)
    }

    @Test fun mapErrorAndRetryDoNotChangeCarousel() = runTest(dispatcher) {
        val near = NearbyFake().apply { current = listOf(nearby("near")) }
        val map = MapFake().apply { fail = true }
        val model = vm(near, map)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        model.onViewportChanged(MapViewport(a))
        advanceUntilIdle()
        assertTrue(model.map.value is MapDiscoveryState.Error)
        assertEquals(listOf("near"), (model.state.value as NearbyUiState.Success).bars.map { it.barId })
        map.fail = false
        model.retryMap()
        advanceUntilIdle()
        assertTrue(model.map.value is MapDiscoveryState.Ready)
        assertEquals(listOf(a, a), map.calls)
    }

    @Test fun staleRequestCannotOverwriteMarkersEvenWhenBackendIgnoresCancel() = runTest(dispatcher) {
        val first = CompletableDeferred<List<MapBar>>()
        val second = CompletableDeferred<List<MapBar>>()
        val map = object : MapBarsSource {
            override suspend fun listMapBars(bounds: MapBounds): List<MapBar> =
                withContext(NonCancellable) { if (bounds == a) first.await() else second.await() }
        }
        val model = vm(NearbyFake(), map)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        model.onViewportChanged(MapViewport(a))
        advanceTimeBy(351); runCurrent()
        model.onViewportChanged(MapViewport(b))
        advanceTimeBy(351); runCurrent()
        second.complete(listOf(mapped("new")))
        runCurrent()
        assertEquals(listOf("new"), model.markers.value.map { it.barId })
        first.complete(listOf(mapped("old")))
        advanceUntilIdle()
        assertEquals(listOf("new"), model.markers.value.map { it.barId })
    }

    @Test fun previousMarkersRemainWhileNextAreaLoading() = runTest(dispatcher) {
        val map = MapFake().apply { bars = listOf(mapped("one")) }
        val model = vm(NearbyFake(), map)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        model.onViewportChanged(MapViewport(a)); advanceUntilIdle()
        map.bars = listOf(mapped("two"))
        model.onViewportChanged(MapViewport(b))
        assertEquals(MapDiscoveryState.Loading, model.map.value)
        assertEquals(listOf("one"), model.markers.value.map { it.barId })
        advanceUntilIdle()
        assertEquals(listOf("two"), model.markers.value.map { it.barId })
    }

    @Test fun permissionRevocationClearsMapAndPendingRequest() = runTest(dispatcher) {
        val map = MapFake()
        val model = vm(NearbyFake(), map)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        model.onViewportChanged(MapViewport(a))
        model.updatePermission(NearbyPermission.NONE)
        advanceUntilIdle()
        assertNull(model.origin.value)
        assertEquals(MapDiscoveryState.Initial, model.map.value)
        assertTrue(model.markers.value.isEmpty())
        assertEquals(emptyList<MapBounds>(), map.calls)
    }

    @Test fun detailReturnRestoresLastCameraButSearchExitClearsIt() = runTest(dispatcher) {
        val near = NearbyFake().apply { current = listOf(nearby("near")) }
        val model = vm(near, MapFake())
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        assertTrue(model.selectBar("near"))
        model.consumeFocusRequest()
        model.rememberCamera(moved, 13)
        assertEquals(DiscoveryCamera(moved, 13), model.savedCamera())
        assertNull(model.focusBarId.value)
        model.leaveDiscovery()
        assertNull(model.savedCamera())
        model.rememberCamera(moved, 13) // disposed MapView must not resurrect camera
        assertNull(model.savedCamera())
        model.beginDiscovery()
        model.rememberCamera(moved, 13)
        assertEquals(DiscoveryCamera(moved, 13), model.savedCamera())
    }

    @Test fun restoredSavedStateAndPermissionRecheckKeepCamera() = runTest(dispatcher) {
        val handle = SavedStateHandle(mapOf(
            "mapCenterLatitude" to moved.latitude,
            "mapCenterLongitude" to moved.longitude,
            "mapZoomLevel" to 18,
        ))
        val model = vm(NearbyFake(), MapFake(), handle)
        model.updatePermission(NearbyPermission.APPROXIMATE)
        advanceUntilIdle()
        assertEquals(DiscoveryCamera(moved, 18), model.savedCamera())
        model.refresh()
        advanceUntilIdle()
        assertNull(model.savedCamera())
        model.rememberCamera(NearbyCoordinate(95.0, 0.0), 16)
        assertNull(model.savedCamera())
    }

    @Test fun screenCornerBoundsRejectMissingAndSupportExactPoint() {
        val corners = listOf(
            NearbyCoordinate(37.48, 126.94),
            NearbyCoordinate(37.48, 126.96),
            NearbyCoordinate(37.47, 126.94),
            NearbyCoordinate(37.47, 126.96),
        )
        assertEquals(MapBounds(37.47, 126.94, 37.48, 126.96),
            mapBoundsFromCorners(corners))
        assertNull(mapBoundsFromCorners(corners.take(2)))
        assertFalse(MapBounds(37.3, 126.8, 37.501, 126.9).isSupportedByBackend())
        assertTrue(MapBounds(37.29, 126.8, 37.49, 127.0).isSupportedByBackend())
    }
}
