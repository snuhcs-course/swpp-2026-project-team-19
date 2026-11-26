package com.zerotoone.bottlemap.telemetry

import org.junit.Assert.*
import org.junit.Test

class TelemetryTest {
    @Test fun consentAndBuildPermissionBothGateEventsAndScreen() {
        val fake = FakeTelemetry()
        val gate = ConsentTelemetry(fake, true)
        gate.setScreen(ScreenRoute.DETAIL)
        gate.log(TelemetryEvent.ReportProblemOpened)
        assertTrue(fake.events.isEmpty()); assertTrue(fake.screens.isEmpty())
        gate.setEnabled(true)
        gate.log(TelemetryEvent.ReportProblemOpened)
        assertEquals(listOf(TelemetryEvent.ReportProblemOpened), fake.events)
        assertEquals(listOf(ScreenRoute.DETAIL), fake.screens)
        gate.setEnabled(false)
        gate.log(TelemetryEvent.ReportProblemOpened)
        assertEquals(1, fake.events.size)
        val disabledBuild = ConsentTelemetry(fake, false)
        disabledBuild.setEnabled(true)
        disabledBuild.log(TelemetryEvent.ReportProblemOpened)
        assertEquals(1, fake.events.size)
        assertEquals(listOf(true, false, false), fake.enabledChanges)
    }
    @Test fun endpointAllowlistDropsEveryArgumentAndQueryEvenForNonUuidInput() {
        assertEquals(ApiEndpoint.API_BARS_ID_MENU,
            ApiEndpoint.fromPath("/api/bars/private@example.invalid/menu?lat=37&query=secret"))
        assertEquals("/api/bars/{id}/menu", ApiEndpoint.API_BARS_ID_MENU.template)
        assertEquals(ApiEndpoint.API_MENU_IMPORTS_ID_REVIEW_DRAFT,
            ApiEndpoint.fromPath("/api/menu-imports/123/review-draft"))
        assertEquals(ApiEndpoint.API_BARS_ID_PHOTOS_ORDER, ApiEndpoint.fromPath("/api/bars/123/photos/order"))
        assertEquals(ApiEndpoint.UNKNOWN, ApiEndpoint.fromPath("/private@example.invalid"))
        assertEquals(ApiEndpoint.UNKNOWN, ApiEndpoint.fromPath("/api/bars//menu"))
        assertEquals(ErrorCode.UNKNOWN, ErrorCode.from("private@example.invalid"))
        assertEquals(HttpStatus.NO_RESPONSE, HttpStatus.from(0))
        assertEquals(HttpStatus.OTHER, HttpStatus.from(418))
        assertEquals(ScreenRoute.DETAIL, ScreenRoute.fromTemplate("customer/bar/{barId}"))
        assertFalse(ScreenRoute.fromTemplate("untrusted/private@example.invalid").template.contains("@"))
    }
    @Test fun searchTimingBoundariesAndOtherSourcesHaveNoSearchDuration() {
        assertEquals(SearchTime.UNDER_30, SearchTime.fromMillis(29_999))
        assertEquals(SearchTime.FROM_30_TO_60, SearchTime.fromMillis(30_000))
        assertEquals(SearchTime.FROM_60_TO_180, SearchTime.fromMillis(60_000))
        assertEquals(SearchTime.FROM_180, SearchTime.fromMillis(180_000))
        var now = 100L
        val journey = DiscoveryJourney { now }
        journey.searched(); now += 60_000
        assertEquals(TelemetryEvent.BarDetailOpened(DetailSource.SEARCH, SearchTime.FROM_60_TO_180), journey.detailOpened())
        journey.fromMap(); assertNull(journey.detailOpened().secondsSinceSearch)
        journey.searched(popular=true); assertNull(journey.detailOpened().secondsSinceSearch)
        assertNull(DiscoveryJourney { now }.detailOpened().secondsSinceSearch)
    }
    @Test fun reviewTimeAndCountBucketsHonorBoundaries() {
        assertEquals(listOf(ReviewTime.UNDER_3, ReviewTime.FROM_3_TO_10, ReviewTime.FROM_10_TO_30, ReviewTime.FROM_30),
            listOf(179_999L,180_000L,600_000L,1_800_000L).map(ReviewTime::fromMillis))
        assertEquals(listOf(PhotoCount.ONE,PhotoCount.TWO_TO_FIVE,PhotoCount.TWO_TO_FIVE,PhotoCount.SIX_PLUS),
            listOf(1,2,5,6).map(PhotoCount::from))
        assertEquals(listOf(CheckCount.ZERO,CheckCount.ONE_TO_FIVE,CheckCount.ONE_TO_FIVE,CheckCount.SIX_PLUS),
            listOf(0,1,5,6).map(CheckCount::from))
    }
    @Test fun payloadHasOnlyDocumentedKeysAndNoDurationsForNonSearchDetails() {
        assertEquals(mapOf("kind" to "brand", "has_results" to "true"),
            TelemetryEvent.SearchCompleted(SearchKind.BRAND, true).payload().parameters)
        assertEquals(mapOf("source" to "map"),
            TelemetryEvent.BarDetailOpened(DetailSource.MAP, SearchTime.UNDER_30).payload().parameters)
        assertEquals(mapOf("needed_check" to "1-5", "minutes" to "3-10"),
            TelemetryEvent.MenuPublished(CheckCount.ONE_TO_FIVE, ReviewTime.FROM_3_TO_10).payload().parameters)
        val error = TelemetryEvent.ApiError(ApiEndpoint.API_BARS_ID_MENU, HttpStatus.CONFLICT, ErrorCode.MENU_OUTDATED).payload()
        assertEquals("api_error", error.name)
        assertEquals(setOf("endpoint","http_status","code"), error.parameters.keys)
        assertEquals(409L, error.parameters["http_status"])
    }
    @Test fun terminalExtractionErrorsRetainTheirContractCode() {
        assertEquals(ErrorCode.IMAGE_EXTRACTION_FAILED, ErrorCode.from("IMAGE_EXTRACTION_FAILED"))
        assertEquals(ErrorCode.PROCESSING_FAILED, ErrorCode.from("PROCESSING_FAILED"))
        assertEquals(ErrorCode.UNKNOWN, ErrorCode.from("private server message"))
    }
    @Test fun noopAcceptsEveryOperationWithoutConfiguration() {
        NoOpTelemetry.setEnabled(true)
        NoOpTelemetry.setScreen(ScreenRoute.ACCOUNT)
        NoOpTelemetry.log(TelemetryEvent.ReportProblemOpened)
        NoOpTelemetry.setEnabled(false)
    }
}
