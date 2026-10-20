// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.network

data class ApiErrorEnvelopeDto(
    val error: ApiErrorBodyDto,
)

data class ApiErrorBodyDto(
    val code: String,
    val message: String,
    val details: Map<String, Any?>? = null,
    val fieldErrors: List<FieldErrorDto> = emptyList(),
)

data class FieldErrorDto(
    val path: String,
    val code: String,
    val message: String,
)

data class CurrentUserDto(
    val userId: String,
    val email: String?,
    val displayName: String?,
    val userType: String,
    val updatedAt: String,
)

// Backend A9 PR #43, API spec 3.12. Server distance in rounded integer meters.
data class NearbyBarItemDto(
    val barId: String,
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    val distanceMeters: Int,
    val menuUpdatedAt: String?,
)

data class NearbyBarsResponseDto(
    val items: List<NearbyBarItemDto>,
)

data class MatchedProductDto(
    val productId: String,
    val displayName: String,
    val brandName: String,
    val ageYears: Int? = null,
    val editionName: String? = null,
    val resultCount: Int,
)

data class SearchOptionDto(
    val optionLabel: String? = null,
    val pourMl: Int? = null,
    val priceKrw: Int,
    val sortOrder: Int,
)

data class SearchResultDto(
    val barId: String,
    val barName: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    val distanceMeters: Int? = null,
    val productId: String,
    val productDisplayName: String,
    val menuDisplayName: String,
    val options: List<SearchOptionDto> = emptyList(),
    val menuUpdatedAt: String,
)

data class SearchBarsResponseDto(
    val query: String,
    val matchType: String,
    val matchedProducts: List<MatchedProductDto> = emptyList(),
    val items: List<SearchResultDto> = emptyList(),
    val truncated: Boolean,
)

// P24 - GET /api/bars/{barId}/menu (API spec section 3.9).
// These DTO names and nullabilities match the current backend Pydantic schema.
data class BarMenuOptionDto(
    val menuEntryOptionId: String,
    val optionLabel: String?,
    val pourMl: Int?,
    val priceKrw: Int,
    val sortOrder: Int,
)

data class BarMenuItemDto(
    val menuBoardEntryId: String,
    val barMenuItemId: String,
    val productId: String,
    // Published menu label, NOT the canonical catalog product name.
    val displayName: String,
    val sortOrder: Int,
    val options: List<BarMenuOptionDto>,
)

data class BarMenuResponseDto(
    val barId: String,
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    val phone: String?,
    val menuBoardId: String?,
    val publishedAt: String?,
    val items: List<BarMenuItemDto>,
)

// Backend PR #54: GET /api/search/bar-names (public).
data class BarNameItemDto(
    val barId: String,
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    val hasOwner: Boolean,
)

data class BarNamesResponseDto(
    val items: List<BarNameItemDto>,
    val truncated: Boolean,
)

// Backend PR #54: GET /api/search/map-bars (no distanceMeters).
data class MapBarItemDto(
    val barId: String,
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    val menuUpdatedAt: String?,
)

data class MapBarsResponseDto(
    val items: List<MapBarItemDto>,
)
