package com.zerotoone.bottlemap.ui.common

import java.util.Locale

/**
 * UI-only portion label, shared by Customer detail/results and the Owner preview.
 * Never infer a pour volume from an unspecified option label such as "잔".
 */
internal fun servingDisplayLabel(pourMl: Int?, optionLabel: String?): String {
    if (pourMl != null) return "${pourMl}ml"
    val raw = optionLabel?.trim().orEmpty()
    return when(raw.lowercase(Locale.ROOT)) {
        "병", "bottle" -> "Bottle"
        else -> raw
    }
}
