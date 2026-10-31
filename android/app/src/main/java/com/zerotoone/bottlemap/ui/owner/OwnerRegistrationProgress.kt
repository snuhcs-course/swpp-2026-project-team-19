package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockApplicationKind
import com.zerotoone.bottlemap.data.owner.MockRegistrationDraft

/** Stable mock-only registration navigation checkpoint; never part of a Backend DTO. */
private val registrationCommon = listOf(
    "INTRO", "METHOD", "BN", "REP", "DATE", "BIZCHECK", "VERIFIED", "BARNAME"
)
private val registrationNewBar = listOf("BARPHOTO", "ADDRESS", "BARPHONE")
private val registrationEnd = listOf("MENUS", "CONTACT", "REVIEW")

internal fun registrationCheckpointable(page: String): Boolean =
    page in registrationCommon || page in registrationNewBar || page in registrationEnd

internal fun registrationResumePage(draft: MockRegistrationDraft): String {
    val stored = draft.resumePageKey
    if (stored != null && registrationCheckpointable(stored)) return stored
    // Migration for drafts saved before the checkpoint field existed.
    return when {
        draft.initialMenuPhotos.isNotEmpty() -> "MENUS"
        draft.kind == MockApplicationKind.EXISTING_BAR && draft.existingBarId != null -> "MENUS"
        draft.storePhone.isNotBlank() -> "BARPHONE"
        draft.proposedBarAddress.isNotBlank() -> "ADDRESS"
        draft.applicantGallery.isNotEmpty() -> "BARPHOTO"
        draft.proposedBarName.isNotBlank() -> "BARNAME"
        draft.businessNumberDigits.isNotBlank() && draft.representativeName.isNotBlank() &&
            draft.openingDateIso.isNotBlank() -> "BIZCHECK"
        draft.openingDateIso.isNotBlank() -> "DATE"
        draft.representativeName.isNotBlank() -> "REP"
        draft.businessNumberDigits.isNotBlank() -> "BN"
        else -> "METHOD"
    }
}

/**
 * Reconstruct back path on a new process. Resume from MENUS goes to BARPHONE for
 * new bars and BARNAME for existing-bar claims, never immediately to My Page.
 */
internal fun registrationHistoryFor(page: String, kind: MockApplicationKind): List<String> {
    val path = registrationCommon +
        (if (kind == MockApplicationKind.NEW_BAR) registrationNewBar else emptyList()) +
        registrationEnd
    val index = path.indexOf(page)
    return if (index <= 0) emptyList() else path.take(index)
}

/**
 * Name edits after selecting an existing candidate must not preserve a stale bar ID.
 * This is a local UI draft transition, not a backend request mapping.
 */
internal fun updatedBarNameDraft(draft: MockRegistrationDraft, rawName: String): MockRegistrationDraft {
    val name = rawName.take(150)
    val changedSelectedBar = draft.kind == MockApplicationKind.EXISTING_BAR &&
        !draft.proposedBarName.trim().equals(name.trim(), ignoreCase = true)
    return if (changedSelectedBar) {
        draft.copy(proposedBarName = name, kind = MockApplicationKind.NEW_BAR, existingBarId = null)
    } else {
        draft.copy(proposedBarName = name)
    }
}

/** Whether the existing shop number can be copied into the private contact field. */
internal fun canCopyShopPhone(phone: String): Boolean = phone.isNotBlank() && validOwnerPhone(phone)
