package com.zerotoone.bottlemap.data.owner

import com.zerotoone.bottlemap.network.BarMenuResponseDto
import com.zerotoone.bottlemap.network.BarMenuItemDto
import com.zerotoone.bottlemap.network.BarMenuOptionDto
import com.zerotoone.bottlemap.network.BottleMapApiException
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

class OwnerWriteAcknowledgementsTest {
    private val a = MockBar("a", "이전 이름", "주소")
    private val b = MockBar("b", "다른 매장", "주소")
    private fun menu(items: List<BarMenuItemDto>) = BarMenuResponseDto(
        barId = "a", name = "서버 매장", address = "주소", latitude = 37.0, longitude = 127.0,
        phone = null, menuBoardId = "board", publishedAt = null, items = items, menuVersion = 9,
    )
    private val network = BottleMapApiException(code = "NETWORK_ERROR", message = "raw")

    @Test fun acknowledgedBarValueSurvivesFailedAggregateGetWithDraftAndOtherBarIntact() = runTest {
        val draft = MockRegistrationDraft(proposedBarName = "별도 등록 초안")
        var state = MockOwnerSnapshot(bars = listOf(a,b), registrationDraft = draft)
        val acknowledged = a.copy(name = "서버가 확정한 이름", phone = "02-123-4567")
        state = ownerSnapshotAfterBarCommit(state, acknowledged)
        var notices = 0
        refreshOwnerAfterWrite(true, { throw network }, { notices++ })
        assertEquals(acknowledged, state.bars.first())
        assertEquals(b, state.bars.last())
        assertEquals(draft, state.registrationDraft)
        assertEquals(1, notices)
    }

    @Test fun acknowledgedDeletionCannotRemainAvailableForRepeatDeletionAfterGetFails() = runTest {
        val rowA = MockBarMenuItem("deleted", "a", "product-a", listOf(MockMenuOption("option-a", priceKrw = 1000)))
        val rowB = MockBarMenuItem("keep", "b", "product-b", listOf(MockMenuOption("option-b", priceKrw = 2000)))
        var state = MockOwnerSnapshot(bars = listOf(a,b), menuItems = listOf(rowA,rowB))
        state = ownerSnapshotAfterMenuCommit(state, "a", menu(emptyList()))
        refreshOwnerAfterWrite(true, { throw network }, {})
        assertEquals(listOf(rowB), state.menuItems)
        assertFalse(state.menuItems.any { it.barMenuItemId == "deleted" })
    }

    @Test fun acknowledgedMenuUsesServerItemAndOptionIdsIncludingPriceAndStock() = runTest {
        val old = MockBarMenuItem("server-row", "a", "old", listOf(MockMenuOption("old-option", priceKrw = 1)))
        val response = menu(listOf(BarMenuItemDto(
            menuBoardEntryId = "entry", barMenuItemId = "server-row", productId = null,
            displayName = "서버 이름", sortOrder = 0, soldOut = true, kind = "other",
            options = listOf(BarMenuOptionDto("server-option", null, 45, 15000, 0)),
        )))
        val state = ownerSnapshotAfterMenuCommit(MockOwnerSnapshot(bars = listOf(a), menuItems = listOf(old)), "a", response)
        refreshOwnerAfterWrite(true, { throw network }, {})
        val row = state.menuItems.single()
        assertEquals("server-row", row.barMenuItemId)
        assertEquals("server-option", row.options.single().optionId)
        assertEquals(15000, row.options.single().priceKrw)
        assertTrue(row.soldOut)
        assertEquals("서버 이름", row.displayNameOverride)
        assertEquals("unlinked:server-row", row.productId)
        assertEquals("otherAlcohol", state.products.single().category)
    }
}
