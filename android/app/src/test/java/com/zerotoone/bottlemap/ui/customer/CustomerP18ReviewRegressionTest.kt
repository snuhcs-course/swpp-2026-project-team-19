package com.zerotoone.bottlemap.ui.customer

import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.FieldErrorDto
import com.zerotoone.bottlemap.network.BarMenuDiscountDto
import com.zerotoone.bottlemap.network.BarOperatingExceptionDto
import com.zerotoone.bottlemap.network.BarWeeklyHoursDto
import com.zerotoone.bottlemap.network.SearchOptionDto
import com.zerotoone.bottlemap.network.SearchResultDto
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime

/**
 * PR #109 Codex correctness regressions; no change to customer UI or ordinary
 * search/detail navigation. Times are explicit to avoid flaky clock tests.
 */
class CustomerP18ReviewRegressionTest {
    private val kst=ZoneId.of("Asia/Seoul")

    @Test fun backendNotSearchableQueryUsesExistingCorrectionState() {
        val invalid=BottleMapApiException(
            httpStatus=422,code="VALIDATION_FAILED",message="input error",
            fieldErrors=listOf(FieldErrorDto("query","NOT_SEARCHABLE","invalid")))
        assertEquals("NOT_SEARCHABLE",p18QueryValidationCode(invalid))
        val otherField=BottleMapApiException(
            httpStatus=422,code="VALIDATION_FAILED",message="other error",
            fieldErrors=listOf(FieldErrorDto("lat","GREATER_THAN_EQUAL","invalid")))
        assertNull(p18QueryValidationCode(otherField))
        assertNull(p18QueryValidationCode(BottleMapApiException(
            code="NETWORK_ERROR",message="offline")))
    }

    @Test fun yesterdayClosureNoteMustNotPersistIntoNormalOpenHours() {
        val hours=listOf(BarWeeklyHoursDto(2,false,"12:00","22:00"))
        val yesterday=BarOperatingExceptionDto(
            "closed_today","2026-11-02","2026-11-02",note="정비 중")
        val today=ZonedDateTime.of(2026,11,3,14,0,0,0,kst)
        val status=p18BusinessStatus(hours,yesterday,today)
        assertEquals("영업 중",status.text)
        assertNull(status.note)
    }

    @Test fun overnightCustomHoursNoteOnlyCarriesUntilRealCloseTime() {
        val exception=BarOperatingExceptionDto(
            "custom_hours","2026-11-02","2026-11-02",
            "19:00","02:00",note="이벤트 연장 영업")
        val hours=listOf(BarWeeklyHoursDto(2,false,"12:00","22:00"))
        val overnight=p18BusinessStatus(hours,exception,
            ZonedDateTime.of(2026,11,3,1,0,0,0,kst))
        assertEquals("영업 중",overnight.text)
        assertEquals("이벤트 연장 영업",overnight.note)
        val later=p18BusinessStatus(hours,exception,
            ZonedDateTime.of(2026,11,3,14,0,0,0,kst))
        assertEquals("영업 중",later.text)
        assertNull(later.note)
    }

    private fun bar(id:String,originalPrice:Int,discount:BarMenuDiscountDto?) =
        SearchResultDto(
            barId=id,barName=id,address="서울",latitude=37.48,longitude=126.95,
            productId="p12",productDisplayName="Glenfiddich 12",
            menuDisplayName="Glenfiddich 12",
            options=listOf(SearchOptionDto("잔",30,originalPrice,0,discount)),
            menuUpdatedAt="2026-11-01T00:00:00Z",
        )

    @Test fun priceSortUsesSameDiscountInstantAsDisplayedCardAndMapMarker() {
        val discount=BarMenuDiscountDto(
            8000,"2026-11-03T09:00:00Z","2026-11-03T10:00:00Z")
        val rows=listOf(bar("discounted",15000,discount),bar("normal",10000,null))
        assertEquals("discounted",p18Sorted(rows,P18Sort.PRICE,false,
            Instant.parse("2026-11-03T09:59:59Z")).first().barId)
        assertEquals("normal",p18Sorted(rows,P18Sort.PRICE,false,
            Instant.parse("2026-11-03T10:00:00Z")).first().barId)
    }
}
