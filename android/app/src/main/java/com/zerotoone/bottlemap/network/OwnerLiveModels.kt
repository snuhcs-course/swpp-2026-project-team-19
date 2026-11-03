package com.zerotoone.bottlemap.network

/** DTOs from the existing production backend; owner identity comes from /api/me/bars. */
data class OwnedMenuImportDto(val menuImportId: String, val status: String)
data class OwnedMenuStateDto(
    val menuBoardId: String,
    val menuVersion: Int,
    val publishedAt: String,
    val confirmedAt: String? = null,
)
data class OwnedBarDto(
    val barId: String,
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    val phone: String? = null,
    val status: String,
    val description: String? = null,
    val defaultPourMl: Int? = null,
    val tags: List<String> = emptyList(),
    val weeklyHours: List<BarWeeklyHoursDto> = emptyList(),
    val operatingException: BarOperatingExceptionDto? = null,
    val photos: List<BarPhotoDto> = emptyList(),
    val currentMenu: OwnedMenuStateDto? = null,
    val activeMenuImport: OwnedMenuImportDto? = null,
)
data class MyOwnedBarsDto(val items: List<OwnedBarDto> = emptyList())
data class OwnerApplicationBarDto(
    val barId: String, val name: String, val address: String,
)
data class OwnerApplicationProposedBarDto(
    val name: String, val address: String, val phone: String? = null,
)
data class OwnerBusinessVerificationDto(val result: String)

data class OwnerApplicationCoverPhotoDto(
    val imageUrl: String,
    val thumbnailUrl: String,
    val imageUrlExpiresAt: String? = null,
)

data class OwnerApplicationDto(
    val applicationId: String,
    val applicationType: String,
    val status: String,
    val bar: OwnerApplicationBarDto? = null,
    val proposedBar: OwnerApplicationProposedBarDto? = null,
    val rejectionReason: String? = null,
    val createdAt: String,
    val reviewedAt: String? = null,
    val businessRegistrationNumber: String? = null,
    val representativeName: String? = null,
    val openingDate: String? = null,
    val contactPhone: String? = null,
    val applicantNote: String? = null,
    val coverPhoto: OwnerApplicationCoverPhotoDto? = null,
)
data class MyOwnerApplicationsDto(val items: List<OwnerApplicationDto> = emptyList())

/** OCR prefill only; the backend verifies the business fields at application submission. */
data class OwnerCertificateOcrDto(
    val businessRegistrationNumber: String? = null,
    val representativeName: String? = null,
    val openingDate: String? = null,
    val businessName: String? = null,
    val address: String? = null,
)

data class OwnerCatalogProductDto(
    val productId: String,
    val displayName: String,
    val brandId: String,
    val brandName: String,
    val category: String,
    val ageYears: Int? = null,
    val editionName: String? = null,
    val abv: Double? = null,
    val isActive: Boolean = true,
)
data class OwnerCatalogProductsDto(val items: List<OwnerCatalogProductDto> = emptyList())

data class OwnedPhotoListDto(val photos: List<BarPhotoDto> = emptyList())
