package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.network.PopularProductDto
import org.junit.Assert.*
import org.junit.Test

class CustomerP18PopularStateTest {
    @Test fun loadingAndEmptyHaveExplicitCopyWithoutChangingSuccessfulCards() {
        assertEquals("인기 위스키를 불러오고 있어요.",
            p18PopularPlaceholder(P18PopularState.Loading))
        assertEquals("아직 표시할 인기 위스키가 없어요.",
            p18PopularPlaceholder(P18PopularState.Ready(emptyList())))
        assertNull(p18PopularPlaceholder(P18PopularState.Ready(listOf(
            PopularProductDto("product","Glenfiddich 12","Glenfiddich", barCount=2)))))
        assertNull(p18PopularPlaceholder(P18PopularState.Error))
    }
}
