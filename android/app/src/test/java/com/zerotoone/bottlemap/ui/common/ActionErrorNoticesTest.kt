package com.zerotoone.bottlemap.ui.common

import com.zerotoone.bottlemap.network.BottleMapApiException
import java.io.IOException
import java.net.SocketTimeoutException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class ActionErrorNoticesTest {
    @Test fun eachFailedAttemptNotifiesWithoutLatchingOrReturningInlineError() = runTest {
        var notices = 0
        backgroundScope.launch(start = CoroutineStart.UNDISPATCHED) {
            ActionErrorNotices.networkErrors.collect { notices++ }
        }
        val error = BottleMapApiException(code = "NETWORK_ERROR", message = "raw network trace")
        assertNull(error.actionErrorMessage())
        runCurrent()
        assertEquals(1, notices)
        assertNull(menuWriteActionErrorText(error))
        runCurrent()
        assertEquals(2, notices)
        assertNull(SocketTimeoutException("raw timeout").actionErrorMessage())
        runCurrent()
        assertEquals(3, notices)
    }

    @Test fun diskAndServerFailuresRemainContextualWithoutNetworkNotice() = runTest {
        var notices = 0
        backgroundScope.launch(start = CoroutineStart.UNDISPATCHED) {
            ActionErrorNotices.networkErrors.collect { notices++ }
        }
        assertEquals("기기에 저장하지 못했어요.", IOException("disk full")
            .actionErrorMessage("기기에 저장하지 못했어요."))
        assertEquals("가격을 확인해 주세요.", UserInputException("가격을 확인해 주세요.").actionErrorMessage())
        assertEquals("서버에 일시적인 문제가 있어요. 잠시 후 다시 시도해 주세요.",
            BottleMapApiException(httpStatus = 503, code = "UNAVAILABLE", message = "raw")
                .actionErrorMessage())
        runCurrent()
        assertEquals(0, notices)
    }

    @Test fun cancellationDoesNotBecomeAUserError() {
        val cancelled = CancellationException("cancelled request")
        try { cancelled.actionErrorMessage(); fail("Cancellation swallowed") }
        catch (caught: CancellationException) { assertSame(cancelled, caught) }
    }

    @Test fun existingLoadErrorMappingDoesNotEmitActionToast() = runTest {
        var notices = 0
        backgroundScope.launch(start = CoroutineStart.UNDISPATCHED) {
            ActionErrorNotices.networkErrors.collect { notices++ }
        }
        val error = BottleMapApiException(code = "NETWORK_ERROR", message = "raw")
        assertEquals(ActionErrorNotices.NETWORK_MESSAGE, error.userMessage())
        runCurrent()
        assertEquals(0, notices)
    }
}
