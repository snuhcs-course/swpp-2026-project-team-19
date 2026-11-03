package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.network.MatchedProductDto
import com.zerotoone.bottlemap.network.SearchBarsResponseDto
import com.zerotoone.bottlemap.network.SearchOptionDto
import com.zerotoone.bottlemap.network.SearchResultDto
import org.junit.Assert.*
import org.junit.Test

/** Regression cases from Galaxy S23: Glenfiddich 12 exact skip + late GPS. */
class CustomerP18SearchStabilityTest {
    private val product=MatchedProductDto(
        productId="p12",displayName="Glenfiddich 12",brandName="Glenfiddich",
        resultCount=1)
    private val item=SearchResultDto(
        barId="bar1",barName="관악 위스키 바",address="서울",
        latitude=37.480,longitude=126.950,
        productId="p12",productDisplayName="Glenfiddich 12",
        menuDisplayName="Glenfiddich 12",
        options=listOf(SearchOptionDto("잔",30,17000,0)),
        menuUpdatedAt="2026-11-01T00:00:00Z"
    )
    private fun search(query:String?,type:String,product:Boolean=true)=
        SearchBarsResponseDto(query,type,if(product)listOf(this.product)else emptyList(),
            if(product)listOf(item)else emptyList(),false)

    @Test fun exactMatchIsStableAndSkipsProductSelection() {
        val exact=search("glenfiddich 12","alias_exact")
        val original=p18OriginalResponse("glenfiddich 12",null,exact,exact)
        assertEquals("alias_exact",original?.matchType)
        assertEquals(1,original?.matchedProducts?.size)
        assertEquals(exact,p18ResolvedResult(null,null,true,original,exact))
    }

    @Test fun staleCandidatesOrProductIdResponseCannotBecomeUnknownQuery() {
        val prior=search("glenfiddich 12","alias_exact")
        val newQuery=search("glenfiddich 15","alias_exact")
        val staleProduct=search(null,"product")
        assertNull(p18OriginalResponse("glenfiddich 15",null,prior,staleProduct))
        assertEquals(newQuery,
            p18OriginalResponse("glenfiddich 15",null,prior,newQuery))
    }

    @Test fun emptyProductIdResponseIsNotMistakenForUnknownQuery() {
        val missingProduct=search(null,"none",false)
        assertEquals(missingProduct,
            p18OriginalResponse(null,"p12",null,missingProduct))
        assertNull(p18ResolvedResult(null,"p12",true,missingProduct,missingProduct))
    }

    @Test fun priceHasFirstPriorityButUnavailableOptionsAreOmitted() {
        assertEquals(listOf(P18Sort.PRICE,P18Sort.DISTANCE,P18Sort.UPDATED),
            p18AvailableSorts(hasLocation=true,allowPrice=true))
        assertEquals(listOf(P18Sort.PRICE,P18Sort.UPDATED),
            p18AvailableSorts(hasLocation=false,allowPrice=true))
        assertEquals(listOf(P18Sort.DISTANCE,P18Sort.UPDATED),
            p18AvailableSorts(hasLocation=true,allowPrice=false))
        assertEquals(listOf(P18Sort.UPDATED),
            p18AvailableSorts(hasLocation=false,allowPrice=false))
    }

    @Test fun aLateGpsFixCanSupplyDistanceWithoutChangingQueryResult() {
        val exact=search("glenfiddich 12","alias_exact")
        assertNull(p18DisplayDistance(item,null))
        val resolved=p18DisplayDistance(item,NearbyCoordinate(37.480,126.950))
        assertEquals(0,resolved)
        assertEquals(exact,p18ResolvedResult(null,null,true,exact,exact))
    }
}
