package com.zerotoone.bottlemap.data.owner

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** An asynchronous Owner GET must never roll back newer local registration input. */
class OwnerRegistrationRefreshTest {
    @Test fun slowOwnerRefreshCannotRestoreStaleOpeningDateAfterCorrection() {
        val old = MockRegistrationDraft(
            businessNumberDigits = "1234567891",
            representativeName = "김민준",
            openingDateIso = "2019-05-13",
            resumePageKey = "BIZCHECK",
        )
        // The GET started on the incorrect opening date.
        val refreshStartedFrom = MockOwnerSnapshot(registrationDraft = old)
        // While the GET was in flight, the user corrected the date and
        // advanced through the verification result to the next step.
        val current = MockOwnerSnapshot(registrationDraft = old.copy(
            openingDateIso = "2019-05-14", resumePageKey = "BARNAME"))
        val merged = keepLatestOwnerRegistrationDraft(
            refreshed = refreshStartedFrom, current = current)
        assertEquals("2019-05-14", merged.registrationDraft!!.openingDateIso)
        assertEquals("BARNAME", merged.registrationDraft!!.resumePageKey)
    }

    @Test fun lateGetCannotResurrectDraftAlreadyClearedAfterApplication() {
        val old = MockOwnerSnapshot(registrationDraft = MockRegistrationDraft(
            openingDateIso = "2019-05-13"))
        val afterSubmit = old.copy(registrationDraft = null)
        val result = keepLatestOwnerRegistrationDraft(old, afterSubmit)
        assertNull(result.registrationDraft)
    }

    @Test fun serverRefreshStillUpdatesServerOwnedFields() {
        val current = MockOwnerSnapshot(registrationDraft = MockRegistrationDraft(
            openingDateIso = "2019-05-14"))
        val refreshed = MockOwnerSnapshot(nextLocalId = 21L,
            registrationDraft = MockRegistrationDraft(openingDateIso = "2019-05-13"))
        val result = keepLatestOwnerRegistrationDraft(refreshed, current)
        assertEquals(21L, result.nextLocalId)
        assertEquals("2019-05-14", result.registrationDraft!!.openingDateIso)
    }
}
