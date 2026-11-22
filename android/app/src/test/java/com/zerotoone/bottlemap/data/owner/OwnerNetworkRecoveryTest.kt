package com.zerotoone.bottlemap.data.owner

import com.zerotoone.bottlemap.network.BottleMapApiException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

class OwnerNetworkRecoveryTest {
    @Test fun unchangedSavePropagatesFailedRefreshWithoutReplacingTheEditor() = runTest {
        val network = BottleMapApiException(code = "NETWORK_ERROR", message = "raw")
        var committedFailureCalls = 0
        try {
            refreshOwnerAfterWrite(false, { throw network }, { committedFailureCalls++ })
            fail("An unchanged save must not report success after its only request failed")
        } catch (caught: BottleMapApiException) { assertSame(network, caught) }
        assertEquals(0, committedFailureCalls)
    }

    @Test fun confirmedWriteDoesNotBecomeAFailedWriteWhenRefreshLosesNetwork() = runTest {
        val network = BottleMapApiException(code = "NETWORK_ERROR", message = "raw")
        var noticed: Throwable? = null
        refreshOwnerAfterWrite(true, { throw network }, { noticed = it })
        assertSame(network, noticed)
    }

    @Test fun refreshCancellationIsNeverShownAsANetworkFailure() = runTest {
        val cancelled = CancellationException("cancelled")
        var notices = 0
        try {
            refreshOwnerAfterWrite(true, { throw cancelled }, { notices++ })
            fail("Cancellation swallowed")
        } catch (caught: CancellationException) { assertSame(cancelled, caught) }
        assertEquals(0, notices)
    }

    @Test fun sameVerifiedOwnerRetainsBarAndRegistrationDraftOnFailedReload() {
        val cached = MockOwnerSnapshot(
            bars = listOf(MockBar("bar-1", "기존 매장", "주소")),
            registrationDraft = MockRegistrationDraft(proposedBarName = "입력 중인 매장"),
        )
        val retained = ownerStateAfterNetworkLoadFailure(cached, true, "owner-A", "owner-A")
        assertEquals(cached, (retained as MockOwnerLoadState.Ready).snapshot)
    }

    @Test fun unknownOrDifferentAccountCannotSeeCachedOwnerOrRegistrationEntry() {
        val cached = MockOwnerSnapshot(bars = listOf(MockBar("private", "이전 매장", "주소")))
        assertEquals(MockOwnerLoadState.NetworkUnavailable,
            ownerStateAfterNetworkLoadFailure(cached, true, "owner-A", "owner-B"))
        assertEquals(MockOwnerLoadState.NetworkUnavailable,
            ownerStateAfterNetworkLoadFailure(cached, true, "owner-A", null))
        assertEquals(MockOwnerLoadState.NetworkUnavailable,
            ownerStateAfterNetworkLoadFailure(cached, false, "owner-A", "owner-A"))
    }
}
