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

data class TemporaryLoginResponseDto(
    val accessToken: String,
    val tokenType: String,
    val expiresIn: Int,
)

data class ActiveMenuImportDto(
    val menuImportId: String,
    val status: String,
)

data class BarDto(
    val barId: String,
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
    val phone: String? = null,
    val status: String,
    val activeMenuImport: ActiveMenuImportDto? = null,
)

data class BarListResponseDto(
    val items: List<BarDto> = emptyList(),
    val nextCursor: String? = null,
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

data class MenuImportAcceptedDto(
    val menuImportId: String,
    val status: String,
    val imageCount: Int,
    val statusUrl: String,
    val pollAfterMs: Long,
)

data class ImportProgressDto(
    val totalImages: Int,
    val completedImages: Int,
    val failedImages: Int,
)

data class ImportFailureDto(
    val code: String,
    val message: String,
)

data class ReviewOptionDto(
    val extractedOptionId: String,
    val optionOrder: Int,
    val extractedOptionLabel: String? = null,
    val extractedPourMl: Int? = null,
    val extractedPriceKrw: Int? = null,
)

data class ReviewCandidateDto(
    val productId: String,
    val candidateRank: Int,
    val displayName: String,
    val brandId: String,
    val brandName: String,
    val category: String,
    val ageYears: Int? = null,
    val editionName: String? = null,
    val abv: Double? = null,
    val matchMethod: String,
    val score: Double? = null,
    val evidence: Map<String, Any?> = emptyMap(),
)

data class NewProductDraftDto(
    val brandText: String? = null,
    val category: String,
    val displayName: String? = null,
    val ageYears: Int? = null,
    val editionName: String? = null,
    val abv: Double? = null,
)

data class ReviewItemDto(
    val extractedItemId: String,
    val itemOrder: Int,
    val rawText: String,
    val extractedLineType: String,
    val correctedLineType: String? = null,
    val effectiveLineType: String,
    val initialResolutionStatus: String? = null,
    val extractedProductName: String? = null,
    val extractedBrandName: String? = null,
    val extractedAgeYears: Int? = null,
    val extractedEditionName: String? = null,
    val extractedAbv: Double? = null,
    val extractionConfidence: Double? = null,
    val proposedProductId: String? = null,
    val options: List<ReviewOptionDto> = emptyList(),
    val candidates: List<ReviewCandidateDto> = emptyList(),
    val newProductDraft: NewProductDraftDto? = null,
)

data class ReviewImageDto(
    val imageId: String,
    val imageOrder: Int,
    val imageUrl: String,
    val imageUrlExpiresAt: String? = null,
    val items: List<ReviewItemDto> = emptyList(),
)

data class ChangeAfterDto(
    val productId: String? = null,
    val displayName: String? = null,
)

data class ProposedChangeDto(
    val changeId: String,
    val changeType: String,
    val barMenuItemId: String? = null,
    val extractedItemId: String? = null,
    val after: ChangeAfterDto? = null,
    val summary: String,
    val decision: String,
)

data class MenuImportStatusDto(
    val menuImportId: String,
    val barId: String? = null,
    val mode: String? = null,
    val status: String,
    val reviewVersion: Int? = null,
    val progress: ImportProgressDto? = null,
    val pollAfterMs: Long? = null,
    val failure: ImportFailureDto? = null,
    val images: List<ReviewImageDto> = emptyList(),
    val proposedChanges: List<ProposedChangeDto> = emptyList(),
    val appliedAt: String? = null,
    val menuBoardId: String? = null,
)

data class ChangeDecisionDto(
    val changeId: String,
    val decision: String,
)

data class ReviewAndApplyRequestDto(
    val reviewVersion: Int,
    val itemDecisions: List<Map<String, Any?>>,
    val changeDecisions: List<ChangeDecisionDto>,
)

data class ReviewResultDto(
    val added: Int,
    val updated: Int,
    val removed: Int,
    val ignored: Int,
    val createdBrands: Int,
    val createdProducts: Int,
)

data class ReviewAppliedResponseDto(
    val menuImportId: String,
    val status: String,
    val reviewVersion: Int,
    val appliedAt: String,
    val menuBoardId: String,
    val result: ReviewResultDto,
)

data class MenuImportListItemDto(
    val menuImportId: String,
    val mode: String,
    val status: String,
    val imageCount: Int,
    val reviewVersion: Int,
    val ownerNote: String? = null,
    val createdAt: String,
    val completedAt: String? = null,
)

data class MenuImportListResponseDto(
    val items: List<MenuImportListItemDto> = emptyList(),
    val nextCursor: String? = null,
)
