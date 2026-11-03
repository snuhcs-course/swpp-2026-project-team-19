
package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.network.*
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant
import java.time.ZonedDateTime
import java.time.ZoneId

/** P18 UI decisions: data comes from API, no fabricated server values. */
class CustomerP18PolicyTest {
    @Test fun representativeServingPrefers30MlThenNearestLargerOnTie() {
        val prices=listOf(
            SearchOptionDto("잔",15,11000,1),
            SearchOptionDto("잔",45,26000,2),
            SearchOptionDto("잔",30,17000,3),
            SearchOptionDto("병",null,160000,4))
        assertEquals(30,p18Representative(prices)?.pourMl)
        assertEquals(45,p18Representative(prices.filterNot{it.pourMl==30})?.pourMl)
        assertEquals(160000,p18Representative(prices.takeLast(1))?.priceKrw)
    }

    @Test fun discountOnlyAppliesInsideExactInstantWindow() {
        val discount=BarMenuDiscountDto(14000,
            "2026-11-01T09:00:00Z","2026-11-15T15:00:00Z")
        assertEquals(17000,p18EffectivePrice(17000,discount,
            Instant.parse("2026-11-01T08:59:59Z")))
        assertEquals(14000,p18EffectivePrice(17000,discount,
            Instant.parse("2026-11-01T09:00:00Z")))
        assertEquals(14000,p18EffectivePrice(17000,discount,
            Instant.parse("2026-11-15T14:59:59Z")))
        assertEquals(17000,p18EffectivePrice(17000,discount,
            Instant.parse("2026-11-15T15:00:00Z")))
        assertEquals(17000,p18EffectivePrice(17000,null,
            Instant.parse("2026-11-10T00:00:00Z")))
    }

    @Test fun sortedPriceUsesRepresentative30MlRatherThanMinimum15Ml() {
        fun row(id:String, low:Int, serving30:Int)=SearchResultDto(
            barId=id,barName=id,address="test",latitude=37.0,longitude=127.0,
            productId="product",productDisplayName="product",menuDisplayName="menu",
            options=listOf(SearchOptionDto("잔",15,low,1),
                SearchOptionDto("잔",30,serving30,2)),
            menuUpdatedAt="2026-10-04T09:00:00Z")
        val a=row("a",1000,25000)
        val b=row("b",9000,15000)
        assertEquals(listOf("b","a"),
            p18Sorted(listOf(a,b),P18Sort.PRICE,false).map{it.barId})
    }

    @Test fun productIdSearchResponseAllowsNullQuery() {
        val payload="""{"query":null,"matchType":"product",
            "matchedProducts":[],"items":[],"truncated":false}"""
        val result=ApiClient.moshi.adapter(SearchBarsResponseDto::class.java)
            .fromJson(payload)
        assertNotNull(result)
        assertNull(result?.query)
        assertEquals("product",result?.matchType)
    }

    @Test fun overnightHoursCarryAndClosedTodayOverridesThem() {
        val hours=listOf(
            BarWeeklyHoursDto(5,false,"18:00","02:00"),
            BarWeeklyHoursDto(6,true),
        )
        val saturday=ZonedDateTime.of(2026,11,7,1,0,0,0,
            ZoneId.of("Asia/Seoul"))
        assertEquals("영업 중",p18BusinessStatus(hours,null,saturday).text)
        assertEquals("익일 02:00 종료",
            p18BusinessStatus(hours,null,ZonedDateTime.of(
                2026,11,6,19,0,0,0,ZoneId.of("Asia/Seoul"))).next)
        val closed=BarOperatingExceptionDto("closed_today",
            "2026-11-07","2026-11-07",note="정비 중")
        val state=p18BusinessStatus(hours,closed,saturday)
        assertEquals("임시 휴무",state.text)
        assertEquals("정비 중",state.note)
    }

    @Test fun unknownHoursAreNotReportedAsClosed() {
        val time=ZonedDateTime.of(2026,11,3,14,0,0,0,
            ZoneId.of("Asia/Seoul"))
        assertEquals("영업시간 정보 없음",p18BusinessStatus(emptyList(),null,time).text)
    }
}
