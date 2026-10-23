package com.zerotoone.bottlemap.ui.customer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Test

class BarMapTargetTest {
    private fun bar(
        id: String = "bar-a",
        latitude: Double? = 37.478321,
        longitude: Double? = 126.951234,
    ) = BarDetailUiModel(
        barId = id,
        name = "Backend bar A",
        address = "서버 주소",
        phone = null,
        latitude = latitude,
        longitude = longitude,
        publishedAtText = null,
        items = emptyList(),
    )

    @Test
    fun retainsBackendBarIdentityAndLatitudeLongitudeOrder() {
        val location = validatedBarLocation(bar())
        assertNotNull(location)
        assertEquals("bar-a", location!!.barId)
        assertEquals("Backend bar A", location.name)
        assertEquals("서버 주소", location.address)
        assertEquals(37.478321, location.latitude, 0.0000001)
        assertEquals(126.951234, location.longitude, 0.0000001)
        // A swapped Korean longitude is outside the valid latitude range.
        assertNull(validatedBarLocation(bar(latitude = 126.951234, longitude = 37.478321)))
    }

    @Test
    fun changingBarChangesSelectedMapTarget() {
        val a = validatedBarLocation(bar())!!
        val b = validatedBarLocation(
            bar(id = "bar-b", latitude = 37.42, longitude = 127.07),
        )!!
        assertEquals("bar-a", a.barId)
        assertEquals("bar-b", b.barId)
        assertEquals(37.42, b.latitude, 0.000001)
        assertEquals(127.07, b.longitude, 0.000001)
    }

    @Test
    fun addressCopyPreservesExactBackendBytesAndDisablesEmpty() {
        val address = " 서울특별시 관악구 관악로 1, 2층 "
        assertEquals(address, copyableBarAddress(address))
        assertNull(copyableBarAddress(null))
        assertNull(copyableBarAddress(""))
        assertNull(copyableBarAddress("  \t "))
    }

    @Test
    fun rejectsMissingOrInvalidCoordinatesWithoutDefaultLocation() {
        assertNull(validatedBarLocation(bar(latitude = null)))
        assertNull(validatedBarLocation(bar(longitude = null)))
        assertNull(validatedBarLocation(bar(latitude = null, longitude = null)))
        assertNull(validatedBarLocation(bar(latitude = Double.NaN)))
        assertNull(validatedBarLocation(bar(longitude = Double.POSITIVE_INFINITY)))
        assertNull(validatedBarLocation(bar(latitude = -91.0)))
        assertNull(validatedBarLocation(bar(latitude = 90.00001)))
        assertNull(validatedBarLocation(bar(longitude = -180.00001)))
        assertNull(validatedBarLocation(bar(longitude = 180.00001)))
        assertNull(validatedBarLocation(bar(latitude = 0.0, longitude = 0.0)))
        assertNull(validatedBarLocation(bar(id = " ")))
    }
}
