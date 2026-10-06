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
    @POST("api/auth/temp-login")
    suspend fun temporaryLogin(): TemporaryLoginResponseDto

    @GET("api/bars")
    suspend fun getBars(
        @Header("Authorization") authorization: String,
        @Query("status") status: String = "active",
        @Query("limit") limit: Int = 100,
        @Query("cursor") cursor: String? = null,
    ): BarListResponseDto

    @GET("api/bars/{barId}/menu-imports")
    suspend fun getMenuImports(
        @Header("Authorization") authorization: String,
        @Path("barId") barId: String,
        @Query("status") status: String = "all",
        @Query("limit") limit: Int = 20,
        @Query("cursor") cursor: String? = null,
    ): MenuImportListResponseDto

    @GET("api/search/bars")
    suspend fun searchBars(
        @Query("query") query: String,
        @Query("limit") limit: Int = 50,
    ): SearchBarsResponseDto

    @Multipart
    @POST("api/bars/{barId}/menu-imports")
    suspend fun uploadMenuImport(
        @Header("Authorization") authorization: String,
        @Header("Idempotency-Key") idempotencyKey: String,
        @Path("barId") barId: String,
        @Part images: List<MultipartBody.Part>,
        @Part("mode") mode: RequestBody,
        @Part("ownerNote") ownerNote: RequestBody? = null,
    ): MenuImportAcceptedDto

    @GET("api/menu-imports/{menuImportId}")
    suspend fun getMenuImport(
        @Header("Authorization") authorization: String,
        @Path("menuImportId") menuImportId: String,
    ): MenuImportStatusDto

    @POST("api/menu-imports/{menuImportId}/review-and-apply")
    suspend fun reviewAndApply(
        @Header("Authorization") authorization: String,
        @Path("menuImportId") menuImportId: String,
        @Body request: ReviewAndApplyRequestDto,
    ): ReviewAppliedResponseDto
}
