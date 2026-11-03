package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.*
import org.junit.Assert.*
import org.junit.Test

class OwnerRegistrationReapplicationTest {
    private val cert=MockPhoto("certificate","content://mock/certificate",MockPhotoKind.REGISTRATION_ATTACHMENT)
    private val cover=MockPhoto("cover","content://mock/cover",MockPhotoKind.BAR_GALLERY)
    private val menu=MockPhoto("menu","content://mock/menu",MockPhotoKind.MENU_CAPTURE)
    private fun rejected():MockOwnerApplication=MockOwnerApplication(
        applicationId="old-rejected",kind=MockApplicationKind.NEW_BAR,
        status=MockApplicationStatus.REJECTED,proposedBarName="몰트 앤 무드",
        proposedBarAddress="서울특별시 관악구 관악로 1 2층",
        representativeName="김민준",businessNumberDigits="1234567891",
        openingDateIso="2019-05-14",contactPhone="01012345678",
        storePhone="025551234",
        registrationPhotos=listOf(cert,cover,menu)
    )

    @Test fun rejectedReapplicationStartsIntroAndRestoresEveryAvailableFieldAndPhoto() {
        val input=rejected()
        val draft=reapplicationDraftFromRejected(input)
        assertEquals("INTRO",registrationResumePage(draft))
        assertEquals("몰트 앤 무드",draft.proposedBarName)
        assertEquals("서울특별시 관악구 관악로 1 2층",draft.proposedBarAddress)
        assertEquals("김민준",draft.representativeName)
        assertEquals("1234567891",draft.businessNumberDigits)
        assertEquals("2019-05-14",draft.openingDateIso)
        assertEquals("01012345678",draft.contactPhone)
        assertEquals("025551234",draft.storePhone)
        assertEquals(cert,draft.certificatePhoto)
        assertEquals(listOf(cover),draft.applicantGallery)
        assertEquals(listOf(menu),draft.initialMenuPhotos)
        assertEquals(MockApplicationStatus.REJECTED,input.status)
    }

    @Test fun rejectedExistingBarRetainsBarIdentityAndSkipsNewBarRequirements() {
        val rejected=rejected().copy(kind=MockApplicationKind.EXISTING_BAR,barId="saved-bar")
        val draft=reapplicationDraftFromRejected(rejected)
        assertEquals(MockApplicationKind.EXISTING_BAR,draft.kind)
        assertEquals("saved-bar",draft.existingBarId)
        assertEquals("INTRO",registrationResumePage(draft))
    }

    @Test fun nonRejectedApplicationCannotStartReapply() {
        try {
            reapplicationDraftFromRejected(rejected().copy(status=MockApplicationStatus.PENDING))
            fail("Only a rejected application may be re-submitted")
        }catch(_:IllegalArgumentException) {
            // No accidental second pending application is created.
        }
    }

    @Test fun approvedPreviewHasPublishedMenuWhileNewlyApprovedPreviewRequiresReview() {
        val unreviewed=ownerQaPreviewSnapshot(28)
        val reviewed=ownerQaPreviewSnapshot(29)
        assertFalse(unreviewed.hasPublishedInitialReview("qa-bar-1"))
        assertTrue(reviewed.hasPublishedInitialReview("qa-bar-1"))
    }
}
