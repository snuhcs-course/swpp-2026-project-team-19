package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.data.MapBar
import com.zerotoone.bottlemap.data.NearbyCoordinate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CustomerP18PinVisibilityTest {
    private val saved=MapBar(
        barId="bar1",
        name="관악 위스키 바",
        address="서울특별시 관악구 관악로 1",
        location=NearbyCoordinate(37.478321,126.951234),
    )

    @Test fun zoomedOutStateClearsPreviouslyVisibleNativeMarkers() {
        assertTrue(p18VisibleBars(P18ExploreState.TooWide,listOf(saved)).isEmpty())
    }

    @Test fun aPendingViewportRequestCanPreservePinsWithoutContradictingTooWide() {
        assertEquals(listOf(saved),
            p18VisibleBars(P18ExploreState.Loading,listOf(saved)))
        assertEquals(listOf(saved),
            p18VisibleBars(P18ExploreState.Ready(listOf(saved)),emptyList()))
    }
}
