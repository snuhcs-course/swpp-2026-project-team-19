package com.zerotoone.bottlemap.ui.common

import java.util.Locale

/**
 * UI-only portion label, shared by Customer detail/results and the Owner preview.
 * Never infer a pour volume from an unspecified option label such as "잔".
 */
internal fun servingDisplayLabel(pourMl: Int?, optionLabel: String?): String {
    val raw = optionLabel?.trim().orEmpty()
    // Bottle is a sale unit, not a glass size. Even a legacy row saved with
    // both label="병" and pourMl=700 must display as "Bottle".
    if (raw.lowercase(Locale.ROOT) in setOf("병", "bottle")) return "Bottle"
    if (pourMl != null) return "${pourMl}ml"
    return raw
}
