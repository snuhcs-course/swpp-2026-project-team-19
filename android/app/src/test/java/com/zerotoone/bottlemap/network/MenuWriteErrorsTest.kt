package com.zerotoone.bottlemap.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MenuWriteErrorsTest {
    @Test fun oldServerSchemaExplainsVersionMismatchInsteadOfGenericValidation() {
        val error = BottleMapApiException(
            httpStatus = 422, code = "VALIDATION_FAILED",
            message = "입력값을 확인해 주세요.",
            fieldErrors = listOf(FieldErrorDto("localItem", "EXTRA_FORBIDDEN", "Extra inputs are not permitted")),
        )
        assertTrue(menuWriteErrorText(error).contains("API 버전"))
        assertTrue(menuWriteErrorText(error).contains("localItem"))
    }

    @Test fun kindRejectedByOldDeployedSchemaExplainsDeploymentWithoutRetry() {
        val oldServer = BottleMapApiException(
            httpStatus = 422, code = "VALIDATION_FAILED",
            message = "입력값을 확인해 주세요.",
            fieldErrors = listOf(FieldErrorDto("kind", "EXTRA_FORBIDDEN",
                "Extra inputs are not permitted")),
        )
        val text = menuWriteErrorText(oldServer)
        assertTrue(text.contains("서버"))
        assertTrue(text.contains("kind"))
        assertTrue(text.contains("저장되지 않았"))
        val nested = oldServer.copyForField("body.kind")
        assertTrue(menuWriteErrorText(nested).contains("서버"))
    }

    private fun BottleMapApiException.copyForField(path: String) =
        BottleMapApiException(
            httpStatus = httpStatus, code = code, message = message,
            fieldErrors = listOf(FieldErrorDto(path,"EXTRA_FORBIDDEN",
                "Extra inputs are not permitted")),
        )

    @Test fun photoReviewUnionMismatchExplainsVersionMismatch() {
        val error = BottleMapApiException(
            httpStatus = 422, code = "VALIDATION_FAILED",
            message = "입력값을 확인해 주세요.",
            fieldErrors = listOf(FieldErrorDto("itemDecisions[0]", "UNION_TAG_INVALID", "Invalid action")),
        )
        assertTrue(menuWriteErrorText(error).contains("서버"))
    }

    @Test fun optionPriceFieldErrorIsShownToOwner() {
        val error = BottleMapApiException(
            httpStatus = 422, code = "VALIDATION_FAILED", message = "입력값을 확인해 주세요.",
            fieldErrors = listOf(FieldErrorDto("options[1].priceKrw", "GREATER_THAN_EQUAL", "Input should be greater than or equal to 1")),
        )
        assertTrue(menuWriteErrorText(error).contains("2번 옵션 가격"))
        assertTrue(menuWriteErrorText(error).contains("greater than"))
    }

    @Test fun menuVersionAndOtherApiErrorsStayActionable() {
        val invalid = BottleMapApiException(
            code = "VALIDATION_FAILED", message = "입력값을 확인해 주세요.",
            fieldErrors = listOf(FieldErrorDto("menuVersion", "INT_TYPE", "Input should be a valid integer"))
        )
        assertTrue(menuWriteErrorText(invalid).contains("메뉴 버전"))
        val outdated = BottleMapApiException(httpStatus = 409, code = "MENU_OUTDATED", message = "최신 메뉴를 다시 불러와 주세요.")
        assertEquals("최신 메뉴를 다시 불러와 주세요.", menuWriteErrorText(outdated))
    }
}
