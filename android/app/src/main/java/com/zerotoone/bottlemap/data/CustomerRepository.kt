// AI-assisted implementation draft (2026-10-13, I2-P13/P14). Human build/review pending.
package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.SearchBarsResponseDto

/** Existing network implementation behind a minimal test seam; not a new architecture. */
interface CustomerSearchSource {
    suspend fun searchBars(query: String): SearchBarsResponseDto
}

class CustomerRepository : CustomerSearchSource {
    override suspend fun searchBars(query: String): SearchBarsResponseDto =
        ApiClient.call {
            // Public guest endpoint: do not attach owner/session credentials.
            ApiClient.api.searchBars(query = query)
        }
}
