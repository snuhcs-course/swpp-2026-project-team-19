// AI-assisted implementation draft (2026-10-13, I2-P13/P14). Human build/review pending.
package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BarMenuResponseDto
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.SearchBarsResponseDto

/** Existing network implementation behind a minimal test seam; not a new architecture. */
interface CustomerSearchSource {
    suspend fun searchBars(query: String): SearchBarsResponseDto
}

interface CustomerBarDetailSource {
    suspend fun getPublishedBarMenu(barId: String): BarMenuResponseDto
}

class CustomerRepository : CustomerSearchSource, CustomerBarDetailSource {
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
