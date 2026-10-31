package com.zerotoone.bottlemap.ui.owner

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Phone validation is local UX-only and intentionally not a mobile-prefix regex. */
class OwnerOnboardingValidationTest {
    @Test fun commonKoreanAreaMobileAnd0507NumbersAreAccepted() {
        assertTrue(validOwnerPhone("02-1234-5678"))
        assertTrue(validOwnerPhone("031-123-4567"))
        assertTrue(validOwnerPhone("010-1234-5678"))
        assertTrue(validOwnerPhone("0507-1234-5678"))
    }

    @Test fun v4KoreanBusinessNumberCheckDigitMatchesReference() {
        assertTrue(validBusinessRegistrationNumber("123-45-67891"))
        assertTrue(validBusinessRegistrationNumber("1234567891"))
        assertFalse(validBusinessRegistrationNumber("1234567890"))
        assertFalse(validBusinessRegistrationNumber("123"))
    }

    @Test fun v4OpeningDateRejectsImpossibleAndFutureDates() {
        assertTrue(validOpeningDate("2019-05-14"))
        assertFalse(validOpeningDate("2024-02-30"))
        assertFalse(validOpeningDate("2025-13-01"))
        assertFalse(validOpeningDate("2099-01-01"))
        assertFalse(validOpeningDate("20190514"))
    }

    @Test fun v4PhoneNumbersMustBeginWithZero() {
        assertFalse(validOwnerPhone("123456789"))
        assertTrue(validOwnerPhone("0507-1234-5678"))
        assertTrue(validOwnerPhone("02-1234-5678"))
        assertTrue(validOwnerPhone("031-123-4567"))
        assertEquals("0507-1234-5678", formatOwnerPhone("050712345678"))
    }

    @Test fun resumedMenuPhotoStepRebuildsBackPathForNewBar() {
        val menu = com.zerotoone.bottlemap.data.owner.MockPhoto(
            "photo-1", "content://picker/photo1",
            com.zerotoone.bottlemap.data.owner.MockPhotoKind.MENU_CAPTURE
        )
        val draft = com.zerotoone.bottlemap.data.owner.MockRegistrationDraft(
            proposedBarName = "Test", storePhone = "0212345678",
            initialMenuPhotos = listOf(menu), resumePageKey = "MENUS"
        )
        assertEquals("MENUS", registrationResumePage(draft))
        assertEquals("BARPHONE", registrationHistoryFor("MENUS", draft.kind).last())
        assertEquals("ADDRESS", registrationHistoryFor("BARPHONE", draft.kind).last())
    }

    @Test fun migratedDraftWithPhotosDoesNotJumpToContact() {
        val photo = com.zerotoone.bottlemap.data.owner.MockPhoto(
            "a", "content://picker/a",
            com.zerotoone.bottlemap.data.owner.MockPhotoKind.MENU_CAPTURE
        )
        val legacy = com.zerotoone.bottlemap.data.owner.MockRegistrationDraft(
            initialMenuPhotos = listOf(photo), resumePageKey = null
        )
        assertEquals("MENUS", registrationResumePage(legacy))
    }

    @Test fun completedMenuPhotoPageResumesAtContactWhenExplicitlySaved() {
        val draft = com.zerotoone.bottlemap.data.owner.MockRegistrationDraft(
            resumePageKey = "CONTACT",
            initialMenuPhotos = listOf(com.zerotoone.bottlemap.data.owner.MockPhoto(
                "p", "content://picker/p",
                com.zerotoone.bottlemap.data.owner.MockPhotoKind.MENU_CAPTURE
            ))
        )
        assertEquals("CONTACT", registrationResumePage(draft))
        assertEquals("MENUS", registrationHistoryFor("CONTACT", draft.kind).last())
    }

    @Test fun changingClaimedBarNameClearsStaleExistingBarSelection() {
        val original = com.zerotoone.bottlemap.data.owner.MockRegistrationDraft(
            kind = com.zerotoone.bottlemap.data.owner.MockApplicationKind.EXISTING_BAR,
            existingBarId = "candidate-1",
            proposedBarName = "기존 매장"
        )
        val edited = updatedBarNameDraft(original, "새 매장")
        assertEquals(com.zerotoone.bottlemap.data.owner.MockApplicationKind.NEW_BAR, edited.kind)
        assertEquals(null, edited.existingBarId)
        assertEquals("새 매장", edited.proposedBarName)
        assertEquals("candidate-1", original.existingBarId)
    }

    @Test fun unchangedClaimedBarNameStillReferencesChosenCandidate() {
        val original = com.zerotoone.bottlemap.data.owner.MockRegistrationDraft(
            kind = com.zerotoone.bottlemap.data.owner.MockApplicationKind.EXISTING_BAR,
            existingBarId = "candidate-1",
            proposedBarName = "기존 매장"
        )
        val edited = updatedBarNameDraft(original, " 기존 매장 ")
        assertEquals(com.zerotoone.bottlemap.data.owner.MockApplicationKind.EXISTING_BAR, edited.kind)
        assertEquals("candidate-1", edited.existingBarId)
    }

    @Test fun rejectingClaimDuringReviewMustVisitNewBarDetails() {
        val existing = com.zerotoone.bottlemap.data.owner.MockApplicationKind.EXISTING_BAR
        val newBar = com.zerotoone.bottlemap.data.owner.MockApplicationKind.NEW_BAR
        assertTrue(needsNewBarDetailsAfterClaimEdit(true, existing, newBar))
        assertFalse(needsNewBarDetailsAfterClaimEdit(false, existing, newBar))
        assertFalse(needsNewBarDetailsAfterClaimEdit(true, newBar, newBar))
        val backHistory = registrationHistoryFor("BARNAME", newBar) + "BARNAME"
        assertEquals("BARNAME", backHistory.last()) // BARPHOTO Back does not jump to REVIEW.
        assertEquals("BARPHOTO", registrationHistoryFor("ADDRESS", newBar).last())
        assertEquals("ADDRESS", registrationHistoryFor("BARPHONE", newBar).last())
    }

    @Test fun debugCandidatesReceiveDifferentIdsAcrossRegistrations() {
        val first = newDebugCandidateId()
        val second = newDebugCandidateId()
        assertTrue(first.startsWith("fixture-v4-bar-"))
        assertTrue(second.startsWith("fixture-v4-bar-"))
        assertFalse(first == second)
    }

    @Test fun existingBarPhotoStepBackReturnsToName() {
        val kind = com.zerotoone.bottlemap.data.owner.MockApplicationKind.EXISTING_BAR
        assertEquals("BARNAME", registrationHistoryFor("MENUS", kind).last())
    }

    @Test fun copyShopPhoneActionIsIndependentOfExistingPrivateNumber() {
        assertTrue(canCopyShopPhone("02-1234-5678"))
        assertTrue(canCopyShopPhone("0507-1234-5678"))
        assertFalse(canCopyShopPhone(""))
        assertFalse(canCopyShopPhone("112"))
        // UI keeps the button visible even when the copied value is already equal.
    }

    @Test fun phoneFormattingDoesNotPreventIndependentContactInput() {
        assertEquals("0212345678", ownerPhoneDigits("02-1234-5678"))
        assertEquals("050712345678", ownerPhoneDigits("0507-1234-5678"))
        assertEquals("", ownerPhoneDigits(""))
        assertTrue(validOwnerPhone("")) // optional shop number; contact is required by screen separately
        assertFalse(validOwnerPhone("123"))
        assertFalse(validOwnerPhone("1234567890123"))
    }
}
