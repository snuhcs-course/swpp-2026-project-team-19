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
    // I2 PR #54 / spec 3.11.11: public global active-bar name/address lookup.
    @GET("api/search/bar-names")
    suspend fun searchBarNames(
        @Query("query") query: String,
        @Query("limit") limit: Int = 20,
    ): BarNamesResponseDto

    // Spec 3.19: public complete list; same item shape as 3.13, no queries.
    @GET("api/search/all-bars")
    suspend fun getAllBars(): MapBarsResponseDto

    // Confirmed API spec §3.17: public, guest-safe, search-count-ranked cards.
    @GET("api/search/popular-products")
    suspend fun popularProducts(@Query("limit") limit: Int = 10): PopularProductsResponseDto

    // §3.10: only one of query/productId is sent. No extra ad-hoc endpoint.
    @GET("api/search/bars")
    suspend fun searchProductP18(
        @Query("query") query: String? = null,
        @Query("productId") productId: String? = null,
        @Query("source") source: String = "input",
        @Query("limit") limit: Int = 50,
    ): SearchBarsResponseDto

    @GET("api/search/bars")
    suspend fun searchBars(
        @Query("query") query: String,
        @Query("limit") limit: Int = 50,
    ): SearchBarsResponseDto

}
