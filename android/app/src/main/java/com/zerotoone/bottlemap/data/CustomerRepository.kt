package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BarMenuResponseDto
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.SearchBarsResponseDto
import com.zerotoone.bottlemap.network.PopularProductsResponseDto

/** Existing network implementation behind a minimal test seam; not a new architecture. */
interface CustomerSearchSource {
    suspend fun searchBars(query: String): SearchBarsResponseDto
}

interface CustomerBarDetailSource {
    suspend fun getPublishedBarMenu(barId: String): BarMenuResponseDto
}

/**
 * P18 discovery network seam: preserves the public API contract while keeping
 * Retrofit out of UI ViewModels. Small fakes can implement this in local tests.
 */
interface CustomerDiscoverySource {
    suspend fun popularProducts(limit:Int = 10):PopularProductsResponseDto
    suspend fun searchProduct(
        query:String?,productId:String?,source:String,
        latitude:Double?=null,longitude:Double?=null,
    ):SearchBarsResponseDto
}

class CustomerRepository : CustomerSearchSource, CustomerBarDetailSource, CustomerDiscoverySource {
    override suspend fun popularProducts(limit:Int):PopularProductsResponseDto =
        ApiClient.call { ApiClient.api.popularProducts(limit=limit) }

    override suspend fun searchProduct(
        query:String?,productId:String?,source:String,latitude:Double?,longitude:Double?,
    ):SearchBarsResponseDto = ApiClient.call {
        ApiClient.api.searchProductP18(
            query=query?.takeIf(String::isNotBlank),
            productId=productId?.takeIf(String::isNotBlank),
            latitude=latitude,longitude=longitude,source=source,
        )
    }

    override suspend fun getPublishedBarMenu(barId: String): BarMenuResponseDto {
        val auth = AppAuth.gateway
        val token = auth.currentAccessTokenOrNull()
        // Public guest request: no credentials. Signed-in request: optional JWT.
        if (token == null) return ApiClient.call {
            ApiClient.api.getPublishedBarMenu(barId)
        }
        return try {
            ApiClient.call { ApiClient.api.getPublishedBarMenu(barId, "Bearer $token") }
        } catch (error: BottleMapApiException) {
            if (error.code != "UNAUTHENTICATED") throw error
            val newToken = auth.refreshAccessTokenAfter401(token)
            // If refresh fails, fall back to guest WITHOUT the stale token.
            try {
                ApiClient.call {
                    ApiClient.api.getPublishedBarMenu(
                        barId,
                        newToken?.let { "Bearer $it" },
                    )
                }
            } catch (retryError: BottleMapApiException) {
                if (retryError.code != "UNAUTHENTICATED" || newToken == null) throw retryError
                // A second 401 is not retryable. Drop the stale signed-in
                // session and show the same public bar as a Guest.
                auth.logout()
                ApiClient.call { ApiClient.api.getPublishedBarMenu(barId) }
            }
        }
    }

    override suspend fun searchBars(query: String): SearchBarsResponseDto =
        ApiClient.call {
            // Public guest endpoint: do not attach owner/session credentials.
            ApiClient.api.searchBars(query = query)
        }
}
