package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.data.CustomerDiscoverySource
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.network.*
import com.zerotoone.bottlemap.telemetry.FakeTelemetry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import org.junit.After
import org.junit.Before
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class OnDeviceSearchTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setup() { Dispatchers.setMain(dispatcher) }
    @After fun cleanup() { Dispatchers.resetMain() }

    @Test fun lateGpsPermissionRevocationAndReentryNeverRepeatTheSearch() = runTest(dispatcher) {
        var calls = 0
        val response = SearchBarsResponseDto("synthetic","brand",truncated=true)
        val source = object: CustomerDiscoverySource {
            override suspend fun popularProducts(limit:Int):PopularProductsResponseDto = error("unused")
            override suspend fun searchProduct(query:String?,productId:String?,source:String):SearchBarsResponseDto {
                calls++
                return response
            }
        }
        val telemetry = FakeTelemetry()
        val vm = P18SearchViewModel(source,telemetry)
        vm.load("synthetic",null,"input")
        advanceUntilIdle()
        assertEquals(P18SearchState.Ready(response),vm.state.value)
        vm.setLocation(NearbyCoordinate(37.478,126.951))
        vm.load("synthetic",null,"input")
        vm.clearLocation()
        vm.load("synthetic",null,"input")
        advanceUntilIdle()
        assertEquals(1,calls)
        assertEquals(1,telemetry.events.size)
        assertNull(vm.location.value)
        assertEquals(P18SearchState.Ready(response),vm.state.value)
        vm.load("synthetic",null,"input",force=true)
        advanceUntilIdle()
        assertEquals(2,calls)
        assertEquals(1,telemetry.events.size)
    }

    @Test fun distanceTiesUseCompleteSpecOrderAndNoLocationPreservesResponseOrder() {
        fun row(bar:String,product:String,name:String) = SearchResultDto(
            bar,"Same bar","Synthetic",37.478,126.951,100,product,name,name,
            menuUpdatedAt="2026-11-01T00:00:00Z")
        val rows = listOf(row("b","p2","B"),row("b","p2","A"),row("a","p2","A"),row("a","p1","A"))
        assertEquals(listOf("a:p1:A","a:p2:A","b:p2:A","b:p2:B"),
            p18Sorted(rows,P18Sort.DISTANCE,true).map { "${it.barId}:${it.productId}:${it.productDisplayName}" })
        assertEquals(rows,p18Sorted(rows,P18Sort.DISTANCE,false))
    }
}
