package com.zerotoone.bottlemap.network

import com.zerotoone.bottlemap.telemetry.*
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
        .addInterceptor { chain ->
            try { chain.proceed(chain.request()) }
            catch (error: IOException) {
                throw EndpointIOException(ApiEndpoint.fromPath(chain.request().url.encodedPath), error)
            }
        }
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        // Debug BASIC logging prints full URLs, including the user's lat/lng.
        // Never log this privacy-sensitive Nearby request on the Android device.
        // Backend access logs are a separate concern (API spec 3.12.3).
        .addInterceptor { chain ->
            if (chain.request().url.encodedPath == "/api/search/nearby-bars" ||
                chain.request().url.encodedPath == "/api/search/map-bars" ||
                chain.request().url.encodedPath == "/api/search/bars"
            ) {
                chain.proceed(chain.request())
            } else {
                logging.intercept(chain)
            }
        }
        .build()

    private val retrofit: Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(httpClient)
        .addConverterFactory(MoshiConverterFactory.create(moshi))
        .build()

    val api: BottleMapApi = retrofit.create(BottleMapApi::class.java)

    fun <T> createService(type: Class<T>): T = retrofit.create(type)

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
            AppTelemetry.current.log(TelemetryEvent.ApiError(
                ApiEndpoint.fromPath(error.response()?.raw()?.request?.url?.encodedPath.orEmpty()),
                HttpStatus.from(error.code()), ErrorCode.from(parsed?.code)))
            throw BottleMapApiException(
                httpStatus = error.code(),
                code = parsed?.code ?: "HTTP_" + error.code(),
                // #189: retain structured codes/fields, never expose untrusted server prose.
                message = "요청을 처리하지 못했어요. 입력 내용과 연결을 확인해 주세요.",
                details = parsed?.details,
                fieldErrors = parsed?.fieldErrors.orEmpty(),
                cause = error,
            )
        } catch (error: IOException) {
            if (kotlin.coroutines.coroutineContext[kotlinx.coroutines.Job]?.isActive != false) {
                AppTelemetry.current.log(TelemetryEvent.ApiError(
                    (error as? EndpointIOException)?.endpoint ?: ApiEndpoint.UNKNOWN,
                    HttpStatus.NO_RESPONSE, ErrorCode.NETWORK_ERROR))
            }
            throw BottleMapApiException(
                code = "NETWORK_ERROR",
                message = "인터넷 연결을 확인한 뒤 다시 시도해 주세요.",
                cause = error,
            )
        }
    }
}


private class EndpointIOException(val endpoint: ApiEndpoint, cause: IOException) : IOException("Request failed", cause)
