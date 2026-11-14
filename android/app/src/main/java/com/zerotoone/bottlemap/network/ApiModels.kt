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

// API spec §3.17: display-only popular whisky cards (not an OCR or catalog guess).
data class PopularProductDto(
    val productId: String,
    val displayName: String,
    val brandName: String,
    val ageYears: Int? = null,
    val editionName: String? = null,
    val barCount: Int,
)
data class PopularProductsResponseDto(val items: List<PopularProductDto> = emptyList())

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
    val discount: BarMenuDiscountDto? = null,
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
    val coverThumbnailUrl: String? = null,
)

data class SearchBarsResponseDto(
    val query: String?,
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
    val discount: BarMenuDiscountDto? = null,
)
data class BarMenuDiscountDto(
    val discountedPriceKrw: Int,
    val startsAt: String,
    val endsAt: String,
)
data class BarPhotoDto(
    val photoId: String, val imageUrl: String, val thumbnailUrl: String,
)
data class BarWeeklyHoursDto(
    val dayOfWeek: Int, val closed: Boolean,
    val openTime: String? = null, val closeTime: String? = null,
)
data class BarOperatingExceptionDto(
    val kind: String, val startDate: String, val endDate: String,
    val openTime: String? = null, val closeTime: String? = null,
    val note: String? = null,
)

data class BarMenuItemDto(
    val menuBoardEntryId: String,
    val barMenuItemId: String,
    val productId: String?,
    // Published menu label, NOT the canonical catalog product name.
    val displayName: String,
    val sortOrder: Int,
    val options: List<BarMenuOptionDto>,
    val productName: String? = null,
    val brandId: String? = null,
    val brandName: String? = null,
    // No canonical category exists until an operator links a whisky.
    val category: String? = null,
    val kind: String = "whisky",
    val soldOut: Boolean = false,
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
    val description: String? = null,
    val tags: List<String> = emptyList(),
    val weeklyHours: List<BarWeeklyHoursDto> = emptyList(),
    val operatingException: BarOperatingExceptionDto? = null,
    val photos: List<BarPhotoDto> = emptyList(),
    val menuVersion: Int? = null,
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
    val coverThumbnailUrl: String? = null,
)

data class MapBarsResponseDto(
    val items: List<MapBarItemDto>,
)
