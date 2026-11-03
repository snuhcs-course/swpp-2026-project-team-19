package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BarDto
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.OwnerEndpoint
import com.zerotoone.bottlemap.network.MenuImportAcceptedDto
import com.zerotoone.bottlemap.network.MenuImportStatusDto
import com.zerotoone.bottlemap.network.ReviewAndApplyRequestDto
import com.zerotoone.bottlemap.network.ReviewAppliedResponseDto
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

class OwnerRepository {
    /**
     * All production owner endpoints use the exact Supabase session shared with /api/me.
     * TEMP_AUTH_ENABLED is disabled on the deployed server.
     */
    private suspend fun <T> withOwnerAuth(block: suspend (String) -> T): T {
        val gateway = AppAuth.gateway
        val first = gateway.currentAccessTokenOrNull()
            ?: throw BottleMapApiException(code = "UNAUTHENTICATED", message = "로그인이 필요합니다.")
        try {
            return ApiClient.call { block("Bearer $first") }
        } catch (error: BottleMapApiException) {
            if (error.code != "UNAUTHENTICATED") throw error
            val refreshed = gateway.refreshAccessTokenAfter401(first)
                ?: throw BottleMapApiException(
                    code = "NETWORK_ERROR",
                    message = "로그인 세션을 갱신하지 못했어요. 연결을 확인해 주세요.",
                )
            return ApiClient.call { block("Bearer $refreshed") }
        }
    }

    suspend fun searchCatalogProducts(query: String):
        List<com.zerotoone.bottlemap.network.OwnerCatalogProductDto> =
        withOwnerAuth { OwnerEndpoint.api.searchOwnerCatalogProducts(it, query).items }

    suspend fun getOwnedBars(): List<com.zerotoone.bottlemap.network.OwnedBarDto> =
        withOwnerAuth { authorization ->
            OwnerEndpoint.api.getMyBars(authorization).items
        }

    suspend fun getMyApplications(): List<com.zerotoone.bottlemap.network.OwnerApplicationDto> =
        withOwnerAuth { authorization ->
            OwnerEndpoint.api.getMyOwnerApplications(authorization).items
        }

    suspend fun getBars(): List<BarDto> = getOwnedBars().map { bar ->
        BarDto(
            barId = bar.barId, name = bar.name, address = bar.address,
            latitude = bar.latitude, longitude = bar.longitude,
            phone = bar.phone, status = bar.status,
            activeMenuImport = bar.activeMenuImport?.let {
                com.zerotoone.bottlemap.network.ActiveMenuImportDto(it.menuImportId, it.status)
            },
        )
    }

    suspend fun addBarPhoto(barId: String, prepared: PreparedMenuImage):
        com.zerotoone.bottlemap.network.OwnedPhotoListDto =
        withOwnerAuth { token ->
            OwnerEndpoint.api.addOwnedBarPhoto(token, barId,
                MultipartBody.Part.createFormData("image", prepared.filename,
                    prepared.bytes.toRequestBody(prepared.mimeType.toMediaType())))
        }

    suspend fun deleteBarPhoto(barId: String, photoId: String):
        com.zerotoone.bottlemap.network.OwnedPhotoListDto =
        withOwnerAuth { OwnerEndpoint.api.deleteOwnedBarPhoto(it, barId, photoId) }

    suspend fun reorderBarPhotos(barId: String, ids: List<String>):
        com.zerotoone.bottlemap.network.OwnedPhotoListDto =
        withOwnerAuth { OwnerEndpoint.api.reorderOwnedBarPhotos(it, barId, mapOf("photoIds" to ids)) }

    suspend fun setOperatingException(barId: String, body: Map<String, Any?>):
        com.zerotoone.bottlemap.network.OwnedBarDto =
        withOwnerAuth { OwnerEndpoint.api.setOperatingException(it, barId, body) }

    suspend fun removeOperatingException(barId: String):
        com.zerotoone.bottlemap.network.OwnedBarDto =
        withOwnerAuth { OwnerEndpoint.api.removeOperatingException(it, barId) }

    suspend fun getOwnedMenu(barId: String): com.zerotoone.bottlemap.network.BarMenuResponseDto =
        withOwnerAuth { OwnerEndpoint.api.getOwnedMenu(it, barId) }

    suspend fun updateBar(barId: String, fields: Map<String, Any?>):
        com.zerotoone.bottlemap.network.OwnedBarDto =
        withOwnerAuth { OwnerEndpoint.api.updateOwnedBar(it, barId, fields) }

    suspend fun addMenuItem(barId: String, body: Map<String, Any?>):
        com.zerotoone.bottlemap.network.BarMenuResponseDto =
        withOwnerAuth { OwnerEndpoint.api.addOwnedMenuItem(it, barId, body) }

