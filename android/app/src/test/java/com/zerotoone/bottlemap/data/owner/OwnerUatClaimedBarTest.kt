package com.zerotoone.bottlemap.data.owner

import com.zerotoone.bottlemap.network.BarNameItemDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** UAT 4.9: a claimed bar must stay visible but cannot be chosen as ours. */
class OwnerUatClaimedBarTest {
    @Test fun alreadyOwnedBarsNeverAppearAsClaimable() {
        val publicCandidates = listOf(
            BarNameItemDto("claimed", "서로상", "관악구", 37.4, 126.9, true),
            BarNameItemDto("unclaimed", "위스키복춘", "관악구", 37.5, 126.9, false),
        )
        val (claimable, managed) =
            partitionOwnerApplicationBarCandidates(publicCandidates)
        assertEquals(listOf("unclaimed"), claimable.map { it.barId })
        assertEquals(listOf("claimed"), managed.map { it.barId })
    }

    @Test fun emptyResultsClearBothCandidateLists() {
        val (claimable, managed) = partitionOwnerApplicationBarCandidates(emptyList())
        assertTrue(claimable.isEmpty())
        assertTrue(managed.isEmpty())
    }
}
