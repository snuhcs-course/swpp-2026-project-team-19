package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BarDto
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.MenuImportAcceptedDto
import com.zerotoone.bottlemap.network.MenuImportStatusDto
import com.zerotoone.bottlemap.network.ReviewAndApplyRequestDto
import com.zerotoone.bottlemap.network.ReviewAppliedResponseDto
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

class OwnerRepository {
    private var accessToken: String? = null

    private suspend fun ensureAccessToken(): String {
        accessToken?.let { return it }
        val token = ApiClient.call { ApiClient.api.temporaryLogin() }.accessToken
        accessToken = token
        return token
    }

    private suspend fun <T> withOperatorAuth(block: suspend (String) -> T): T {
        val firstToken = ensureAccessToken()
        try {
            return ApiClient.call { block("Bearer " + firstToken) }
        } catch (error: BottleMapApiException) {
            if (error.code != "UNAUTHENTICATED") throw error
            accessToken = null
            val refreshed = ensureAccessToken()
            return ApiClient.call { block("Bearer " + refreshed) }
        }
    }

    suspend fun getBars(): List<BarDto> = withOperatorAuth { authorization ->
        buildList {
            var cursor: String? = null
            do {
                val page = ApiClient.api.getBars(
                    authorization = authorization,
                    status = "active",
                    limit = 100,
                    cursor = cursor,
                )
                addAll(page.items)
                cursor = page.nextCursor
            } while (cursor != null)
        }
    }

    suspend fun getMenuImport(menuImportId: String): MenuImportStatusDto =
        withOperatorAuth { authorization ->
            ApiClient.api.getMenuImport(
                authorization = authorization,
                menuImportId = menuImportId,
            )
        }

    suspend fun uploadMenuImport(
        barId: String,
        image: PreparedMenuImage,
        mode: String,
        idempotencyKey: String,
    ): MenuImportAcceptedDto = withOperatorAuth { authorization ->
        val imageBody = image.bytes.toRequestBody(image.mimeType.toMediaType())
        val imagePart = MultipartBody.Part.createFormData(
            "images",
            image.filename,
            imageBody,
        )
        ApiClient.api.uploadMenuImport(
            authorization = authorization,
            idempotencyKey = idempotencyKey,
            barId = barId,
            images = listOf(imagePart),
            mode = mode.toRequestBody("text/plain".toMediaType()),
        )
    }

    suspend fun reviewAndApply(
        menuImportId: String,
        request: ReviewAndApplyRequestDto,
    ): ReviewAppliedResponseDto = withOperatorAuth { authorization ->
        ApiClient.api.reviewAndApply(
            authorization = authorization,
            menuImportId = menuImportId,
            request = request,
        )
    }
}

object Repositories {
    val customer: CustomerRepository by lazy { CustomerRepository() }
    val owner: OwnerRepository by lazy { OwnerRepository() }
}
