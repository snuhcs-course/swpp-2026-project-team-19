package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.SearchBarsResponseDto

class CustomerRepository {
    suspend fun searchBars(query: String): SearchBarsResponseDto =
        ApiClient.call {
            ApiClient.api.searchBars(query = query)
        }
}
