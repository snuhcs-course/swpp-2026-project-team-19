package com.zerotoone.bottlemap.network

import org.junit.Assert.*
import org.junit.Test

class MenuWriteErrorsTest {
    private fun invalid(path: String, code: String, message: String = "Raw secret: Extra inputs are not permitted") =
        BottleMapApiException(httpStatus=422, code="VALIDATION_FAILED", message="server secret",
            fieldErrors=listOf(FieldErrorDto(path,code,message)))

    @Test fun oldServerSchemaExplainsRecoveryWithoutLeakingField() {
        val text=menuWriteErrorText(invalid("localItem", "EXTRA_FORBIDDEN"))
        assertTrue(text.contains("서비스와 앱")); assertFalse(text.contains("업데이트")); assertFalse(text.contains("localItem"))
        assertFalse(text.contains("secret")); assertFalse(text.contains("API"))
    }
    @Test fun kindAndNestedSchemaFailuresDoNotExposeTechnicalNames() {
        for(path in listOf("kind", "body.kind")) for(code in listOf("EXTRA_FORBIDDEN", "UNION_TAG_INVALID", "LITERAL_ERROR")) {
            val text=menuWriteErrorText(invalid(path,code))
            assertTrue(text.contains("서비스와 앱")); assertFalse(text.contains("업데이트"));assertFalse(text.contains(path))
        }
    }
    @Test fun photoReviewUnionMismatchUsesSameSafeRecovery() {
        val text=menuWriteErrorText(invalid("itemDecisions[0]", "UNION_TAG_INVALID"))
        assertTrue(text.contains("서비스와 앱")); assertFalse(text.contains("업데이트"));assertFalse(text.contains("itemDecisions"))
    }
    @Test fun optionPriceErrorIdentifiesRowAndActionInKorean() {
        assertEquals("2번 옵션 가격: 입력할 수 있는 숫자 범위를 확인해 주세요.",
            menuWriteErrorText(invalid("options[1].priceKrw", "GREATER_THAN_EQUAL")))
    }
    @Test fun menuVersionIsRefreshableRatherThanEditable() {
        assertTrue(menuWriteErrorText(invalid("menuVersion","INT_TYPE")).contains("최신"))
        assertTrue(menuWriteErrorText(BottleMapApiException(httpStatus=409,code="MENU_OUTDATED",message="raw")).contains("최신"))
    }
    @Test fun arbitraryFieldPathsAndKoreanServerMessagesNeverLeak() {
        val text=menuWriteErrorText(invalid("private.customer.email", "UNKNOWN", "개인정보 원문"))
        assertEquals("입력 내용: 입력한 값을 확인해 주세요.",text)
    }
}
