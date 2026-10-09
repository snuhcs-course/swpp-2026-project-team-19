// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.SearchBarsResponseDto

class CustomerRepository {
    suspend fun searchBars(query: String): SearchBarsResponseDto =
        ApiClient.call {
            ApiClient.api.searchBars(query = query)
        }
}
