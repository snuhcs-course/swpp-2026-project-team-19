package com.zerotoone.bottlemap.telemetry

/** Mapping is internal: callers cannot provide an arbitrary name, key or value. */
internal data class TelemetryPayload(val name: String, val parameters: Map<String, Any> = emptyMap())
internal fun TelemetryEvent.payload(): TelemetryPayload = when (this) {
    is TelemetryEvent.SearchCompleted -> TelemetryPayload("search_completed", mapOf("kind" to kind.name.lowercase(), "has_results" to hasResults.toString()))
    is TelemetryEvent.BarDetailOpened -> TelemetryPayload("bar_detail_opened", buildMap {
        put("source", source.name.lowercase())
        if (source == DetailSource.SEARCH && secondsSinceSearch != null) put("seconds_since_search", when (secondsSinceSearch) {
            SearchTime.UNDER_30 -> "<30"; SearchTime.FROM_30_TO_60 -> "30-60"; SearchTime.FROM_60_TO_180 -> "60-180"; SearchTime.FROM_180 -> "180+"
        })
    })
    is TelemetryEvent.MenuImportStarted -> TelemetryPayload("menu_import_started", mapOf("source" to source.name.lowercase(), "photos" to when (photos) {
        PhotoCount.ONE -> "1"; PhotoCount.TWO_TO_FIVE -> "2-5"; PhotoCount.SIX_PLUS -> "6+"
    }))
    is TelemetryEvent.MenuImportFailed -> TelemetryPayload("menu_import_failed", mapOf("stage" to stage.name.lowercase(), "error_code" to errorCode.name))
    TelemetryEvent.MenuReviewOpened -> TelemetryPayload("menu_review_opened")
    is TelemetryEvent.MenuPublished -> TelemetryPayload("menu_published", mapOf("needed_check" to when (neededCheck) {
        CheckCount.ZERO -> "0"; CheckCount.ONE_TO_FIVE -> "1-5"; CheckCount.SIX_PLUS -> "6+"
    }, "minutes" to when (minutes) {
        ReviewTime.UNDER_3 -> "<3"; ReviewTime.FROM_3_TO_10 -> "3-10"; ReviewTime.FROM_10_TO_30 -> "10-30"; ReviewTime.FROM_30 -> "30+"
    }))
    is TelemetryEvent.MenuPublishFailed -> TelemetryPayload("menu_publish_failed", mapOf("error_code" to errorCode.name))
    is TelemetryEvent.OwnerApplicationStarted -> TelemetryPayload("owner_application_started", mapOf("type" to type.name.lowercase()))
    is TelemetryEvent.OwnerApplicationSubmitted -> TelemetryPayload("owner_application_submitted", mapOf("type" to type.name.lowercase()))
    is TelemetryEvent.OwnerApplicationFailed -> TelemetryPayload("owner_application_failed", mapOf("error_code" to errorCode.name))
    is TelemetryEvent.NearbyOpened -> TelemetryPayload("nearby_opened", mapOf("permission" to permission.name.lowercase()))
    is TelemetryEvent.SignInResult -> TelemetryPayload("sign_in_result", mapOf("entry" to entry.name.lowercase(), "result" to result.name.lowercase()))
    TelemetryEvent.ReportProblemOpened -> TelemetryPayload("report_problem_opened")
    is TelemetryEvent.ApiError -> TelemetryPayload("api_error", mapOf("endpoint" to endpoint.template, "http_status" to httpStatus.value, "code" to code.name))
}
