package com.zerotoone.bottlemap.ui.customer

import org.junit.Assert.assertEquals
import org.junit.Test

class NearbyCarouselPlaceholderTest {
    @Test fun noLocationPermissionShowsPermissionPromptNotFalseEmpty() {
        assertEquals("위치 권한을 설정해 주세요.",
            nearbyCarouselEmptyMessage(false, NearbyUiState.Empty))
        assertEquals("위치 권한을 설정해 주세요.",
            nearbyCarouselEmptyMessage(false, NearbyUiState.LoadingLocation))
        assertEquals("위치 권한을 설정해 주세요.",
            nearbyCarouselEmptyMessage(false, NearbyUiState.PermissionRequired))
    }

    @Test fun allowedButUnloadedOrEmptyShowsAppropriateText() {
        assertEquals("근처 매장을 확인하는 중입니다.",
            nearbyCarouselEmptyMessage(true, NearbyUiState.Initial))
        assertEquals("근처에 매장이 없습니다.",
            nearbyCarouselEmptyMessage(true, NearbyUiState.Empty))
        assertEquals("근처 매장을 불러오지 못했습니다.",
            nearbyCarouselEmptyMessage(true, NearbyUiState.Error("network")))
    }
}
