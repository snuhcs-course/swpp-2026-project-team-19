package com.zerotoone.bottlemap.data.owner

import java.util.Locale

/**
 * BottleMap Android serving-name policy.
 *
 * The UI always shows "Bottle". During Owner photo review, both Korean "병"
 * and English "Bottle" mean the same bottle serving, whereas 30ml "잔"
 * and 30ml "샷" remain independently priced servings.
 *
 * Backend #164 still stores the submitted literal optionLabel; new Android
 * review requests canonicalize bottle to "Bottle" without changing OCR
 * extractedOptionId or editing existing persisted rows behind the Owner's back.
 */
internal fun isBottleServingLabel(label: String?): Boolean =
    label?.trim()?.lowercase(Locale.ROOT) in setOf("병", "bottle")

internal fun canonicalServingLabel(label: String?): String? {
    val trimmed = label?.trim() ?: return null
    return if (isBottleServingLabel(trimmed)) "Bottle" else trimmed
}

internal fun servingIdentityKey(pourMl: Int?, label: String?): String {
    val normalized = canonicalServingLabel(label).orEmpty().lowercase(Locale.ROOT)
    val volume = if (normalized == "bottle") null else pourMl
    return "label:$normalized|ml:${volume ?: "none"}"
}
