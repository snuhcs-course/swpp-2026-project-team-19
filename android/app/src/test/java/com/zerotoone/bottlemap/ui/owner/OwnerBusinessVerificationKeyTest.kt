package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockRegistrationDraft
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** UAT 4.9: prior successful business verification never validates edited fields. */
class OwnerBusinessVerificationKeyTest {
    @Test fun changingOpeningDateInvalidatesPreviousMatchedResult() {
        val checked = MockRegistrationDraft(
            businessNumberDigits = "1234567890",
            representativeName = "홍길동",
            openingDateIso = "2020-11-16",
        )
        val fingerprint = ownerBusinessVerificationKey(checked)
        assertTrue(ownerBusinessVerificationIsCurrent(fingerprint, checked))
        assertFalse(ownerBusinessVerificationIsCurrent(
            fingerprint, checked.copy(openingDateIso = "2020-11-17")))
        assertFalse(ownerBusinessVerificationIsCurrent(null, checked))
    }

    @Test fun changingBusinessNumberOrRepresentativeAlsoInvalidatesResult() {
        val checked = MockRegistrationDraft(
            businessNumberDigits = "1234567890",
            representativeName = "홍길동",
            openingDateIso = "2020-11-16",
        )
        val key = ownerBusinessVerificationKey(checked)
        assertFalse(ownerBusinessVerificationIsCurrent(
            key, checked.copy(businessNumberDigits = "1234567891")))
        assertFalse(ownerBusinessVerificationIsCurrent(
            key, checked.copy(representativeName = "다른 대표자")))
    }

    @Test fun insignificantDateAndNumberFormattingDoesNotInvalidateResult() {
        val checked = MockRegistrationDraft(
            businessNumberDigits = "1234567890",
            representativeName = "홍길동",
            openingDateIso = "2020-11-16",
        )
        val key = ownerBusinessVerificationKey(checked)
        assertTrue(ownerBusinessVerificationIsCurrent(
            key, checked.copy(
                businessNumberDigits = "123-45-67890",
                openingDateIso = "2020.11.16",
                representativeName = " 홍길동 ",
            )))
    }
}
