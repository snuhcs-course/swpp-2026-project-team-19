package com.zerotoone.bottlemap.ui.common

import com.zerotoone.bottlemap.network.BottleMapApiException
import kotlinx.coroutines.CancellationException
import java.io.IOException
import org.junit.Assert.*
import org.junit.Test

class UserErrorMessageTest {
    @Test fun networkNeverEchoesBackendTextOrSecrets() {
        val error = BottleMapApiException(code = "NETWORK_ERROR", message = "Cannot reach backend token=secret")
        assertEquals("인터넷 연결을 확인하고 다시 시도해 주세요.", error.userMessage())
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
    @Test fun missingOwnerTokenWithoutHttpResponseRequiresSignInAgain() {
        val error = BottleMapApiException(code = "UNAUTHENTICATED", message = "raw token details")
        assertNull(error.httpStatus)
        val expected = "로그인이 만료됐어요. 다시 로그인해 주세요."
        assertEquals(expected, error.userMessage("저장에 실패했어요."))
        assertEquals(expected, error.actionErrorMessage("저장에 실패했어요."))
        assertEquals(expected, com.zerotoone.bottlemap.network.menuWriteErrorText(error))
    }
    @Test fun localAddressLocationFailurePreservesItsActionableInstruction() {
        val old = com.zerotoone.bottlemap.data.owner.MockBar("bar", "매장", "이전 주소", latitude = 37.0, longitude = 127.0)
        try {
            com.zerotoone.bottlemap.data.owner.requireMovedBarCoordinates(old, old.copy(address = "새 주소"))
            fail("Address edit without coordinates accepted")
        } catch (error: IllegalArgumentException) {
            assertEquals("주소 변경에는 새로운 지도 위치 확인이 필요해요. 현재 주소는 저장되지 않았어요.",
                error.actionErrorMessage("일반 저장 실패"))
        }
    }
    @Test fun nonReviewConflictsExplainSpecificRecoveryInsteadOfBlindRetry() {
        val cases = mapOf(
            "OWNER_APPLICATION_EXISTS" to "신청 내역",
            "BAR_OWNER_EXISTS" to "다른 매장",
            "ACTIVE_IMPORT_EXISTS" to "기존 작업",
        )
        for ((code, action) in cases) {
            val message = BottleMapApiException(code = code, httpStatus = 409, message = "raw").userMessage()
            assertTrue(message.contains(action))
            assertFalse(message.contains("최신 내용을 불러온 뒤 다시 시도"))
        }
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
    @Test fun onlyTypedLocalValidationPreservesAppOwnedInstructions() {
        val copy = "용량을 입력하거나 Bottle 판매를 선택해 주세요."
        assertEquals(copy, UserInputException(copy).userMessage())
        assertEquals("다시 시도해 주세요.", IllegalArgumentException(copy).userMessage("다시 시도해 주세요."))
    }
    @Test fun sizeAndLimitErrorsHaveActionsWithoutEchoingValues() {
        assertTrue(BottleMapApiException(code="LIMIT", httpStatus=429,message="raw").userMessage().contains("횟수"))
        assertTrue(BottleMapApiException(code="SIZE", httpStatus=413,message="raw").userMessage().contains("줄여"))
    }
}
