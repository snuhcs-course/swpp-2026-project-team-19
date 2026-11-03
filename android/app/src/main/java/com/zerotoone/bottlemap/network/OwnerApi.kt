// A12/A13: operator endpoints are linked only into Developer builds.
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

interface OwnerApi {
    @POST("api/auth/temp-login")
    suspend fun temporaryLogin(): TemporaryLoginResponseDto

    /** Production owner routes: the Supabase user is never an operator fixture. */
    @GET("api/me/bars")
    suspend fun getMyBars(@Header("Authorization") authorization: String): MyOwnedBarsDto

    @GET("api/me/owner-applications")
    suspend fun getMyOwnerApplications(
        @Header("Authorization") authorization: String,
    ): MyOwnerApplicationsDto

    @GET("api/bars/{barId}")
    suspend fun getOwnedBar(
        @Header("Authorization") authorization: String,
        @Path("barId") barId: String,
    ): OwnedBarDto

    @retrofit2.http.PATCH("api/bars/{barId}")
    suspend fun updateOwnedBar(
        @Header("Authorization") authorization: String,
        @Path("barId") barId: String,
        @Body body: Map<String, @JvmSuppressWildcards Any?>,
    ): OwnedBarDto

    @GET("api/bars/{barId}/menu")
    suspend fun getOwnedMenu(
        @Header("Authorization") authorization: String,
        @Path("barId") barId: String,
    ): BarMenuResponseDto

    @POST("api/bars/{barId}/menu/items")
    suspend fun addOwnedMenuItem(
        @Header("Authorization") authorization: String,
        @Path("barId") barId: String,
        @Body body: Map<String, @JvmSuppressWildcards Any?>,
    ): BarMenuResponseDto

    @retrofit2.http.PUT("api/bars/{barId}/menu/items/{itemId}")
    suspend fun updateOwnedMenuItem(
        @Header("Authorization") authorization: String,
        @Path("barId") barId: String,
        @Path("itemId") itemId: String,
        @Body body: Map<String, @JvmSuppressWildcards Any?>,
    ): BarMenuResponseDto

    @retrofit2.http.DELETE("api/bars/{barId}/menu/items/{itemId}")
    suspend fun removeOwnedMenuItem(
        @Header("Authorization") authorization: String,
        @Path("barId") barId: String,
        @Path("itemId") itemId: String,
        @Query("menuVersion") menuVersion: Int,
    ): BarMenuResponseDto

    @POST("api/bars/{barId}/menu/reset")
    suspend fun resetOwnedMenu(
        @Header("Authorization") authorization: String,
        @Path("barId") barId: String,
        @Body body: Map<String, @JvmSuppressWildcards Any?>,
    ): BarMenuResponseDto

    @retrofit2.http.PUT("api/bars/{barId}/menu/items/{itemId}/sold-out")
    suspend fun setOwnedItemSoldOut(
        @Header("Authorization") authorization: String,
        @Path("barId") barId: String,
        @Path("itemId") itemId: String,
        @Body body: Map<String, @JvmSuppressWildcards Any?>,
    ): BarMenuResponseDto

    @POST("api/bars/{barId}/menu/confirm")
    suspend fun confirmOwnedMenu(
        @Header("Authorization") authorization: String,
        @Path("barId") barId: String,
        @Body body: Map<String, @JvmSuppressWildcards Any?>,
    ): OwnedBarDto

    @POST("api/owner-applications")
    suspend fun applyForBar(
        @Header("Authorization") authorization: String,
        @Body body: Map<String, @JvmSuppressWildcards Any?>,
    ): OwnerApplicationDto

    @Multipart
    @retrofit2.http.PUT("api/owner-applications/{applicationId}/menu-photos")
    suspend fun uploadApplicationMenuPhotos(
        @Header("Authorization") authorization: String,
        @Path("applicationId") applicationId: String,
        @Part images: List<MultipartBody.Part>,
    ): OwnerApplicationDto

    @Multipart
    @POST("api/owner-applications/business-certificate-ocr")
    suspend fun readBusinessCertificate(
        @Header("Authorization") authorization: String,
        @Part image: MultipartBody.Part,
    ): OwnerCertificateOcrDto

    @POST("api/owner-applications/{applicationId}/cancel")
    suspend fun cancelApplication(
        @Header("Authorization") authorization: String,
        @Path("applicationId") applicationId: String,
    ): OwnerApplicationDto

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

    @POST("api/menu-imports/{menuImportId}/cancel")
    suspend fun cancelMenuImport(
        @Header("Authorization") authorization: String,
        @Path("menuImportId") menuImportId: String,
    ): MenuImportStatusDto

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
 
/** Shares the same Retrofit base URL, timeouts, and JSON converter as Customer. */
internal object OwnerEndpoint {
    val api: OwnerApi by lazy { ApiClient.createService(OwnerApi::class.java) }
}
