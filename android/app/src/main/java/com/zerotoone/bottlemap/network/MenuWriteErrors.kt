package com.zerotoone.bottlemap.network

import com.zerotoone.bottlemap.ui.common.userMessage

/** Translate field codes to app-owned copy. Neither field paths nor server prose is UI text. */
fun menuWriteErrorText(error: Throwable): String {
    val fallback = "메뉴를 저장하지 못했어요. 입력 내용을 확인하고 다시 시도해 주세요."
    if (error !is BottleMapApiException) return error.userMessage(fallback)
    if (error.code != "VALIDATION_FAILED" || error.fieldErrors.isEmpty())
        return error.userMessage(fallback)
    if (error.fieldErrors.any {
            it.code.uppercase() in setOf("EXTRA_FORBIDDEN", "UNION_TAG_INVALID", "LITERAL_ERROR")
        }) return "현재 앱에서 메뉴를 저장할 수 없어요. 앱을 업데이트한 뒤 다시 시도해 주세요."
    val field = error.fieldErrors.first()
    if (field.path in setOf("menuVersion", "reviewVersion"))
        return "메뉴 정보가 변경됐어요. 최신 내용을 불러온 뒤 다시 시도해 주세요."
    val option = Regex("options\\[(\\d+)]\\..+").matchEntire(field.path)
        ?.groupValues?.get(1)?.toIntOrNull()?.takeIf { it in 0..99 }
        ?.let { "${it + 1}번 옵션 " }.orEmpty()
    val title = when {
        field.path.matches(Regex("options\\[\\d+]\\.priceKrw")) -> "${option}가격"
        field.path.matches(Regex("options\\[\\d+]\\.pourMl")) -> "${option}용량"
        field.path.matches(Regex("options\\[\\d+]\\.optionLabel")) -> "${option}용량 이름"
        field.path == "displayName" || field.path == "name" -> "메뉴 이름"
        field.path == "category" || field.path == "kind" -> "주류 종류"
        field.path.startsWith("itemDecisions") || field.path.startsWith("changeDecisions") -> "메뉴 검수 내용"
        else -> "입력 내용"
    }
    val action = when (field.code.uppercase()) {
        "MISSING", "BLANK", "STRING_TOO_SHORT" -> "빠진 항목을 입력해 주세요."
        "STRING_TOO_LONG" -> "입력한 내용을 줄여 주세요."
        "GREATER_THAN", "GREATER_THAN_EQUAL", "LESS_THAN", "LESS_THAN_EQUAL", "INT_PARSING", "INT_TYPE" ->
            "입력할 수 있는 숫자 범위를 확인해 주세요."
        else -> "입력한 값을 확인해 주세요."
    }
    return "$title: $action"
}
