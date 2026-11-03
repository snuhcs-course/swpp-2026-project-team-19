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

    // I2 PR #54 / spec 3.13: exact visible map bounds, no distanceMeters.
    @GET("api/search/map-bars")
    suspend fun getMapBars(
        @Query("south") south: Double,
        @Query("west") west: Double,
        @Query("north") north: Double,
        @Query("east") east: Double,
    ): MapBarsResponseDto

    @GET("api/search/nearby-bars")
    suspend fun getNearbyBars(
        @Query("lat") latitude: Double,
        @Query("lng") longitude: Double,
        @Query("radiusMeters") radiusMeters: Int = 500,
    ): NearbyBarsResponseDto

    // Confirmed API spec §3.17: public, guest-safe, search-count-ranked cards.
    @GET("api/search/popular-products")
    suspend fun popularProducts(@Query("limit") limit: Int = 10): PopularProductsResponseDto

    // §3.10: only one of query/productId is sent. No extra ad-hoc endpoint.
    @GET("api/search/bars")
    suspend fun searchProductP18(
        @Query("query") query: String? = null,
        @Query("productId") productId: String? = null,
        @Query("lat") latitude: Double? = null,
        @Query("lng") longitude: Double? = null,
        @Query("source") source: String = "input",
        @Query("limit") limit: Int = 50,
    ): SearchBarsResponseDto

    @GET("api/search/bars")
    suspend fun searchBars(
        @Query("query") query: String,
        @Query("limit") limit: Int = 50,
    ): SearchBarsResponseDto

}
