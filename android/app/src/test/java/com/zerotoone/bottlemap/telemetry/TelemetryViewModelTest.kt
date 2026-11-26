package com.zerotoone.bottlemap.telemetry

import com.zerotoone.bottlemap.data.CustomerDiscoverySource
import com.zerotoone.bottlemap.data.MapPlaceSearchSource
import com.zerotoone.bottlemap.data.MapPlace
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.network.*
import com.zerotoone.bottlemap.ui.customer.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import org.junit.After
import org.junit.Before
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class TelemetryViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setup() { Dispatchers.setMain(dispatcher) }
    @After fun cleanup() { Dispatchers.resetMain() }
    @Test fun brandSelectionLocationRefreshAndRecompositionDoNotInflateSearchCount() = runTest(dispatcher) {
        val fake = FakeTelemetry()
        val source = object: CustomerDiscoverySource {
            override suspend fun popularProducts(limit:Int):PopularProductsResponseDto = error("unused")
            override suspend fun searchProduct(query:String?,productId:String?,source:String) =
                SearchBarsResponseDto(query, if(productId == null) "brand" else "product",
                    matchedProducts=listOf(MatchedProductDto("product","name","brand",resultCount=1)), truncated=false)
        }
        val vm = P18SearchViewModel(source, fake)
        vm.load("private query",null,"input"); advanceUntilIdle()
        vm.load("private query",null,"input"); advanceUntilIdle()
        vm.load(null,"product","input"); advanceUntilIdle()
        vm.setLocation(NearbyCoordinate(37.5,127.0))
        vm.load(null,"product","input",force=true); advanceUntilIdle()
        assertEquals(listOf(TelemetryEvent.SearchCompleted(SearchKind.BRAND,true)),fake.events)
    }
    @Test fun emptySearchHasFalseResultsButErrorAndCancelledResponsesAreNotCompleted() = runTest(dispatcher) {
        val fake = FakeTelemetry()
        val pending = CompletableDeferred<SearchBarsResponseDto>()
        val source = object: CustomerDiscoverySource {
            override suspend fun popularProducts(limit:Int):PopularProductsResponseDto = error("unused")
            override suspend fun searchProduct(query:String?,productId:String?,source:String):SearchBarsResponseDto {
                if(query == "old") return withContext(NonCancellable) { pending.await() }
                if(query == "failure") throw BottleMapApiException(code="NETWORK_ERROR",message="private")
                return SearchBarsResponseDto(query,"none",truncated=false)
            }
        }
        val vm = P18SearchViewModel(source,fake)
        vm.load("old",null,"input"); runCurrent()
        vm.load("new",null,"input"); runCurrent()
        pending.complete(SearchBarsResponseDto("old","none",truncated=false)); advanceUntilIdle()
        vm.load("failure",null,"input"); advanceUntilIdle()
        assertEquals(listOf(TelemetryEvent.SearchCompleted(SearchKind.PRODUCT,false)),fake.events)
    }
    @Test fun barNameSearchDoesNotCountGenericGeocoderMatchesAsBars() = runTest(dispatcher) {
        val fake=FakeTelemetry()
        val source=object:MapPlaceSearchSource {
            override suspend fun search(query:String)=listOf(MapPlace("private","private",NearbyCoordinate(37.5,127.0),
                if(query=="registered") "private-id" else null))
        }
        val vm=MapPlaceSearchViewModel(source,fake)
        vm.search("generic");advanceUntilIdle()
        vm.search("registered");advanceUntilIdle()
        assertEquals(listOf(TelemetryEvent.SearchCompleted(SearchKind.BAR_NAME,false),
            TelemetryEvent.SearchCompleted(SearchKind.BAR_NAME,true)),fake.events)
    }
    @Test fun locationlessCarouselUsesMapAndLocatedCarouselUsesNearby() {
        val journey = DiscoveryJourney()
        val vm = P18ExploreViewModel(journey = journey)
        vm.openingBar()
        assertEquals(DetailSource.MAP, journey.detailOpened().source)
        vm.setLocation(NearbyCoordinate(37.5, 127.0))
        vm.openingBar()
        assertEquals(DetailSource.NEARBY, journey.detailOpened().source)
        vm.openingBar(nearby = false)
        assertEquals(DetailSource.MAP, journey.detailOpened().source)
        vm.clearLocation()
        vm.openingBar()
        assertEquals(DetailSource.MAP, journey.detailOpened().source)
    }
    @Test fun nearbyPermissionChangesEmitOncePerActualState() {
        val fake=FakeTelemetry()
        val vm=P18ExploreViewModel(telemetry=fake)
        vm.opened(false);vm.opened(false);vm.opened(true);vm.opened(true);vm.opened(false)
        assertEquals(listOf(TelemetryEvent.NearbyOpened(Permission.DENIED),
            TelemetryEvent.NearbyOpened(Permission.GRANTED), TelemetryEvent.NearbyOpened(Permission.DENIED)),fake.events)
    }
}
