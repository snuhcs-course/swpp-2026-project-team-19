package com.zerotoone.bottlemap.telemetry

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BottleMapApiException
import kotlinx.coroutines.test.runTest
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import okhttp3.Request
import okhttp3.Protocol
import org.junit.Assert.*
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response
import java.io.IOException

class ApiErrorTelemetryTest {
    @Test fun httpFailureRecordsOnlyTemplateStatusAndAllowlistedCodeAndStillThrows() = runTest {
        val fake = FakeTelemetry(); val previous = AppTelemetry.current; AppTelemetry.current = fake
        try {
            val raw = okhttp3.Response.Builder().request(Request.Builder()
                .url("https://example.invalid/api/bars/secret-id/menu?query=private@example.invalid").build())
                .protocol(Protocol.HTTP_1_1).code(409).message("Conflict").build()
            val body = """{"error":{"code":"MENU_OUTDATED","message":"private@example.invalid"}}"""
                .toResponseBody("application/json".toMediaType())
            try { ApiClient.call<Unit> { throw HttpException(Response.error<Unit>(body, raw)) }; fail() }
            catch (error: BottleMapApiException) { assertEquals("MENU_OUTDATED", error.code) }
            assertEquals(listOf(TelemetryEvent.ApiError(ApiEndpoint.API_BARS_ID_MENU,
                HttpStatus.CONFLICT, ErrorCode.MENU_OUTDATED)), fake.events)
        } finally { AppTelemetry.current = previous }
    }
    @Test fun connectionFailureAndCancellationAreDistinguished() = runTest {
        val fake = FakeTelemetry(); val previous = AppTelemetry.current; AppTelemetry.current = fake
        try {
            try { ApiClient.call<Unit> { throw IOException("private URL") }; fail() }
            catch (error: BottleMapApiException) { assertEquals("NETWORK_ERROR",error.code) }
            assertEquals(listOf(TelemetryEvent.ApiError(ApiEndpoint.UNKNOWN,
                HttpStatus.NO_RESPONSE,ErrorCode.NETWORK_ERROR)),fake.events)
            try { ApiClient.call<Unit> { throw kotlinx.coroutines.CancellationException() }; fail() }
            catch (_: kotlinx.coroutines.CancellationException) { }
            assertEquals(1,fake.events.size)
        } finally { AppTelemetry.current = previous }
    }
}
