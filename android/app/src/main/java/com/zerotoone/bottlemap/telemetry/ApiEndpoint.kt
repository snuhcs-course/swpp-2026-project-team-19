package com.zerotoone.bottlemap.telemetry

/** Fixed API contract templates. Unknown paths and every query are discarded. */
enum class ApiEndpoint(val template: String) {
    API_ME("/api/me"),
    API_BARS_ID_MENU("/api/bars/{id}/menu"),
    API_SEARCH_BAR_NAMES("/api/search/bar-names"),
    API_SEARCH_MAP_BARS("/api/search/map-bars"),
    API_SEARCH_ALL_BARS("/api/search/all-bars"),
    API_SEARCH_NEARBY_BARS("/api/search/nearby-bars"),
    API_SEARCH_POPULAR_PRODUCTS("/api/search/popular-products"),
    API_SEARCH_BARS("/api/search/bars"),
    API_AUTH_TEMP_LOGIN("/api/auth/temp-login"),
    API_CATALOG_BRANDS("/api/catalog/brands"),
    API_CATALOG_PRODUCTS("/api/catalog/products"),
    API_ME_BARS("/api/me/bars"),
    API_ME_OWNER_APPLICATIONS("/api/me/owner-applications"),
    API_BARS_ID("/api/bars/{id}"),
    API_BARS_ID_PHOTOS("/api/bars/{id}/photos"),
    API_BARS_ID_MENU_ITEMS("/api/bars/{id}/menu/items"),
    API_BARS_ID_MENU_RESET("/api/bars/{id}/menu/reset"),
    API_BARS_ID_MENU_CONFIRM("/api/bars/{id}/menu/confirm"),
    API_OWNER_APPLICATIONS_BUSINESS_VERIFICATION("/api/owner-applications/business-verification"),
    API_OWNER_APPLICATIONS("/api/owner-applications"),
    API_OWNER_APPLICATIONS_BUSINESS_CERTIFICATE_OCR("/api/owner-applications/business-certificate-ocr"),
    API_OWNER_APPLICATIONS_ID_CANCEL("/api/owner-applications/{id}/cancel"),
    API_BARS("/api/bars"),
    API_BARS_ID_MENU_IMPORTS("/api/bars/{id}/menu-imports"),
    API_MENU_IMPORTS_ID_CANCEL("/api/menu-imports/{id}/cancel"),
    API_MENU_IMPORTS_ID("/api/menu-imports/{id}"),
    API_MENU_IMPORTS_ID_REVIEW_AND_APPLY("/api/menu-imports/{id}/review-and-apply"),
    API_BARS_ID_PHOTOS_ID("/api/bars/{id}/photos/{id}"),
    API_BARS_ID_PHOTOS_ORDER("/api/bars/{id}/photos/order"),
    API_BARS_ID_OPERATING_EXCEPTION("/api/bars/{id}/operating-exception"),
    API_BARS_ID_MENU_ITEMS_ID("/api/bars/{id}/menu/items/{id}"),
    API_BARS_ID_MENU_ITEMS_ID_SOLD_OUT("/api/bars/{id}/menu/items/{id}/sold-out"),
    API_OWNER_APPLICATIONS_ID_COVER_PHOTO("/api/owner-applications/{id}/cover-photo"),
    API_OWNER_APPLICATIONS_ID_MENU_PHOTOS("/api/owner-applications/{id}/menu-photos"),
    API_MENU_IMPORTS_ID_REVIEW_DRAFT("/api/menu-imports/{id}/review-draft"),
    UNKNOWN("unknown");
    companion object {
        fun fromPath(path: String): ApiEndpoint {
            val clean = path.substringBefore('?')
            // Prefer /photos/order over the otherwise matching /photos/{id}.
            return entries.sortedBy { endpoint -> endpoint.template.count { it == '{' } }.firstOrNull { endpoint ->
                endpoint != UNKNOWN && endpoint.template.split('/').let { parts ->
                    val actual = clean.split('/')
                    parts.size == actual.size && parts.zip(actual).all { (expected, value) ->
                        if (expected.startsWith("{")) value.isNotEmpty() else expected == value
                    }
                }
            } ?: UNKNOWN
        }
    }
}
