package com.zerotoone.bottlemap.network

/** Owner-facing explanation for an API write failure. Never discard fieldErrors on HTTP 422. */
fun menuWriteErrorText(error: Throwable): String {
    if (error !is BottleMapApiException) {
        return error.message ?: "메뉴를 저장하지 못했어요. 다시 시도해 주세요."
    }
    if (error.code != "VALIDATION_FAILED" || error.fieldErrors.isEmpty()) {
        return if (error.code == "VALIDATION_FAILED")
            "입력값을 확인해 주세요. (서버 응답 422: 상세 오류 없음)"
        else error.message
    }
    val field = error.fieldErrors.first()
    val path = field.path
    // A new Android client cannot publish bar-local menu data to the old
    // backend schema. Explaining this prevents repeated destructive retries.
    val incompatible = error.fieldErrors.any {
        (it.code.equals("EXTRA_FORBIDDEN", ignoreCase = true) ||
            it.code.equals("UNION_TAG_INVALID", ignoreCase = true) ||
            it.code.equals("LITERAL_ERROR", ignoreCase = true)) &&
            (it.path.contains("localItem") || it.path.contains("addedOptions") ||
                it.path.contains("itemDecisions"))
    }
    if (incompatible) {
        return "앱과 서버의 메뉴 등록 API 버전이 달라요. 서버 업데이트를 확인해 주세요. (${path})"
    }
    val title = when {
        path.startsWith("options[") -> {
            val index = path.substringAfter('[').substringBefore(']').toIntOrNull()
            val row = index?.plus(1)?.let { "${it}번 옵션" } ?: "가격 옵션"
            when {
                path.endsWith(".priceKrw") -> "${row} 가격"
                path.endsWith(".pourMl") -> "${row} 용량"
                path.endsWith(".optionLabel") -> "${row} 이름"
                else -> row
            }
        }
        path.startsWith("itemDecisions") -> "사진 검수 항목"
        path.startsWith("changeDecisions") -> "사진 검수 변경"
        path == "menuVersion" || path == "reviewVersion" -> "메뉴 버전"
        path.contains("displayName") -> "메뉴 이름"
        path.contains("category") -> "주류 종류"
        else -> path
    }
    return "입력값 확인: ${title} — ${field.message}"
}