    suspend fun updateMenuItem(barId: String, itemId: String, body: Map<String, Any?>):
        com.zerotoone.bottlemap.network.BarMenuResponseDto =
        withOwnerAuth { OwnerEndpoint.api.updateOwnedMenuItem(it, barId, itemId, body) }

    suspend fun deleteMenuItem(barId: String, itemId: String, version: Int):
        com.zerotoone.bottlemap.network.BarMenuResponseDto =
        withOwnerAuth { OwnerEndpoint.api.removeOwnedMenuItem(it, barId, itemId, version) }

    suspend fun resetMenu(barId: String, version: Int?):
        com.zerotoone.bottlemap.network.BarMenuResponseDto =
        withOwnerAuth { OwnerEndpoint.api.resetOwnedMenu(it, barId, mapOf("menuVersion" to version)) }

    suspend fun setSoldOut(barId: String, itemId: String, soldOut: Boolean):
        com.zerotoone.bottlemap.network.BarMenuResponseDto =
        withOwnerAuth { OwnerEndpoint.api.setOwnedItemSoldOut(it, barId, itemId, mapOf("soldOut" to soldOut)) }

    suspend fun confirmMenu(barId: String, version: Int?):
        com.zerotoone.bottlemap.network.OwnedBarDto =
        withOwnerAuth { OwnerEndpoint.api.confirmOwnedMenu(it, barId, mapOf("menuVersion" to version)) }

    suspend fun submitOwnerApplication(body: Map<String, Any?>):
        com.zerotoone.bottlemap.network.OwnerApplicationDto =
        withOwnerAuth { OwnerEndpoint.api.applyForBar(it, body) }

    suspend fun uploadApplicationMenuPhotos(
        applicationId: String, images: List<PreparedMenuImage>,
    ): com.zerotoone.bottlemap.network.OwnerApplicationDto =
        withOwnerAuth { authorization ->
            require(images.isNotEmpty()) { "메뉴 사진을 선택해 주세요." }
            val parts = images.map { image ->
                MultipartBody.Part.createFormData("images", image.filename,
                    image.bytes.toRequestBody(image.mimeType.toMediaType()))
            }
            OwnerEndpoint.api.uploadApplicationMenuPhotos(authorization, applicationId, parts)
        }

    suspend fun readBusinessCertificate(image: PreparedMenuImage):
        com.zerotoone.bottlemap.network.OwnerCertificateOcrDto =
        withOwnerAuth { authorization ->
            val part = MultipartBody.Part.createFormData(
                "image", image.filename, image.bytes.toRequestBody(image.mimeType.toMediaType()))
            OwnerEndpoint.api.readBusinessCertificate(authorization, part)
        }

    suspend fun cancelOwnerApplication(applicationId: String):
        com.zerotoone.bottlemap.network.OwnerApplicationDto =
        withOwnerAuth { OwnerEndpoint.api.cancelApplication(it, applicationId) }

    suspend fun cancelMenuImport(menuImportId: String): MenuImportStatusDto =
        withOwnerAuth { authorization ->
            OwnerEndpoint.api.cancelMenuImport(authorization, menuImportId)
        }

    suspend fun getMenuImports(barId: String):
        com.zerotoone.bottlemap.network.MenuImportListResponseDto =
        withOwnerAuth { authorization ->
            OwnerEndpoint.api.getMenuImports(authorization, barId, status = "all", limit = 20)
        }

    suspend fun getMenuImport(menuImportId: String): MenuImportStatusDto =
        withOwnerAuth { authorization ->
            OwnerEndpoint.api.getMenuImport(
                authorization = authorization,
                menuImportId = menuImportId,
            )
        }

    suspend fun uploadMenuImport(
        barId: String,
        images: List<PreparedMenuImage>,
        mode: String,
        idempotencyKey: String,
    ): MenuImportAcceptedDto = withOwnerAuth { authorization ->
        require(images.isNotEmpty()) { "Menu import must include photos" }
        val imageParts = images.map { image ->
            MultipartBody.Part.createFormData(
                "images",
                image.filename,
                image.bytes.toRequestBody(image.mimeType.toMediaType()),
            )
        }
        OwnerEndpoint.api.uploadMenuImport(
            authorization = authorization,
            idempotencyKey = idempotencyKey,
            barId = barId,
            images = imageParts,
            mode = mode.toRequestBody("text/plain".toMediaType()),
        )
    }

    suspend fun reviewAndApply(
        menuImportId: String,
        request: ReviewAndApplyRequestDto,
    ): ReviewAppliedResponseDto = withOwnerAuth { authorization ->
        OwnerEndpoint.api.reviewAndApply(
            authorization = authorization,
            menuImportId = menuImportId,
            request = request,
        )
    }
}

/** Developer-only operator repository; absent from customer variants. */
object OwnerRepositories {
    val owner: OwnerRepository by lazy { OwnerRepository() }
}
