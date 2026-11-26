package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.MapBarItemDto
import com.zerotoone.bottlemap.network.MapBarsResponseDto
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

class AllBarsRepositoryTest {
    private fun bar(id: String, lat: Double = 37.478321, lng: Double = 126.951234) =
        MapBarItemDto(id, "Bar $id", "Seoul", lat, lng, null, "https://example.invalid/$id")

    @Test fun nearbyAndMapReuseOneCatalogAndPreserveMetadata() = runTest {
        var calls = 0
        val all = AllBarsRepository(fetch = {
            calls++
            MapBarsResponseDto(listOf(bar("b"), bar("a"), bar("a")))
        })
        val nearby = BackendNearbyBarsRepository(all)
        val map = BackendMapBarsRepository(all)
        assertEquals(listOf("a", "b"), nearby.listNearbyBars(NearbyCoordinate(37.478321,126.951234)).map { it.barId })
        val pins = map.listMapBars(MapBounds(37.47,126.95,37.48,126.96))
        assertEquals(listOf("a", "b"), pins.map { it.barId })
        assertNull(pins.first().menuUpdatedAt)
        assertEquals("https://example.invalid/a", pins.first().coverThumbnailUrl)
        assertEquals(1, calls)
    }

    @Test fun simultaneousScreensCoalesceTheRequest() = runTest {
        var calls = 0
        val entered = CompletableDeferred<Unit>()
        val reply = CompletableDeferred<MapBarsResponseDto>()
        val all = AllBarsRepository(fetch = { calls++; entered.complete(Unit); reply.await() })
        val first = async { all.listBars() }
        entered.await()
        val second = async { all.listBars() }
        reply.complete(MapBarsResponseDto(listOf(bar("a"))))
        assertEquals(first.await(), second.await())
        assertEquals(1, calls)
    }

    @Test fun emptyCatalogIsCachedAndRefetchedAtTtlBoundary() = runTest {
        var now = 0L
        var calls = 0
        val all = AllBarsRepository(fetch = {
            calls++
            MapBarsResponseDto(if (calls == 1) emptyList() else listOf(bar("new")))
        }, clock = { now })
        assertTrue(all.listBars().isEmpty())
        now = AllBarsRepository.CACHE_TTL_MS - 1
        assertTrue(all.listBars().isEmpty())
        assertEquals(1, calls)
        now++
        assertEquals("new", all.listBars().single().barId)
        assertEquals(2, calls)
    }

    @Test fun failedOrMalformedResponseIsNotCachedAndCanBeRetried() = runTest {
        var calls = 0
        val all = AllBarsRepository(fetch = {
            calls++
            when(calls) {
                1 -> error("offline")
                2 -> MapBarsResponseDto(listOf(bar("valid"), bar("invalid",91.0)))
                else -> MapBarsResponseDto(listOf(bar("valid")))
            }
        })
        assertTrue(runCatching { all.listBars() }.isFailure)
        assertTrue(runCatching { all.listBars() }.isFailure)
        assertEquals("valid", all.listBars().single().barId)
        assertEquals(3, calls)
    }

    @Test fun cancellationDoesNotPoisonTheSharedCache() = runTest {
        var calls = 0
        val entered = CompletableDeferred<Unit>()
        val all = AllBarsRepository(fetch = {
            if (++calls == 1) { entered.complete(Unit); CompletableDeferred<Unit>().await() }
            MapBarsResponseDto(listOf(bar("recovered")))
        })
        val first = launch { all.listBars() }
        entered.await()
        first.cancelAndJoin()
        assertEquals("recovered", all.listBars().single().barId)
        assertEquals(2, calls)
    }

    @Test fun expiredFailureDoesNotMasqueradeAsFreshOrEmptyData() = runTest {
        var now = 0L
        var calls = 0
        val all = AllBarsRepository(fetch = {
            if (++calls == 2) error("offline")
            MapBarsResponseDto(listOf(bar(if(calls == 1) "old" else "new")))
        }, clock = { now })
        assertEquals("old", all.listBars().single().barId)
        now = AllBarsRepository.CACHE_TTL_MS
        assertTrue(runCatching { all.listBars() }.isFailure)
        assertEquals("new", all.listBars().single().barId)
    }

    @Test fun roundedBoundaryIsIncludedAndTiesUseBarId() = runTest {
        val all = AllBarsRepository(fetch = { MapBarsResponseDto(listOf(
            bar("out",37.482503,126.951),
            bar("z",37.482498,126.951), bar("a",37.482498,126.951),
        )) })
        val nearby = BackendNearbyBarsRepository(all).listNearbyBars(NearbyCoordinate(37.478,126.951),500)
        assertEquals(listOf("a", "z"), nearby.map { it.barId })
        assertEquals(listOf(500.0,500.0), nearby.map { it.distanceMeters })
    }

    @Test fun mapFilterIncludesEveryEdgeAndCornerAndEmptyIsRealEmpty() = runTest {
        val all = AllBarsRepository(fetch = { MapBarsResponseDto(listOf(
            bar("sw",37.47,126.95), bar("se",37.47,126.96),
            bar("nw",37.48,126.95), bar("ne",37.48,126.96),
            bar("south",37.469999,126.955), bar("east",37.475,126.960001),
        )) })
        val map = BackendMapBarsRepository(all)
        assertEquals(listOf("ne","nw","se","sw"), map.listMapBars(MapBounds(37.47,126.95,37.48,126.96)).map { it.barId })
        assertTrue(map.listMapBars(MapBounds(35.0,129.0,35.1,129.1)).isEmpty())
    }

    @Test fun invalidOriginOrRadiusIsRejectedBeforeFetching() = runTest {
        var calls = 0
        val source = BackendNearbyBarsRepository(AllBarsRepository(fetch = { calls++; MapBarsResponseDto(emptyList()) }))
        assertTrue(runCatching { source.listNearbyBars(NearbyCoordinate(Double.NaN,127.0)) }.isFailure)
        for(radius in listOf(0,3001)) {
            assertTrue(runCatching { source.listNearbyBars(NearbyCoordinate(37.48,126.95),radius) }.isFailure)
        }
        assertEquals(0,calls)
    }

    @Test fun serverDistanceFixturesIncludeRoundedEdgesPoleAndAntimeridian() {
        // Independent expected values from backend/app/services/search.py distance_meters,
        // also covering backend/tests/test_nearby_bars_api.py boundary coordinates.
        val fixtures = listOf(
            Triple(NearbyCoordinate(37.478,126.951),NearbyCoordinate(37.478321,126.951234),41),
            Triple(NearbyCoordinate(37.478,126.951),NearbyCoordinate(37.482498,126.951),500),
            Triple(NearbyCoordinate(37.478,126.951),NearbyCoordinate(37.482503,126.951),501),
            Triple(NearbyCoordinate(0.0,179.9995),NearbyCoordinate(0.0,-179.9995),111),
            Triple(NearbyCoordinate(89.9995,0.0),NearbyCoordinate(89.9995,180.0),111),
            Triple(NearbyCoordinate(37.48,126.95),NearbyCoordinate(35.1796,129.0756),318862),
            Triple(NearbyCoordinate(0.0,0.0),NearbyCoordinate(0.0,0.0),0),
        )
        fixtures.forEach { (from,to,expected) -> assertEquals(expected,roundedDistanceMeters(from,to)) }
    }
}
