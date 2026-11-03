package com.zerotoone.bottlemap.ui.owner

import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/** v4 local form validation. This never performs identity verification. */
internal fun ownerPhoneDigits(value: String): String =
    value.filter(Char::isDigit).take(12)

/** Includes 02, 0xx, 010 and 050x numbers. Contact fields check nonblank separately. */
internal fun validOwnerPhone(value: String): Boolean =
    value.isBlank() || Regex("^0[0-9]{8,11}$").matches(value.filter(Char::isDigit))

internal fun ownerBusinessDigits(value: String): String =
    value.filter(Char::isDigit).take(10)

/** Korean business-number check digit, per v4 and API §3.11.2. Not an NTS lookup. */
internal fun validBusinessRegistrationNumber(value: String): Boolean {
    val number = ownerBusinessDigits(value)
    if (number.length != 10) return false
    val weights = intArrayOf(1, 3, 7, 1, 3, 7, 1, 3, 5)
    var sum = 0
    for (index in weights.indices) sum += (number[index] - '0') * weights[index]
    sum += ((number[8] - '0') * 5) / 10
    return (10 - sum % 10) % 10 == (number[9] - '0')
}

/** Stored date format matches the current request contract YYYY-MM-DD. */
internal fun validOpeningDate(iso: String, nowMillis: Long = System.currentTimeMillis()): Boolean {
    if (!Regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$").matches(iso)) return false
    val format = SimpleDateFormat("yyyy-MM-dd", Locale.US).apply {
        isLenient = false
        timeZone = TimeZone.getTimeZone("Asia/Seoul")
    }
    val date = try { format.parse(iso) } catch (_: Exception) { null } ?: return false
    return date.time <= nowMillis
}

/** For display only; canonical Mock phone state is always digits. */
internal fun formatOwnerPhone(value: String): String {
    val digits = ownerPhoneDigits(value)
    val prefix = when {
        digits.startsWith("02") -> 2
        digits.startsWith("050") -> 4
        else -> 3
    }
    if (digits.length <= prefix) return digits
    val remaining = digits.substring(prefix)
    if (remaining.length <= 4) return digits.substring(0, prefix) + "-" + remaining
    val middle = if (remaining.length >= 8) 4 else 3
    return digits.substring(0, prefix) + "-" + remaining.substring(0, middle) + "-" + remaining.substring(middle)
}
