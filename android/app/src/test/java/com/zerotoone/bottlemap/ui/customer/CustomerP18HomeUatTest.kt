package com.zerotoone.bottlemap.ui.customer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** UAT 4.1 steps 15-17: invalid searches must stay on Home. */
class CustomerP18HomeUatTest {
    @Test fun blankAndWhitespaceRequireInput() {
        assertEquals("검색어를 입력해 주세요.", customerHomeSearchError(""))
        assertEquals("검색어를 입력해 주세요.", customerHomeSearchError("  \t "))
    }

    @Test fun punctuationOnlyIsNotAnUnknownWhisky() {
        assertEquals(
            "검색할 수 있는 문자가 없습니다. 제품명을 입력해 주세요.",
            customerHomeSearchError("!!!"),
        )
    }

    @Test fun validSearchesAllowKoreanEnglishAndThe100CharacterBoundary() {
        assertNull(customerHomeSearchError("아드벡 10"))
        assertNull(customerHomeSearchError("  ardbeg 10  "))
        assertNull(customerHomeSearchError("가".repeat(100)))
    }

    @Test fun tooLongSearchIsRejectedWithoutNavigation() {
        assertEquals(
            "검색어는 100자까지 입력할 수 있어요.",
            customerHomeSearchError("가".repeat(101)),
        )
    }
}
