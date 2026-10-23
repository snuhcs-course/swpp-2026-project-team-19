package com.zerotoone.bottlemap.data

import com.squareup.moshi.JsonDataException
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.zerotoone.bottlemap.network.NearbyBarsResponseDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class NearbyBarsDtoContractTest {
    private val adapter = Moshi.Builder()
        .addLast(KotlinJsonAdapterFactory())
        .build()
        .adapter(NearbyBarsResponseDto::class.java)

    @Test
    fun decodesExactA9FieldsAndNullableMenuTime() {
        val response = requireNotNull(adapter.fromJson(
            """
            {"items":[
              {"barId":"22222222-2222-4222-8222-222222222222",
               "name":"관악 위스키 바","address":"서울 관악구 관악로 1",
               "latitude":37.478321,"longitude":126.951234,
               "distanceMeters":41,"menuUpdatedAt":"2026-10-02T11:00:00Z"},
              {"barId":"33333333-3333-4333-8333-333333333333",
               "name":"샤로수길 몰트","address":"서울 관악구 관악로14길 10",
               "latitude":37.479874,"longitude":126.954512,
               "distanceMeters":373,"menuUpdatedAt":null}
            ]}
            """.trimIndent(),
        ))
        val bars = response.toNearbyBars()
        assertEquals(2, bars.size)
        assertEquals("관악 위스키 바", bars[0].name)
        assertEquals(41.0, bars[0].distanceMeters, 0.0)
        assertEquals("2026-10-02T11:00:00Z", bars[0].menuUpdatedAt)
        assertEquals(37.479874, bars[1].location.latitude, 1e-7)
        assertEquals(126.954512, bars[1].location.longitude, 1e-7)
        assertNull(bars[1].menuUpdatedAt)
    }

    @Test
    fun keepsServerResultAndOrderAtRounded500mEvenIfRawDistanceIsBeyondRadius() {
        val outsideAsDouble = Math.toDegrees(500.4 / 6_371_000.0)
        val response = NearbyBarsResponseDto(listOf(
            dto("A", latitude = outsideAsDouble, longitude = 0.0, distance = 500),
            dto("B", latitude = 0.0, longitude = 0.01, distance = 50),
        ))
        val bars = response.toNearbyBars()
        assertTrue(distanceMeters(NearbyCoordinate(0.0, 0.0), bars[0].location) > 500)
        assertEquals(listOf("A", "B"), bars.map { it.barId })
        assertEquals(500.0, bars[0].distanceMeters, 0.0)
    }

    @Test
    fun deduplicatesIdsButDoesNotSortOrReFilterServerItems() {
        val data = NearbyBarsResponseDto(listOf(
            dto("near", distance = 2),
            dto("near", distance = 2),
            dto("far", distance = 500),
        ))
        val bars = data.toNearbyBars()
        assertEquals(listOf("near", "far"), bars.map { it.barId })
    }

    @Test
    fun noItemsMeansRealEmpty() {
        val response = requireNotNull(adapter.fromJson("""{"items":[]}"""))
        assertTrue(response.toNearbyBars().isEmpty())
    }

    @Test
    fun missingRequiredDistanceIsNotSilentlyInvented() {
        val invalid = """{"items":[{"barId":"A","name":"A","address":"A",
            "latitude":37.478,"longitude":126.951,"menuUpdatedAt":null}]}"""
        assertThrows(JsonDataException::class.java) { adapter.fromJson(invalid) }
    }

    @Test
    fun malformedDataIsAnErrorNotAnIncompleteNearbyList() {
        assertThrows(IllegalArgumentException::class.java) {
            NearbyBarsResponseDto(listOf(dto("bad", latitude = 126.951))).toNearbyBars()
        }
        assertThrows(IllegalArgumentException::class.java) {
            NearbyBarsResponseDto(listOf(dto("bad", distance = 3001))).toNearbyBars()
        }
        assertThrows(IllegalArgumentException::class.java) {
            NearbyBarsResponseDto(listOf(dto(" "))).toNearbyBars()
        }
    }

    private fun dto(
        id: String,
        latitude: Double = 37.478,
        longitude: Double = 126.951,
        distance: Int = 25,
    ) = com.zerotoone.bottlemap.network.NearbyBarItemDto(
        barId = id, name = "test", address = "test",
        latitude = latitude, longitude = longitude, distanceMeters = distance,
        menuUpdatedAt = null,
    )
}
