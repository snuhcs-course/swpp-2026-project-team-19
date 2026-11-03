package com.zerotoone.bottlemap.ui.owner

import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId

/** Pure local checks; a passing result must never be presented as an NTS match. */
class OwnerRegistrationPrecheckTest {
    private val future = LocalDate.of(2030, 1, 1)
        .atStartOfDay(ZoneId.of("Asia/Seoul")).toInstant().toEpochMilli()

    @Test fun locallyWellFormedBusinessFieldsAreAcceptedWithoutServerClaim() {
        assertNull(ownerRegistrationPrecheckError(
            "1234567891", "김민준", "2019-05-14", future))
    }

    @Test fun invalidBusinessChecksumIsRejectedBeforePosting() {
        assertNotNull(ownerRegistrationPrecheckError(
            "1234567890", "김민준", "2019-05-14", future))
    }

    @Test fun missingRepresentativeAndFutureOpeningDateAreRejected() {
        assertNotNull(ownerRegistrationPrecheckError(
            "1234567891", " ", "2019-05-14", future))
        assertNotNull(ownerRegistrationPrecheckError(
            "1234567891", "김민준", "2031-01-01", future))
    }
}
