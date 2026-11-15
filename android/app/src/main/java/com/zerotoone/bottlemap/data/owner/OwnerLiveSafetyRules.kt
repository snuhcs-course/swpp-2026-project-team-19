package com.zerotoone.bottlemap.data.owner

import com.zerotoone.bottlemap.network.OwnerApplicationDto

/** Pure rules for the live Owner adapter; no network or Android framework dependency. */
internal fun requireMovedBarCoordinates(old: MockBar, changed: MockBar): Pair<Double, Double>? {
    if (old.address == changed.address) return null
    require(changed.latitude != null && changed.longitude != null &&
        (changed.latitude != old.latitude || changed.longitude != old.longitude)) {
        "주소 변경에는 새로운 지도 위치 확인이 필요해요. 현재 주소는 저장되지 않았어요."
    }
    return changed.latitude to changed.longitude
}

internal fun matchesPendingOwnerApplication(
    application: OwnerApplicationDto, draft: MockRegistrationDraft,
): Boolean = application.status == "pending" &&
    application.businessRegistrationNumber == draft.businessNumberDigits &&
    application.applicationType == (if (draft.kind == MockApplicationKind.EXISTING_BAR)
        "existing_bar" else "new_bar") &&
    (draft.kind != MockApplicationKind.EXISTING_BAR ||
        application.bar?.barId == draft.existingBarId)

internal fun currentReviewImageUri(local: String?, server: String): String =
    local?.takeUnless { it.startsWith("http://", ignoreCase = true) ||
        it.startsWith("https://", ignoreCase = true) } ?: server

internal fun needsReviewDetailReload(previous: MockMenuImport?, serverVersion: Int): Boolean =
    previous?.images.isNullOrEmpty() || previous?.reviewVersion != serverVersion

internal fun validateReviewOptionClearing(
    edited: MockMenuOption, extracted: MockMenuOption,
) {
    // An OCR glass with an extracted ml may legitimately be reclassified
    // as Bottle (pourMl=null). Likewise the reviewed glass label can be
    // cleared because the Owner's option identity is the ml, not "잔"/"샷".
    // Preserve extractedOptionId; the server validates the final options[].
    require(edited.pourMl != null || extracted.pourMl == null ||
        isBottleServingLabel(edited.label)) {
        "용량을 입력하거나 Bottle 판매를 선택해 주세요."
    }
    require(edited.label != null || extracted.label == null ||
        edited.pourMl != null) {
        "용량이 없는 옵션은 종류를 확인해 주세요."
    }
}

/** Include every serving recognized on different photos, without dropping the other lines. */
internal fun reviewedServingsByProduct(
    job: MockMenuImport, existingProductIds: Set<String>,
): Map<String, List<MockMenuOption>> =
    job.images.flatMap { it.lines }
        .filter { it.decision?.kind == MockDecisionKind.SELECT_PRODUCT &&
            it.decision?.productId?.let(existingProductIds::contains) == true }
        .groupBy { requireNotNull(it.decision?.productId) }
        .mapValues { (_, lines) ->
            lines.flatMap { it.decision?.correctedOptions ?: it.options }
                .distinctBy { reviewServingKey(it.pourMl, it.label) }
        }

internal fun sampledBitmapSize(width: Int, height: Int, maxEdge: Int = 2400): Int {
    require(width > 0 && height > 0 && maxEdge > 0)
    var sample = 1
    while(width / sample > maxEdge || height / sample > maxEdge) sample *= 2
    return sample
}

/**
 * Stage and upload replacements before deleting existing server photos. The server
 * may reject an upload at its gallery capacity; in that case the old photo survives.
 * A caller must reload after a partial server failure rather than repeat deletions.
 */
internal suspend fun <T> replaceOwnerGallerySafely(
    old: List<MockPhoto>, now: List<MockPhoto>,
    prepare: suspend (MockPhoto) -> T,
    upload: suspend (T) -> String,
    delete: suspend (String) -> Unit,
    reorder: suspend (List<String>) -> Unit,
) {
    val oldIds = old.mapTo(mutableSetOf()) { it.photoId }
    val additions = now.filter { it.photoId !in oldIds }
    val prepared = additions.associate { it.photoId to prepare(it) }
    val mapped = old.associate { it.photoId to it.photoId }.toMutableMap()

    for (photo in additions) {
        mapped[photo.photoId] = upload(prepared.getValue(photo.photoId))
    }
    for (photo in old) {
        if (now.none { it.photoId == photo.photoId }) delete(photo.photoId)
    }
    reorder(now.map { mapped.getValue(it.photoId) })
}
