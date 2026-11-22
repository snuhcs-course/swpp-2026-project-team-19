package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockApplicationKind
import com.zerotoone.bottlemap.data.owner.MockOwnerApplication
import com.zerotoone.bottlemap.data.owner.MockPhotoKind
import com.zerotoone.bottlemap.data.owner.MockRegistrationDraft
import java.util.UUID

/** Stable mock-only registration navigation checkpoint; never part of a Backend DTO. */
private val registrationCommon = listOf(
    "INTRO", "METHOD", "BN", "REP", "DATE", "BIZCHECK", "VERIFIED", "BARNAME"
)
private val registrationNewBar = listOf("BARPHOTO", "ADDRESS")
private val registrationEnd = listOf("MENUS", "CONTACT", "BARPHONE", "REVIEW")

internal fun registrationCheckpointable(page: String): Boolean =
    page in registrationCommon || page in registrationNewBar || page in registrationEnd

internal fun registrationResumePage(draft: MockRegistrationDraft): String {
    val stored = draft.resumePageKey
    if (stored != null && registrationCheckpointable(stored)) {
        // Older drafts collected BARPHONE before photos/contact, and existing-bar drafts skipped it.
        if (stored in listOf("CONTACT", "BARPHONE", "REVIEW") && draft.initialMenuPhotos.isEmpty()) return "MENUS"
        if (stored in listOf("BARPHONE", "REVIEW") && (draft.contactPhone.isBlank() || !validOwnerPhone(draft.contactPhone))) return "CONTACT"
        if (stored == "REVIEW" && (draft.storePhone.isBlank() || !validOwnerPhone(draft.storePhone))) return "BARPHONE"
        return stored
    }
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
 * Reconstruct back path on a new process. Resume from MENUS goes to ADDRESS for
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

/** When a claim becomes a new-bar application during review, collect all new-bar details. */
internal fun needsNewBarDetailsAfterClaimEdit(
    editingReview: Boolean,
    previousKind: MockApplicationKind,
    nextKind: MockApplicationKind,
): Boolean = editingReview && previousKind == MockApplicationKind.EXISTING_BAR &&
    nextKind == MockApplicationKind.NEW_BAR

/** Each Debug candidate must have a unique ID, including after earlier candidates were approved. */
internal fun newDebugCandidateId(): String = "fixture-v4-bar-" + UUID.randomUUID()

/** Whether the existing shop number can be copied into the private contact field. */
internal fun canCopyShopPhone(phone: String): Boolean = phone.isNotBlank() && validOwnerPhone(phone)

/** Prefill a *new* application from an earlier rejected application, without
 * modifying the submitted snapshot or treating the old review as approved.
 * The actual backend rejects clear submitted menu photos; API integration must
 * request new photo selection if photos are absent, not synthesize photo URLs.
 */
internal fun reapplicationDraftFromRejected(
    app:MockOwnerApplication
):MockRegistrationDraft {
    require(app.status == com.zerotoone.bottlemap.data.owner.MockApplicationStatus.REJECTED) {
        "Only rejected applications can be resubmitted"
    }
    return MockRegistrationDraft(
        kind=app.kind,
        existingBarId=if(app.kind==MockApplicationKind.EXISTING_BAR)app.barId else null,
        proposedBarName=app.proposedBarName,
        proposedBarAddress=app.proposedBarAddress.orEmpty(),
        businessNumberDigits=app.businessNumberDigits.orEmpty(),
        representativeName=app.representativeName.orEmpty(),
        openingDateIso=app.openingDateIso.orEmpty(),
        contactPhone=app.contactPhone.orEmpty(),
        storePhone=app.storePhone.orEmpty(),
        certificatePhoto=app.registrationPhotos.firstOrNull {
            it.kind==MockPhotoKind.REGISTRATION_ATTACHMENT
        },
        // A signed server image URL is for read-only display only. A new application
        // needs fresh picker URI grants, not an attempt to upload remote HTTP URLs.
        applicantGallery=app.registrationPhotos.filter {
            it.kind==MockPhotoKind.BAR_GALLERY && !it.uri.startsWith("http", ignoreCase=true)
        },
        initialMenuPhotos=app.registrationPhotos.filter {
            it.kind==MockPhotoKind.MENU_CAPTURE && !it.uri.startsWith("http", ignoreCase=true)
        },
        resumePageKey="INTRO",
    )
}

/** Copy is a persistent explicit link; typing a separate public number always unlinks it. */
internal fun registrationContactChanged(draft: MockRegistrationDraft, value: String): MockRegistrationDraft {
    val digits = ownerPhoneDigits(value)
    return draft.copy(contactPhone = digits,
        storePhone = if (draft.storePhoneMatchesContact) digits else draft.storePhone)
}
internal fun registrationStorePhoneChanged(draft: MockRegistrationDraft, value: String): MockRegistrationDraft =
    draft.copy(storePhone = ownerPhoneDigits(value), storePhoneMatchesContact = false)
internal fun registrationUseContactPhone(draft: MockRegistrationDraft): MockRegistrationDraft =
    draft.copy(storePhone = draft.contactPhone, storePhoneMatchesContact = true)

internal const val EXISTING_PUBLIC_PHONE_NOTE = "고객 공개용 매장 전화번호(운영자 검토 후 반영): "
internal fun existingBarPublicPhoneNote(draft: MockRegistrationDraft): String? =
    if (draft.kind == MockApplicationKind.EXISTING_BAR)
        EXISTING_PUBLIC_PHONE_NOTE + formatOwnerPhone(draft.storePhone) else null
internal fun existingBarPhoneFromNote(note: String?): String? = note
    ?.takeIf { it.startsWith(EXISTING_PUBLIC_PHONE_NOTE) }
    ?.removePrefix(EXISTING_PUBLIC_PHONE_NOTE)?.trim()
    ?.takeIf { it.isNotBlank() && validOwnerPhone(it) }
    ?.let(::ownerPhoneDigits)

internal fun registrationPhoneError(draft: MockRegistrationDraft): String? = when {
    draft.contactPhone.isBlank() || !validOwnerPhone(draft.contactPhone) -> "연락받을 번호를 확인해 주세요."
    draft.storePhone.isBlank() || !validOwnerPhone(draft.storePhone) -> "손님에게 공개할 매장 전화번호를 입력해 주세요."
    else -> null
}
