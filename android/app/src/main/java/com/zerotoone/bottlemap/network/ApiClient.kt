// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.zerotoone.bottlemap.BuildConfig
import java.io.IOException
import java.util.concurrent.TimeUnit
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

class BottleMapApiException(
    val httpStatus: Int? = null,
    val code: String,
    override val message: String,
    val details: Map<String, Any?>? = null,
    val fieldErrors: List<FieldErrorDto> = emptyList(),
    cause: Throwable? = null,
) : Exception(message, cause)

object ApiClient {
    val moshi: Moshi = Moshi.Builder()
        .addLast(KotlinJsonAdapterFactory())
        .build()

    private val logging = HttpLoggingInterceptor().apply {
        level = if (BuildConfig.DEBUG) {
            HttpLoggingInterceptor.Level.BASIC
        } else {
            HttpLoggingInterceptor.Level.NONE
        }
    }

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .addInterceptor(logging)
        .build()

    val api: BottleMapApi = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(httpClient)
        .addConverterFactory(MoshiConverterFactory.create(moshi))
        .build()
        .create(BottleMapApi::class.java)

    private val errorAdapter = moshi.adapter(ApiErrorEnvelopeDto::class.java)

    suspend fun <T> call(block: suspend () -> T): T {
        try {
            return block()
        } catch (error: HttpException) {
            val parsed = error.response()
                ?.errorBody()
                ?.string()
                ?.let { body -> runCatching { errorAdapter.fromJson(body) }.getOrNull() }
                ?.error
            throw BottleMapApiException(
                httpStatus = error.code(),
                code = parsed?.code ?: "HTTP_" + error.code(),
                message = parsed?.message ?: "Request failed (" + error.code() + ").",
                details = parsed?.details,
                fieldErrors = parsed?.fieldErrors.orEmpty(),
                cause = error,
            )
        } catch (error: IOException) {
            throw BottleMapApiException(
                code = "NETWORK_ERROR",
                message = "Cannot reach the BottleMap backend. Check the server and network.",
                cause = error,
            )
        }
    }
}
