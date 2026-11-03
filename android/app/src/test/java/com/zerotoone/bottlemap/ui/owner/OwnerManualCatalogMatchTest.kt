package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockBrand
import com.zerotoone.bottlemap.data.owner.MockCatalogProduct
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class OwnerManualCatalogMatchTest {
    private val brand=MockBrand("brand-gf","Glenfiddich","글렌피딕")
    private val twelve=MockCatalogProduct(
        productId="product-12",brandId="brand-gf",
        displayName="Glenfiddich 12 Year Old",category="whisky",ageYears=12)
    private val fifteen=twelve.copy(productId="product-15",ageYears=15,
        displayName="Glenfiddich 15 Year Old")

    @Test fun brandCanBeSearchedAfterItsOnlyBarMenuWasDeleted() {
        assertEquals("글렌피딕",manualBrandSearchQuery("글렌 피딕12년",""))
        assertEquals("Glenfiddich",manualBrandSearchQuery("글렌 피딕12년","Glenfiddich"))
        assertEquals(brand,manualBrandProposal(listOf(brand),"글렌 피딕12년","",null))
        assertNull(manualBrandProposal(listOf(brand),"글렌 피딕12년","","brand-gf"))
    }

    @Test fun sameCatalogProductCanBeSuggestedAfterBrandConfirmation() {
        assertEquals(twelve,manualProductProposal(listOf(twelve,fifteen),
            "글렌 피딕12년","위스키","brand-gf",null))
        assertNull(manualProductProposal(listOf(twelve,fifteen),
            "글렌 피딕12년","위스키","brand-gf","product-12"))
    }

    @Test fun multipleSameAgeEditionsDoNotAutoSelectOne() {
        val other=twelve.copy(productId="other-12",
            displayName="Glenfiddich 12 Special Edition")
        assertNull(manualProductProposal(listOf(twelve,other),
            "글렌피딕 12년","위스키","brand-gf",null))
    }

    @Test fun missingBrandConfirmationDoesNotInferEnglishProductId() {
        assertNull(manualProductProposal(listOf(twelve),
            "글렌피딕12년","위스키",null,null))
    }
}
