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
    require(edited.pourMl != null || extracted.pourMl == null) {
        "추출된 용량은 비울 수 없어요."
    }
    require(edited.label != null || extracted.label == null) {
        "추출된 옵션 이름은 비울 수 없어요."
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
                .distinctBy { it.pourMl to it.label?.trim()?.lowercase() }
        }

internal fun sampledBitmapSize(width: Int, height: Int, maxEdge: Int = 2400): Int {
    require(width > 0 && height > 0 && maxEdge > 0)
    var sample = 1
    while(width / sample > maxEdge || height / sample > maxEdge) sample *= 2
    return sample
}
