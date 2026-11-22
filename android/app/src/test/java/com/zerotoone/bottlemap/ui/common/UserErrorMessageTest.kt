package com.zerotoone.bottlemap.ui.common

import com.zerotoone.bottlemap.network.BottleMapApiException
import kotlinx.coroutines.CancellationException
import java.io.IOException
import org.junit.Assert.*
import org.junit.Test

class UserErrorMessageTest {
    @Test fun networkNeverEchoesBackendTextOrSecrets() {
        val error = BottleMapApiException(code = "NETWORK_ERROR", message = "Cannot reach backend token=secret")
        assertEquals("인터넷 연결을 확인한 뒤 다시 시도해 주세요.", error.userMessage())
    }
    @Test fun koreanServerTextIsNotTrustedEither() {
        val error = BottleMapApiException(code = "UNKNOWN", message = "내부 개인정보 원문", httpStatus = 500)
        assertEquals("서버에 일시적인 문제가 있어요. 잠시 후 다시 시도해 주세요.", error.userMessage())
    }
    @Test fun authPermissionAndConflictHaveDifferentRecoveryActions() {
        val auth = BottleMapApiException(code = "UNAUTHORIZED", httpStatus = 401, message = "raw")
        val permission = BottleMapApiException(code = "FORBIDDEN", httpStatus = 403, message = "raw")
        val conflict = BottleMapApiException(code = "MENU_OUTDATED", httpStatus = 409, message = "raw")
        assertTrue(auth.userMessage().contains("로그인"))
        assertTrue(permission.userMessage().contains("권한"))
        assertTrue(conflict.userMessage().contains("최신"))
        assertEquals(409, conflict.httpStatus) // mapping must not mutate retry/classification data
    }
    @Test fun unknownFailuresUseTaskSpecificCopy() {
        assertEquals("사진을 다시 선택해 주세요.", IllegalStateException("java.lang.Failure").userMessage("사진을 다시 선택해 주세요."))
        assertEquals("사진을 저장하지 못했어요.", IOException("ENOSPC /private/path").userMessage("사진을 저장하지 못했어요."))
    }
    @Test fun unknownApiCodeCannotBeDisplayed() {
        assertEquals("다시 시도해 주세요.", BottleMapApiException(code="SECRET_INTERNAL_CODE", message="원문").userMessage("다시 시도해 주세요."))
    }
    @Test fun cancellationRemainsControlFlow() {
        val cancelled = CancellationException("The coroutine was cancelled")
        try { cancelled.userMessage(); fail("Cancellation swallowed") }
        catch (caught: CancellationException) { assertSame(cancelled, caught) }
    }
    @Test fun sizeAndLimitErrorsHaveActionsWithoutEchoingValues() {
        assertTrue(BottleMapApiException(code="LIMIT", httpStatus=429,message="raw").userMessage().contains("횟수"))
        assertTrue(BottleMapApiException(code="SIZE", httpStatus=413,message="raw").userMessage().contains("줄여"))
    }
}
