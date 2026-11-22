package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.*
import com.zerotoone.bottlemap.network.BottleMapApiException
import kotlinx.coroutines.CancellationException
import org.junit.Assert.*
import org.junit.Test

class OwnerRegistrationConsentFlowTest {
    @Test fun copiedPublicNumberTracksContactUntilDirectlyEdited() {
        val first = MockRegistrationDraft(contactPhone="01012345678",storePhone="0212345678")
        val copied = registrationUseContactPhone(first)
        val changed = registrationContactChanged(copied,"02-555-1234")
        assertEquals("025551234",changed.storePhone)
        assertTrue(changed.storePhoneMatchesContact)
        val separate = registrationStorePhoneChanged(changed,"0507-1234-5678")
        val final = registrationContactChanged(separate,"01099998888")
        assertEquals("050712345678",final.storePhone)
        assertFalse(final.storePhoneMatchesContact)
    }
    @Test fun bothApplicationKindsCollectMenuThenContactThenPublicPhone() {
        for(kind in MockApplicationKind.entries) {
            assertEquals("MENUS",registrationHistoryFor("CONTACT",kind).last())
            assertEquals("CONTACT",registrationHistoryFor("BARPHONE",kind).last())
            assertEquals("BARPHONE",registrationHistoryFor("REVIEW",kind).last())
        }
    }
    @Test fun oldPhoneCheckpointCannotSkipPhotosOrContactAndOldReviewRequiresPublicPhone() {
        val photo=MockPhoto("menu","content://photo",MockPhotoKind.MENU_CAPTURE)
        val old=MockRegistrationDraft(resumePageKey="BARPHONE",storePhone="025551234")
        assertEquals("MENUS",registrationResumePage(old))
        assertEquals("CONTACT",registrationResumePage(old.copy(initialMenuPhotos=listOf(photo))))
        assertEquals("BARPHONE",registrationResumePage(old.copy(resumePageKey="REVIEW",storePhone="",
            initialMenuPhotos=listOf(photo),contactPhone="01012345678")))
    }
    @Test fun existingPublicNumberIsAnExplicitOperatorProposalNotPrivateContactSubstitution() {
        val draft=MockRegistrationDraft(kind=MockApplicationKind.EXISTING_BAR,
            contactPhone="01012345678",storePhone="025551234")
        val note=existingBarPublicPhoneNote(draft)!!
        assertTrue(note.contains("운영자 검토 후 반영"))
        assertEquals("025551234",existingBarPhoneFromNote(note))
        assertFalse(note.contains(draft.contactPhone))
        assertNull(existingBarPublicPhoneNote(draft.copy(kind=MockApplicationKind.NEW_BAR)))
        assertNull(existingBarPhoneFromNote("arbitrary server note"))
    }
    @Test fun neitherRequiredNumberMayBeBlankAndContactIsNotRestrictedToMobile() {
        assertNotNull(registrationPhoneError(MockRegistrationDraft(contactPhone="01012345678")))
        assertNull(registrationPhoneError(MockRegistrationDraft(contactPhone="025551234",storePhone="07012345678")))
    }
    @Test fun dailyOcrLimitKeepsManualEntryInstructionWithoutChangingNtsMapper() {
        for(error in listOf(
            BottleMapApiException(code="RATE_LIMITED",message="raw"),
            BottleMapApiException(code="OTHER",httpStatus=429,message="raw"))) {
            val message=certificateOcrFailureMessage(error)!!
            assertTrue(message.contains("오늘"));assertTrue(message.contains("직접 입력"))
            assertFalse(message.contains("잠시 후"));assertFalse(message.contains("raw"))
        }
        assertTrue(certificateOcrFailureMessage(IllegalStateException("raw"))!!.contains("직접 입력"))
        val cancelled=CancellationException("cancelled")
        try {certificateOcrFailureMessage(cancelled);fail("Cancellation swallowed")}
        catch(caught:CancellationException){assertSame(cancelled,caught)}
    }
}
