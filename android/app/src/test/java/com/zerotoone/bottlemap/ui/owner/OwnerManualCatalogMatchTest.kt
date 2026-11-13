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

    @Test fun inactiveCatalogProductIsVisibleButNotSelectable() {
        val inactive = twelve.copy(isActive = false)
        assertEquals(inactive, inactiveOwnerCatalogMatch(
            listOf(inactive), "Glenfiddich 12 Year Old"))
        assertNull(manualProductProposal(listOf(inactive),
            "Glenfiddich 12 Year Old", "위스키", "brand-gf", null))
        assertNull(inactiveOwnerCatalogMatch(listOf(twelve),
            "Glenfiddich 12 Year Old"))
    }

    @Test fun inactiveProductMatchedByKoreanAliasCannotBeAddedAsNew() {
        val product = MockCatalogProduct(
            productId = "inactive-deanston", brandId = "brand-deanston",
            displayName = "Deanston 12", isActive = false,
            matchedAlias = "딘스톤 12년")
        assertEquals(product, inactiveOwnerCatalogMatch(listOf(product), "딘스톤 12년"))
        assertEquals(product, inactiveOwnerCatalogMatch(listOf(product), "딘스톤12년"))
        assertNull(manualProductProposal(listOf(product), "딘스톤 12년",
            "위스키", null, null))
        assertNull(inactiveOwnerCatalogMatch(listOf(product), "딘스톤 18년"))
        assertNull(inactiveOwnerCatalogMatch(listOf(product.copy(isActive=true)),
            "딘스톤 12년"))
    }

    @Test fun exactCatalogAliasIsSuggestedWithoutManualBrandInput() {
        val alias = twelve.copy(matchedAlias = "글렌피딕 12년")
        assertEquals(alias, manualProductProposal(
            listOf(alias), "글렌피딕 12년", "위스키", null, null))
    }

    @Test fun customAlcoholCategoryIsShownAsTypedAndEditableWithoutChangingProductId() {
        val beer = MockCatalogProduct(
            productId = "beer-1", brandId = "brewery", displayName = "수제 맥주",
            category = "맥주", catalogMatched = true)
        assertEquals("기타 주류", manualEditorCategory(beer))
        assertEquals("맥주", manualEditorAlcoholKind(beer))
        // A legacy non-whisky catalog row is never offered as a canonical
        // match for a new bar-only beer. Only an owned local menu row can match.
        assertNull(manualProductProposal(
            listOf(beer), "수제 맥주", "기타 주류", null, null))
        assertEquals(beer.copy(catalogMatched = false), manualProductProposal(
            listOf(beer.copy(catalogMatched = false)), "수제 맥주", "기타 주류", null, null))
        assertEquals("맥주", ownerV4Category(beer))
    }

    @Test fun freshSaveMustNeverOfferLegacyBeerOrCocktailAsGlobalProduct() {
        val beer = MockCatalogProduct("beer-1", "beer-brand", "맥주 1", category = "맥주")
        val cocktail = MockCatalogProduct("cocktail-1", "bar", "진토닉", category = "cocktail")
        val approved = twelve.copy(matchedAlias = "글렌피딕 12년")
        assertNull(manualFreshCatalogExactMatch(listOf(beer), "맥주 1", "기타 주류", null))
        assertNull(manualFreshCatalogExactMatch(listOf(beer), "맥주 1", "위스키", null))
        assertNull(manualFreshCatalogExactMatch(listOf(cocktail), "진토닉", "칵테일", null))
        assertEquals(approved, manualFreshCatalogExactMatch(listOf(approved),
            "글렌피딕 12년", "위스키", null))
        assertNull(manualFreshCatalogExactMatch(listOf(approved),
            "글렌피딕 12년", "위스키", approved.productId))
    }

    @Test fun missingBrandConfirmationDoesNotInferEnglishProductId() {
        assertNull(manualProductProposal(listOf(twelve),
            "글렌피딕12년","위스키",null,null))
    }
}
