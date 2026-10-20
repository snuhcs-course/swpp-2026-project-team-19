package com.zerotoone.bottlemap.data

import org.junit.Assert.assertEquals
import org.junit.Test

class MapPlaceSearchSourceTest {
    @Test fun removesInvalidOrDuplicatedCoordinatesWithoutFilteringByDistance() {
        val valid = MapPlace("서울역", "서울", NearbyCoordinate(37.5547, 126.9707))
        val distant = MapPlace("부산역", "부산", NearbyCoordinate(35.115, 129.041))
        val invalid = MapPlace("invalid", "", NearbyCoordinate(99.0, 0.0))
        val origin = MapPlace("zero", "", NearbyCoordinate(0.0, 0.0))
        assertEquals(listOf(valid, distant),
            sanitizePlaces(listOf(valid, valid, invalid, distant, origin)))
    }


    @Test fun geocoderResultsOutsideKoreaAreFilteredButKoreanStationsRemain() {
        val korean = MapPlace("강남역", "서울",
            NearbyCoordinate(37.4979, 127.0276))
        val overseas = MapPlace("London", "UK",
            NearbyCoordinate(51.5074, -0.1278))
        val nearBorder = MapPlace("Tokyo", "Japan",
            NearbyCoordinate(35.6762, 139.6503))
        assertEquals(listOf(korean), sanitizePlaces(listOf(overseas, korean, nearBorder)))
    }

    @Test fun registeredNameAndAddressMatchesOnlyFetchedValidBars() {
        val b = NearbyBar("b1", "위스키복춘", "서울 관악구",
            NearbyCoordinate(37.478, 126.951), 12.0)
        val c = NearbyBar("b2", "서로상", "서울 서대문구",
            NearbyCoordinate(37.56, 126.94), 200.0)
        val bars = listOf(b, b, c)
        assertEquals(listOf("b1"),
            findRegisteredBarPlaces("복춘", bars).map { it.barId })
        assertEquals(listOf("b2"),
            findRegisteredBarPlaces("서대문구", bars).map { it.barId })
        assertEquals(emptyList<MapPlace>(), findRegisteredBarPlaces("강남역", bars))
    }

    @Test fun capsLookupResultsToFiveWithoutInventingMissingPlaces() {
        val items = (1..10).map {
            MapPlace("place$it", "", NearbyCoordinate(37.5 + it * 0.001, 126.9))
        }
        assertEquals(items.take(5), sanitizePlaces(items))
        assertEquals(emptyList<MapPlace>(), sanitizePlaces(emptyList()))
    }
}
