// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.network

import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

interface BottleMapApi {
    @GET("api/me")
    suspend fun getMe(
        @Header("Authorization") authorization: String,
    ): CurrentUserDto

    @GET("api/bars/{barId}/menu")
    suspend fun getPublishedBarMenu(
        @Path("barId") barId: String,
        @Header("Authorization") authorization: String? = null,
    ): BarMenuResponseDto

    // Backend A9 PR #43, API spec 3.12. Public, complete, server-sorted results.
    @GET("api/search/nearby-bars")
    suspend fun getNearbyBars(
        @Query("lat") latitude: Double,
        @Query("lng") longitude: Double,
        @Query("radiusMeters") radiusMeters: Int = 500,
    ): NearbyBarsResponseDto

    @GET("api/search/bars")
    suspend fun searchBars(
        @Query("query") query: String,
        @Query("limit") limit: Int = 50,
    ): SearchBarsResponseDto

}
