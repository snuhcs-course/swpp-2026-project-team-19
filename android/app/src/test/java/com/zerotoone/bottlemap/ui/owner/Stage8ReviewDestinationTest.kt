package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockExtractedLine
import com.zerotoone.bottlemap.data.owner.MockLineKind
import com.zerotoone.bottlemap.data.owner.MockMenuOption
import com.zerotoone.bottlemap.data.owner.MockCatalogProduct
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

    @Test fun ambiguousOrUnselectedCandidateWithMissingPriceRequiresMatchingFirst() {
        val ambiguous=MockExtractedLine("a","메뉴판 인식 줄",MockLineKind.PRODUCT,
            candidateProductIds=listOf("first","second"),
            options=listOf(MockMenuOption("a1",priceKrw=0)))
        val single=ambiguous.copy(candidateProductIds=listOf("first"))
        val suggested=ambiguous.copy(suggestedProductId="first")
        assertEquals("line",stage8ReviewDestination(ambiguous))
        assertEquals("line",stage8ReviewDestination(single))
        assertEquals("line",stage8ReviewDestination(suggested))
    }

    @Test fun inactiveSuggestionWithOneActiveFallbackRequiresMatchingBeforePrice() {
        val suggested=MockCatalogProduct("retired","brand","Retired",isActive=false)
        val fallback=MockCatalogProduct("active","brand","Active")
        val line=MockExtractedLine("mixed","Mixed OCR",MockLineKind.PRODUCT,
            suggestedProductId="retired",candidateProductIds=listOf("active"),
            options=listOf(MockMenuOption("o",label="잔",pourMl=30,priceKrw=0)))
        assertEquals("line",stage8DestinationForCatalog(line,listOf(suggested,fallback)))
        assertEquals("catalog",stage8DestinationForCatalog(line,listOf(suggested)))
        // A valid, unambiguous active suggestion retains the direct price flow.
        assertEquals("price",stage8DestinationForCatalog(
            line.copy(suggestedProductId="active",candidateProductIds=emptyList()),
            listOf(suggested,fallback)))
    }

    @Test fun noCandidateAndNoPriceStillGoesToNewProductNotCandidatePage() {
        val line=MockExtractedLine("m","미매칭",MockLineKind.PRODUCT,
            options=listOf(MockMenuOption("m1",priceKrw=0)))
        assertEquals("new",stage8ReviewDestination(line))
    }
}
