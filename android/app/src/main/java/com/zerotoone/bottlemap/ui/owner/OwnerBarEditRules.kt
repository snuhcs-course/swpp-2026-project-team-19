package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockPhoto
import com.zerotoone.bottlemap.data.owner.MockWeeklyHours

/**
 * Owner Flow 5: local Mock-only editing rules; none of these fields are new API contracts.
 * Editing stays in a screen draft until the repository accepts a complete saveBar().
 */
internal fun barInfoError(
    name: String, description: String, address: String, phone: String, pourMl: String
): String? = when {
    name.trim().length !in 1..150 -> "매장명은 1~150자로 입력해 주세요."
    description.length > 100 -> "한 줄 소개는 100자 이하여야 해요."
    address.trim().length !in 1..500 -> "주소는 1~500자로 입력해 주세요."
    phone.length > 30 || (phone.isNotBlank() && !phone.matches(Regex("^[+0-9() .-]{1,30}$"))) ->
        "전화번호는 숫자와 전화번호 기호만 입력해 주세요."
    pourMl.isNotBlank() && (pourMl.toIntOrNull() == null || pourMl.toInt() !in 1..999) ->
        "기본 잔 용량은 1~999ml 사이로 입력해 주세요."
    else -> null
}

internal fun withBarInfo(
    bar: MockBar, name: String, description: String, address: String, phone: String, pourMl: String
): MockBar {
    require(barInfoError(name, description, address, phone, pourMl) == null)
    return bar.copy(
        name = name.trim(), description = description.trim().ifBlank { null },
        address = address.trim(), phone = phone.trim().ifBlank { null },
        defaultPourMl = pourMl.toIntOrNull()
    )
}

internal fun moveBarPhoto(photos: List<MockPhoto>, index: Int, offset: Int): List<MockPhoto> {
    val target = index + offset
    if (index !in photos.indices || target !in photos.indices) return photos
    return photos.toMutableList().apply { add(target, removeAt(index)) }
}
internal fun makeCoverPhoto(photos: List<MockPhoto>, index: Int): List<MockPhoto> =
    if (index !in photos.indices) photos else moveBarPhotoToFront(photos, index)

private fun moveBarPhotoToFront(photos: List<MockPhoto>, index: Int): List<MockPhoto> =
    photos.toMutableList().apply { add(0, removeAt(index)) }

/** Returns null when the tag is invalid or max five selections would be exceeded. */
internal fun toggleBarTag(current: List<String>, candidate: String): List<String>? {
    val value = candidate.trim()
    if (value.isEmpty() || value.length > 24) return null
    val existing = current.indexOfFirst { it.equals(value, ignoreCase = true) }
    if (existing >= 0) return current.filterIndexed { i, _ -> i != existing }
    if (current.size >= 5) return null
    return current + value
}

/** Null = no regular schedule, closed = weekly holiday, otherwise 5-minute hours. */
internal fun validWeeklyHourDraft(day: MockWeeklyHours): Boolean {
    if (day.isoDayOfWeek !in 1..7) return false
    if (day.closed) return true
    val start = day.openMinutes ?: return false
    val end = day.closeMinutes ?: return false
    return start in 0..1435 && end in 0..1435 &&
        start % 5 == 0 && end % 5 == 0 &&
        if (day.closesNextDay) end < start else end > start
}

internal fun weeklyHoursError(hours: List<MockWeeklyHours>): String? = when {
    hours.map { it.isoDayOfWeek }.distinct().size != hours.size -> "같은 요일이 중복됐어요."
    hours.any { !validWeeklyHourDraft(it) } -> "영업시간은 5분 단위이며 시작과 종료 시간이 달라야 해요."
    else -> null
}

internal fun withWeeklyHours(bar: MockBar, hours: List<MockWeeklyHours>): MockBar {
    require(weeklyHoursError(hours) == null)
    return bar.copy(weeklyHours = hours.sortedBy { it.isoDayOfWeek })
}

/**
 * ACTION_FIRST_v4 photo editor protects the first (cover) position from arrow
 * movement. Cover assignment is the only operation that can move a non-cover
 * photo into the first position.
 */
internal fun moveSecondaryBarPhoto(
    photos: List<MockPhoto>, index: Int, offset: Int,
): List<MockPhoto> = if (index <= 0 || index + offset <= 0)
    photos else moveBarPhoto(photos, index, offset)

/** HTML's "평일에 복사" applies Monday to Tue-Fri only. */
internal fun copyMondayToWeekdays(hours: List<MockWeeklyHours>): List<MockWeeklyHours> {
    val monday = hours.firstOrNull { it.isoDayOfWeek == 1 }
    return (hours.filterNot { it.isoDayOfWeek in 2..5 } +
        (2..5).mapNotNull { monday?.copy(isoDayOfWeek = it) })
        .sortedBy { it.isoDayOfWeek }
}
