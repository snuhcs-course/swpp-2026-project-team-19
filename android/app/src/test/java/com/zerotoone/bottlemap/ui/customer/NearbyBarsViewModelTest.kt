// AI-assisted tests for I2-A7/A8. All data below is test-only, never live UI.
package com.zerotoone.bottlemap.ui.customer

import androidx.lifecycle.SavedStateHandle
import com.zerotoone.bottlemap.data.NearbyBar
import com.zerotoone.bottlemap.data.NearbyBarCandidate
import com.zerotoone.bottlemap.data.NearbyBarsSource
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.data.NearbyLocationServicesDisabledException
import com.zerotoone.bottlemap.data.NearbyLocationSource
import com.zerotoone.bottlemap.data.distanceMeters
import com.zerotoone.bottlemap.data.filterNearbyBars
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class NearbyBarsViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val origin = NearbyCoordinate(37.478321, 126.951234)

    @Before fun before() { Dispatchers.setMain(dispatcher) }
    @After fun after() { Dispatchers.resetMain() }

    private fun bar(
        id: String,
        latitude: Double? = origin.latitude,
        longitude: Double? = origin.longitude,
    ) = NearbyBarCandidate(
        barId = id,
        name = "테스트 바 $id",
        address = "테스트용 주소",
        location = if (latitude == null || longitude == null) null
        else NearbyCoordinate(latitude, longitude),
    )

    @Test
    fun radiusIncludesInsideAndExactly1000mAndExcludesOutside() {
        val equator = NearbyCoordinate(0.0, 0.0)
        val near = NearbyCoordinate(Math.toDegrees(999.0 / 6_371_000.0), 0.0)
        val boundary = NearbyCoordinate(Math.toDegrees(1000.0 / 6_371_000.0), 0.0)
        val far = NearbyCoordinate(Math.toDegrees(1001.0 / 6_371_000.0), 0.0)
        assertEquals(1000.0, distanceMeters(equator, boundary), 0.000001)
        val result = filterNearbyBars(
            equator,
            listOf(
                NearbyBarCandidate("far", "Far", "", far),
                NearbyBarCandidate("at500", "Boundary", "", boundary),
                NearbyBarCandidate("inside", "Near", "", near),
            ),
        )
        assertEquals(listOf("inside", "at500"), result.map { it.barId })
    }

    @Test
    fun sortsByDistanceThenIdAndRemovesDuplicateBarIds() {
        val oneHundredMeters = NearbyCoordinate(
            origin.latitude + Math.toDegrees(100.0 / 6_371_000.0),
            origin.longitude,
        )
        val result = filterNearbyBars(
            origin,
            listOf(
                bar("z", oneHundredMeters.latitude, oneHundredMeters.longitude),
                bar("z"), bar("b"), bar("a"),
            ),
        )
        assertEquals(listOf("a", "b", "z"), result.map { it.barId })
        assertEquals(3, result.size)
        assertEquals(0.0, result.first().distanceMeters, 0.001)
    }

    @Test
    fun excludesMissingInvalidNonFiniteAndSwappedCoordinates() {
        val invalid = listOf(
            bar("missing-lat", latitude = null),
            bar("missing-lng", longitude = null),
            bar("nan", latitude = Double.NaN),
            bar("infinity", longitude = Double.POSITIVE_INFINITY),
            bar("lat-range", latitude = 91.0),
            bar("lng-range", longitude = -181.0),
            bar("swapped", latitude = 126.951234, longitude = 37.478321),
            bar(" "),
            bar("valid"),
        )
        assertEquals(listOf("valid"), filterNearbyBars(origin, invalid).map { it.barId })
    }

    @Test
    fun permissionDeniedAndApproximateDoNotRequestLocation() = runTest(dispatcher) {
        val location = FakeLocation(origin)
        val source = FakeBars(listOf(bar("A")))
        val vm = NearbyBarsViewModel(location, source)
        vm.updatePermission(NearbyPermission.NONE)
        advanceUntilIdle()
        assertEquals(NearbyUiState.PermissionRequired, vm.state.value)
        vm.updatePermission(NearbyPermission.APPROXIMATE)
        advanceUntilIdle()
        assertTrue(vm.state.value is NearbyUiState.Success)
        vm.updatePermission(NearbyPermission.PERMANENTLY_DENIED)
        advanceUntilIdle()
        assertEquals(NearbyUiState.PermissionPermanentlyDenied, vm.state.value)
        assertEquals(1, location.count)
        assertEquals(1, source.count)
    }

    @Test
    fun precisePermissionTransitionsThroughLocationAndBarsToSuccess() = runTest(dispatcher) {
        val location = FakeLocation(origin)
        val source = FakeBars(listOf(bar("a"), bar("b")))
        val vm = NearbyBarsViewModel(location, source)
        vm.updatePermission(NearbyPermission.PRECISE)
        assertEquals(NearbyUiState.LoadingLocation, vm.state.value)
        advanceUntilIdle()
        assertTrue(vm.state.value is NearbyUiState.Success)
        assertEquals(null, vm.selectedBarId.value)
        assertEquals(1, location.count)
        assertEquals(1, source.count)
    }

    @Test
    fun empty500mResultIsDistinctFromBackendFailure() = runTest(dispatcher) {
        val vm = NearbyBarsViewModel(FakeLocation(origin), FakeBars(emptyList()))
        vm.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        assertEquals(NearbyUiState.Empty, vm.state.value)
        assertEquals(null, vm.selectedBarId.value)
    }

    @Test
    fun errorRetrySucceedsWithoutAutoPermissionPrompt() = runTest(dispatcher) {
        val location = FakeLocation(origin)
        val source = FakeBars(listOf(bar("a")))
        source.failure = IllegalStateException("offline")
        val vm = NearbyBarsViewModel(location, source)
        vm.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        assertTrue(vm.state.value is NearbyUiState.Error)
        source.failure = null
        vm.refresh()
        advanceUntilIdle()
        assertTrue(vm.state.value is NearbyUiState.Success)
        assertEquals(2, source.count)
    }

    @Test
    fun api404BeforeBackendDeploymentIsNotDisplayedAsEmpty() = runTest(dispatcher) {
        val source = FakeBars(emptyList())
        source.failure = com.zerotoone.bottlemap.network.BottleMapApiException(
            httpStatus = 404,
            code = "HTTP_404",
            message = "endpoint missing",
        )
        val vm = NearbyBarsViewModel(FakeLocation(origin), source)
        vm.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        val error = vm.state.value as NearbyUiState.Error
        assertTrue(error.message.contains("아직 제공하지 않습니다"))
    }

    @Test
    fun serverIncludedRounded500mBarIsNotLocallyRefiltered() = runTest(dispatcher) {
        val beyondRadius = NearbyCoordinate(
            origin.latitude + Math.toDegrees(500.4 / 6_371_000.0),
            origin.longitude,
        )
        assertTrue(distanceMeters(origin, beyondRadius) > 500.0)
        val source = object : NearbyBarsSource {
            override suspend fun listNearbyBars(origin: NearbyCoordinate): List<NearbyBar> =
                listOf(NearbyBar(
                    barId = "rounded-edge",
                    name = "Backend rounded edge",
                    address = "Test",
                    location = beyondRadius,
                    distanceMeters = 500.0,
                ))
        }
        val vm = NearbyBarsViewModel(FakeLocation(origin), source)
        vm.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        val result = vm.state.value as NearbyUiState.Success
        assertEquals(listOf("rounded-edge"), result.bars.map { it.barId })
        assertEquals(500.0, result.bars.first().distanceMeters, 0.0001)
    }

    @Test
    fun permissionRevokedWhileLoadingIsHandled() = runTest(dispatcher) {
        val location = FakeLocation(origin)
        val source = FakeBars(listOf(bar("a")))
        val vm = NearbyBarsViewModel(location, source)
        vm.updatePermission(NearbyPermission.PRECISE)
        vm.updatePermission(NearbyPermission.NONE)
        advanceUntilIdle()
        assertEquals(NearbyUiState.PermissionRequired, vm.state.value)
        assertEquals(0, source.count)
    }

    @Test
    fun locationServicesDisabledHasRecoveryState() = runTest(dispatcher) {
        val location = FakeLocation(origin)
        location.failure = NearbyLocationServicesDisabledException()
        val vm = NearbyBarsViewModel(location, FakeBars(emptyList()))
        vm.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        assertEquals(NearbyUiState.LocationServicesDisabled, vm.state.value)
    }

    @Test
    fun carouselAndMarkerSelectionBothUseSameSavedBarId() = runTest(dispatcher) {
        val handle = SavedStateHandle()
        val vm = NearbyBarsViewModel(
            FakeLocation(origin),
            FakeBars(listOf(bar("a"), bar("b"))),
            handle,
        )
        vm.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        assertTrue(vm.selectBar("b")) // Carousel click.
        assertEquals("b", vm.selectedBarId.value)
        assertTrue(vm.selectBar("a")) // Kakao label click.
        assertEquals("a", handle.get<String>("nearbySelectedBarId"))
        assertFalse(vm.selectBar("unknown-marker"))
        assertEquals("a", vm.selectedBarId.value)
    }

    @Test
    fun retryPreservesSelectedBarIfItStillExists() = runTest(dispatcher) {
        val vm = NearbyBarsViewModel(FakeLocation(origin), FakeBars(listOf(bar("a"), bar("b"))))
        vm.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        assertTrue(vm.selectBar("b"))
        vm.refresh()
        advanceUntilIdle()
        assertEquals("b", vm.selectedBarId.value)
    }

    @Test
    fun backgroundPermissionRecheckDoesNotRepeatSuccessfulNetworkRequest() = runTest(dispatcher) {
        val location = FakeLocation(origin)
        val source = FakeBars(listOf(bar("a")))
        val vm = NearbyBarsViewModel(location, source)
        vm.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        vm.updatePermission(NearbyPermission.PRECISE)
        advanceUntilIdle()
        assertEquals(1, location.count)
        assertEquals(1, source.count)
    }

    private class FakeLocation(private val origin: NearbyCoordinate) : NearbyLocationSource {
        var count = 0
        var failure: Exception? = null
        override suspend fun currentLocation(): NearbyCoordinate {
            count++
            failure?.let { throw it }
            return origin
        }
    }

    private class FakeBars(var items: List<NearbyBarCandidate>) : NearbyBarsSource {
        var count = 0
        var failure: Exception? = null
        override suspend fun listNearbyBars(
            origin: NearbyCoordinate,
        ): List<NearbyBar> {
            count++
            failure?.let { throw it }
            // Fake test-only catalog. The production Backend A9 adapter uses
            // authoritative server results directly, without this filter.
            return filterNearbyBars(origin, items)
        }
    }
}
