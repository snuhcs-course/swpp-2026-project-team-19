package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockExtractedLine
import com.zerotoone.bottlemap.data.owner.MockLineKind
import com.zerotoone.bottlemap.data.owner.MockMenuOption
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * All entry points (summary, next, previous and list) must use the same
 * routing rule; PDF p89/90 must never regress to the p87 match screen.
 */
class Stage8ReviewDestinationTest {
    @Test fun unmatchedSignatoryGoesDirectlyToNewProductEvenWhenItHasAPrice() {
        val line=MockExtractedLine("s","시그나토리 쿨일라13",MockLineKind.PRODUCT,
            options=listOf(MockMenuOption("s1",label="잔",pourMl=30,priceKrw=20000)))
        assertEquals("new",stage8ReviewDestination(line))
    }

    @Test fun knownBookersWithoutExtractedPriceGoesDirectlyToPriceInput() {
        val line=MockExtractedLine("b","부커스",MockLineKind.PRODUCT,
            suggestedProductId="bookers-product",
            options=listOf(MockMenuOption("b1",label="잔",pourMl=null,priceKrw=0)))
        assertEquals("price",stage8ReviewDestination(line))
    }

    @Test fun knownHakushuAndMultiCandidateStayInItemMatching() {
        val hakushu=MockExtractedLine("h","하쿠슈DR",MockLineKind.PRODUCT,
            suggestedProductId="hakushu",options=listOf(
                MockMenuOption("h1",label="잔",pourMl=30,priceKrw=19000)))
        val russell=MockExtractedLine("r","러셀 싱글배럴",MockLineKind.PRODUCT,
            candidateProductIds=listOf("single","rye"),options=listOf(
                MockMenuOption("r1",label="잔",pourMl=30,priceKrw=15000)))
        assertEquals("line",stage8ReviewDestination(hakushu))
        assertEquals("line",stage8ReviewDestination(russell))
    }

    @Test fun noCandidateAndNoPriceStillGoesToNewProductNotCandidatePage() {
        val line=MockExtractedLine("m","미매칭",MockLineKind.PRODUCT,
            options=listOf(MockMenuOption("m1",priceKrw=0)))
        assertEquals("new",stage8ReviewDestination(line))
    }
}
