package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BarNameItemDto
import com.zerotoone.bottlemap.network.BarNamesResponseDto
import com.zerotoone.bottlemap.network.MapBarItemDto
import com.zerotoone.bottlemap.network.MapBarsResponseDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertThrows
import org.junit.Test

class BackendMapBarsRepositoryTest {
    @Test fun kakaoViewportPixelCornersStayInsideExclusiveRightAndBottom() {
        assertEquals(listOf(
            0 to 0, 1079 to 0, 0 to 1919, 1079 to 1919,
        ), viewportCornerPixels(0, 0, 1080, 1920))
        assertEquals(listOf(
            10 to 25, 209 to 25, 10 to 424, 209 to 424,
        ), viewportCornerPixels(10, 25, 210, 425))
        assertEquals(null, viewportCornerPixels(0, 0, 0, 100))
        assertEquals(null, viewportCornerPixels(0, 0, 200, 1))
        assertEquals(null, viewportCornerPixels(40, 20, 39, 60))
    }

    @Test fun transientProjectionWithoutAllCornersOrCurrentCameraIsRejected() {
        val corners = listOf(
            NearbyCoordinate(37.48, 126.94),
            NearbyCoordinate(37.48, 126.96),
            NearbyCoordinate(37.47, 126.94),
            NearbyCoordinate(37.47, 126.96),
        )
        assertEquals(MapBounds(37.47, 126.94, 37.48, 126.96),
            mapBoundsFromCorners(corners, NearbyCoordinate(37.475, 126.95)))
        assertEquals(null, mapBoundsFromCorners(corners.take(3), NearbyCoordinate(37.475, 126.95)))
        assertEquals(null, mapBoundsFromCorners(corners, NearbyCoordinate(37.9, 127.5)))
        assertEquals(null, mapBoundsFromCorners(
            List(4) { NearbyCoordinate(37.475, 126.95) }, NearbyCoordinate(37.475, 126.95)))
        assertEquals(null, mapBoundsFromCorners(
            corners.take(3) + NearbyCoordinate(Double.NaN, 126.96)))
    }

    @Test fun serverMapFieldsAreMappedWithoutInventingDistanceOrSorting() {
        val response = MapBarsResponseDto(
            items = listOf(
                MapBarItemDto("second", "서로상", "서울", 37.51, 126.98, null),
                MapBarItemDto("first", "위스키복춘", "서울", 37.47, 126.95, "2026-10-21T01:00:00Z"),
            )
        )
        val bars = response.toMapBars()
        assertEquals(listOf("second", "first"), bars.map { it.barId })
        assertEquals(null, bars[0].menuUpdatedAt)
        assertEquals("2026-10-21T01:00:00Z", bars[1].menuUpdatedAt)
        assertTrue(bars[0] is BarPin)
        assertFalse((bars[0] as Any) is NearbyBar)
        val moshi = ApiClient.moshi.adapter(MapBarsResponseDto::class.java)
        val parsed = moshi.fromJson("""{"items":[{"barId":"test","name":"Test","address":"Seoul","latitude":37.5,"longitude":127.0,"menuUpdatedAt":null}]}""")
        assertEquals("test", parsed!!.items.single().barId)
    }

    @Test fun barNamesDtosPreserveBackendIdsAndCoordinates() {
        val items = BarNamesResponseDto(
            items = listOf(
                BarNameItemDto("bar1", "서로상", "관악구", 37.48, 126.95, false),
                BarNameItemDto("bar2", "위스키복춘", "관악구", 37.49, 126.95, true),
            ), truncated = true)
        val mapped = items.toMapPlaces()
        assertEquals(listOf("bar1", "bar2"), mapped.map { it.barId })
        assertEquals(listOf("서로상", "위스키복춘"), mapped.map { it.name })
        assertEquals(37.49, mapped[1].coordinate.latitude, 0.0000001)
        assertTrue(items.truncated)
        val moshi = ApiClient.moshi.adapter(BarNamesResponseDto::class.java)
        val parsed = moshi.fromJson("""{"items":[{"barId":"b","name":"위스키복춘","address":"서울","latitude":37.48,"longitude":126.95,"hasOwner":false}],"truncated":false}""")
        assertEquals("b", parsed!!.items.single().barId)
    }

    @Test fun outOfOrderOrInvalidMapCoordinatesFailExplicitly() {
        assertThrows(IllegalArgumentException::class.java) {
            MapBounds(37.49, 127.0, 37.47, 127.1)
        }
        assertThrows(IllegalArgumentException::class.java) {
            MapBounds(37.47, 127.1, 37.49, 127.0)
        }
        assertThrows(IllegalArgumentException::class.java) {
            MapBounds(Double.NaN, 127.0, 37.49, 127.1)
        }
        assertThrows(IllegalArgumentException::class.java) {
            MapBarsResponseDto(listOf(
                MapBarItemDto("bad", "bad", "bad", 100.0, 126.9, null)
            )).toMapBars()
        }
    }

    @Test fun eachSideAtMostPointTwoDegreesIncludingFloatTolerance() {
        val allowed = MapBounds(37.29, 126.81, 37.49, 127.01)
        val oversized = MapBounds(37.29, 126.81, 37.491, 127.01)
        assertTrue(allowed.isSupportedByBackend())
        assertFalse(oversized.isSupportedByBackend())
        assertTrue(MapBounds(37.5, 126.9, 37.5, 126.9).isSupportedByBackend())
        assertEquals(null, mapBoundsFromCorners(emptyList()))
    }
}
