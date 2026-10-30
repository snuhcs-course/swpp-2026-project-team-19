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

    @Test fun phoneFormattingDoesNotPreventIndependentContactInput() {
        assertEquals("0212345678", ownerPhoneDigits("02-1234-5678"))
        assertEquals("050712345678", ownerPhoneDigits("0507-1234-5678"))
        assertEquals("", ownerPhoneDigits(""))
        assertTrue(validOwnerPhone("")) // optional shop number; contact is required by screen separately
        assertFalse(validOwnerPhone("123"))
        assertFalse(validOwnerPhone("1234567890123"))
    }
}
