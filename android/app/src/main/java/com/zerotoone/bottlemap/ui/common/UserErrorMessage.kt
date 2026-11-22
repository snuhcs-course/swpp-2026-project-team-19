package com.zerotoone.bottlemap.ui.common

import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.data.owner.review.ReviewAlreadyAppliedException
import com.zerotoone.bottlemap.data.owner.review.ReviewVersionConflictException
import com.zerotoone.bottlemap.data.owner.review.ReviewDraftConflictException
import com.zerotoone.bottlemap.data.owner.review.ReviewDraftTooLargeLocalException
import com.zerotoone.bottlemap.data.owner.review.ReviewDraftLocalEditingException
import kotlinx.coroutines.CancellationException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

/** Presentation boundary for #189. Never trust even Korean server/exception text.
 * Callers supply an app-owned, task-specific fallback; codes stay intact for recovery.
 * Cancellation is control flow, not a failure to show or save in UI state.
 */
fun Throwable.userMessage(fallback: String = "처리하지 못했어요. 잠시 후 다시 시도해 주세요."): String {
    if (this is CancellationException) throw this
    return when (this) {
        is UserInputException -> notice
        is ReviewAlreadyAppliedException -> "이미 게시된 메뉴판이에요. 메뉴 관리에서 확인해 주세요."
        is ReviewVersionConflictException -> "검수 내용이 바뀌었어요. 다시 불러와 확인해 주세요."
        is ReviewDraftConflictException -> "최신 검수 내용을 다시 불러와 확인해 주세요."
        is ReviewDraftTooLargeLocalException -> "검수 내용이 너무 많아 기기에 보관했어요. 입력 내용을 줄여 주세요."
        is ReviewDraftLocalEditingException -> "수정 내용을 기기에 보관했어요. 연결을 확인한 뒤 다시 시도해 주세요."
        is BottleMapApiException -> when {
            code == "NETWORK_ERROR" -> ActionErrorNotices.NETWORK_MESSAGE
            httpStatus == 401 -> "로그인이 만료됐어요. 다시 로그인해 주세요."
            httpStatus == 403 -> "이 작업을 할 권한이 없어요. 계정과 매장 권한을 확인해 주세요."
            code == "REVIEW_OUTDATED" || code == "REVIEW_DRAFT_OUTDATED" || httpStatus == 409 ->
                "정보가 변경됐어요. 최신 내용을 불러온 뒤 다시 시도해 주세요."
            code == "RATE_LIMITED" || httpStatus == 429 ->
                "요청 가능한 횟수를 초과했어요. 잠시 후 다시 시도해 주세요."
            httpStatus == 413 -> "사진 용량이 너무 커요. 크기나 장수를 줄여 주세요."
            httpStatus == 404 -> "요청한 정보를 찾을 수 없어요. 이전 화면에서 다시 확인해 주세요."
            httpStatus != null && httpStatus >= 500 -> "서버에 일시적인 문제가 있어요. 잠시 후 다시 시도해 주세요."
            code in setOf("VALIDATION_FAILED", "INVALID_REQUEST") || httpStatus in setOf(400, 422) ->
                "입력한 내용을 확인한 뒤 다시 시도해 주세요."
            else -> fallback
        }
        is ConnectException, is SocketTimeoutException, is UnknownHostException -> ActionErrorNotices.NETWORK_MESSAGE
        else -> fallback
    }
}
