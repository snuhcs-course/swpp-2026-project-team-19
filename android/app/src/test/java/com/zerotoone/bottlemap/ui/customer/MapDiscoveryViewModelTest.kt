package com.zerotoone.bottlemap.ui.customer

import androidx.lifecycle.SavedStateHandle
import com.zerotoone.bottlemap.data.NearbyBar
import com.zerotoone.bottlemap.data.NearbyBarsSource
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.data.NearbyLocationSource
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

    @Before fun setup() { Dispatchers.setMain(dispatcher) }
    @After fun cleanup() { Dispatchers.resetMain() }

    private fun item(id: String, center: NearbyCoordinate = user, meters: Double = 10.0) =
        NearbyBar(id, "Bar " + id, "Test address " + id, center, meters)

    private class Source : NearbyBarsSource {
        val calls = mutableListOf<Pair<NearbyCoordinate, Int>>()
        var current = listOf<NearbyBar>()
        var changed = listOf<NearbyBar>()
        var failMap = false
        override suspend fun listNearbyBars(origin: NearbyCoordinate): List<NearbyBar> =
            listNearbyBars(origin, 1000)
        override suspend fun listNearbyBars(origin: NearbyCoordinate, radiusMeters: Int): List<NearbyBar> {
            calls += origin to radiusMeters
            if (radiusMeters != 1000 && failMap) throw IllegalStateException("network")
            return if (radiusMeters == 1000) current else changed
        }
    }

    private fun vm(source: NearbyBarsSource, handle: SavedStateHandle = SavedStateHandle()) =
        NearbyBarsViewModel(
            object : NearbyLocationSource {
                override suspend fun currentLocation(): NearbyCoordinate = user
            }, source, handle)

    @Test fun initialCarouselIs1000mAndMapQueriesIndependently() = runTest(dispatcher) {
        val source = Source().apply {
            current = listOf(item("near"))
            changed = listOf(item("map", moved))
        }
        val model = vm(source)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        assertEquals(listOf(user to 1000), source.calls)
        assertEquals(user, model.origin.value)
        assertEquals(null, model.selectedBarId.value)
        model.onViewportChanged(NearbyViewport(moved, 2800))
        advanceUntilIdle()
        assertEquals(listOf(user to 1000, moved to 2800), source.calls)
        assertEquals(listOf("near"), (model.state.value as NearbyUiState.Success).bars.map { it.barId })
        assertEquals(listOf("map"), (model.map.value as MapDiscoveryState.Ready).bars.map { it.barId })
        assertEquals(listOf("map"), model.markers.value.map { it.barId })
    }

    @Test fun rapidCameraMovesDebounceToOneLatestRequest() = runTest(dispatcher) {
        val source = Source()
        val model = vm(source)
        model.updatePermission(NearbyPermission.APPROXIMATE)
        advanceUntilIdle()
        model.onViewportChanged(NearbyViewport(user, 1400))
        advanceTimeBy(100)
        model.onViewportChanged(NearbyViewport(moved, 2600))
        advanceUntilIdle()
        assertEquals(listOf(user to 1000, moved to 2600), source.calls)
    }

    @Test fun missingCarouselDoesNotSuppressMapAndAllowsMapMarkerSelection() = runTest(dispatcher) {
        val source = Source().apply { changed = listOf(item("far", moved)) }
        val model = vm(source)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        assertEquals(NearbyUiState.Empty, model.state.value)
        assertEquals(user, model.origin.value)
        model.onViewportChanged(NearbyViewport(moved, 1500))
        advanceUntilIdle()
        assertTrue(model.selectBar("far"))
        assertEquals("far", model.selectedBarId.value)
        assertFalse(model.selectBar("missing"))
    }

    @Test fun mapQueryFailureCanRetryWithoutDiscardingCarousel() = runTest(dispatcher) {
        val source = Source().apply { current = listOf(item("near")); failMap = true }
        val model = vm(source)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        model.onViewportChanged(NearbyViewport(moved, 2100))
        advanceUntilIdle()
        assertTrue(model.map.value is MapDiscoveryState.Error)
        assertEquals(listOf("near"), (model.state.value as NearbyUiState.Success).bars.map { it.barId })
        source.failMap = false
        model.retryMap()
        advanceUntilIdle()
        assertTrue(model.map.value is MapDiscoveryState.Ready)
        assertEquals(3, source.calls.size)
    }

    @Test fun requeryUnchangedViewportIsSkippedButZoomChangeIsFetched() = runTest(dispatcher) {
        val source = Source()
        val model = vm(source)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        model.onViewportChanged(NearbyViewport(user, 2000))
        advanceUntilIdle()
        model.onViewportChanged(NearbyViewport(user, 2020))
        advanceUntilIdle()
        assertEquals(2, source.calls.size)
        model.onViewportChanged(NearbyViewport(user, 2400))
        advanceUntilIdle()
        assertEquals(3, source.calls.size)
    }

    @Test fun oldSlowBackendResultMustNotOverwriteNewMarkers() = runTest(dispatcher) {
        val first = CompletableDeferred<List<NearbyBar>>()
        val second = CompletableDeferred<List<NearbyBar>>()
        val source = object : NearbyBarsSource {
            override suspend fun listNearbyBars(origin: NearbyCoordinate): List<NearbyBar> = listOf(item("near"))
            override suspend fun listNearbyBars(origin: NearbyCoordinate, radiusMeters: Int): List<NearbyBar> {
                if (radiusMeters == 1000) return listOf(item("near"))
                // Deliberately ignore cancellation to prove stale-request version protection.
                return withContext(NonCancellable) {
                    if (radiusMeters == 1700) first.await() else second.await()
                }
            }
        }
        val model = vm(source)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        model.onViewportChanged(NearbyViewport(user, 1700))
        advanceTimeBy(351); runCurrent()
        model.onViewportChanged(NearbyViewport(moved, 2000))
        advanceTimeBy(351); runCurrent()
        second.complete(listOf(item("new", moved)))
        runCurrent()
        assertEquals(listOf("new"), (model.map.value as MapDiscoveryState.Ready).bars.map { it.barId })
        first.complete(listOf(item("old")))
        advanceUntilIdle()
        assertEquals(listOf("new"), (model.map.value as MapDiscoveryState.Ready).bars.map { it.barId })
    }

    @Test fun permissionRevokedClearsLocationAndPendingMapState() = runTest(dispatcher) {
        val source = Source()
        val model = vm(source)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        model.onViewportChanged(NearbyViewport(user, 2000))
        model.updatePermission(NearbyPermission.NONE)
        advanceUntilIdle()
        assertNull(model.origin.value)
        assertEquals(MapDiscoveryState.Initial, model.map.value)
        assertEquals(NearbyUiState.PermissionRequired, model.state.value)
        assertEquals(1, source.calls.size)
    }

    @Test fun previousMarkersRemainVisibleWhileNewAreaLoads() = runTest(dispatcher) {
        val source = Source().apply { changed = listOf(item("one")) }
        val model = vm(source)
        model.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        model.onViewportChanged(NearbyViewport(user, 1500))
        advanceUntilIdle()
        assertEquals(listOf("one"), model.markers.value.map { it.barId })
        source.changed = listOf(item("two", moved))
        model.onViewportChanged(NearbyViewport(moved, 1600))
        assertEquals(MapDiscoveryState.Loading, model.map.value)
        assertEquals(listOf("one"), model.markers.value.map { it.barId })
        advanceUntilIdle()
        assertEquals(listOf("two"), model.markers.value.map { it.barId })
    }

    @Test fun viewportAt3kmLimitIsHonestAboutUncoveredArea() {
        val center = NearbyCoordinate(37.5, 126.9)
        val smallCorners = listOf(
            center.copy(latitude = 37.501), center.copy(latitude = 37.499),
            center.copy(longitude = 126.901), center.copy(longitude = 126.899),
        )
        val small = discoveryViewport(center, smallCorners)
        assertTrue(small.radiusMeters in 100..3000)
        assertFalse(small.partiallyCovered)
        val largeCorners = smallCorners.map { it.copy(latitude = it.latitude + 0.10) }
        val large = discoveryViewport(center, largeCorners)
        assertEquals(3000, large.radiusMeters)
        assertTrue(large.partiallyCovered)
        val unavailable = discoveryViewport(center, emptyList())
        assertEquals(3000, unavailable.radiusMeters)
        assertTrue(unavailable.partiallyCovered)
    }
}
