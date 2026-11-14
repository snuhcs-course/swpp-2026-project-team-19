package com.zerotoone.bottlemap.data.owner

import java.util.Locale

/**
 * BottleMap Android serving-name policy.
 *
 * The Owner distinguishes servings by volume, NOT the OCR's word for a
 * serving. Thus "잔 30ml" and "샷 30ml" have the same identity, while 60ml
 * is separate. Korean "병" and English "Bottle" are one bottle identity,
 * regardless of a printed bottle capacity.
 *
 * Backend #164 still keys options by (optionLabel, pourMl). The Android
 * review serializer uses a null optionLabel for sized non-bottle servings
 * so fresh Android-reviewed options have one stable server representation.
 * No existing server rows are migrated or rewritten.
 */
private val bottleWithSize = Regex(
    """^(?:병|bottle)\s*\(?\s*\d{1,4}(?:\.\d+)?\s*(?:ml|l)\s*\)?$""",
    RegexOption.IGNORE_CASE,
)

internal fun isBottleServingLabel(label: String?): Boolean {
    val normalized = label?.trim()?.lowercase(Locale.ROOT) ?: return false
    return normalized in setOf("병", "bottle") || bottleWithSize.matches(normalized)
}

internal fun canonicalServingLabel(label: String?): String? {
    val trimmed = label?.trim() ?: return null
    return if (isBottleServingLabel(trimmed)) "Bottle" else trimmed
}

/** One non-bottle option per ml, independent of any OCR words.
 * An unspecified pour cannot be distinguished by an arbitrary label.
 */
internal fun servingIdentityKey(pourMl: Int?, label: String?): String = when {
    isBottleServingLabel(label) -> "bottle"
    pourMl != null -> "ml:$pourMl"
    else -> "ml:unspecified"
}
