package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BottleMapApi
import com.sun.net.httpserver.HttpServer
import java.io.File
import java.net.InetSocketAddress
import java.util.concurrent.CopyOnWriteArrayList
import kotlinx.coroutines.test.runTest
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.*
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

class OnDeviceLocationNetworkTest {
    private data class CapturedRequest(
        val method: String, val url: HttpUrl, val bodySize: Int, val authorization: String?,
    )

    @Test fun discoveryAndBothSearchModesSendNoCustomerCoordinatesOrBounds() = runTest {
        // JDK HTTP server avoids depending on the resolved OkHttp version's
        // private internals. Capture actual serialized traffic on loopback only.
        val server = HttpServer.create(InetSocketAddress("127.0.0.1",0),0)
        val baseUrl = "http://127.0.0.1:${server.address.port}/".toHttpUrl()
        val requests = CopyOnWriteArrayList<CapturedRequest>()
        server.createContext("/") { exchange ->
            requests.add(CapturedRequest(exchange.requestMethod,
                requireNotNull(baseUrl.resolve(exchange.requestURI.toASCIIString())),
                exchange.requestBody.use { it.readBytes().size }, exchange.requestHeaders.getFirst("Authorization")))
            val response = if(exchange.requestURI.path == "/api/search/all-bars")
                """{"items":[{"barId":"bar-a","name":"Synthetic bar","address":"Synthetic address","latitude":37.478321,"longitude":126.951234,"menuUpdatedAt":null,"coverThumbnailUrl":null}]}"""
            else """{"query":null,"matchType":"none","items":[],"matchedProducts":[],"truncated":false}"""
            val bytes = response.toByteArray(Charsets.UTF_8)
            exchange.responseHeaders.add("Content-Type","application/json")
            exchange.sendResponseHeaders(200,bytes.size.toLong())
            exchange.responseBody.use { it.write(bytes) }
            exchange.close()
        }
        server.start()
        try {
            val api = Retrofit.Builder().baseUrl(baseUrl)
                .addConverterFactory(MoshiConverterFactory.create(ApiClient.moshi)).build()
                .create(BottleMapApi::class.java)
            val all = AllBarsRepository(fetch = { ApiClient.call { api.getAllBars() } })
            val nearby = BackendNearbyBarsRepository(all)
            val map = BackendMapBarsRepository(all)
            val customer = CustomerRepository(api)
            nearby.listNearbyBars(NearbyCoordinate(37.478,126.951))
            map.listMapBars(MapBounds(37.47,126.95,37.48,126.96))
            nearby.listNearbyBars(NearbyCoordinate(35.1796,129.0756))
            map.listMapBars(MapBounds(35.17,129.07,35.18,129.08))
            customer.searchProduct("synthetic whisky",null,"input")
            customer.searchProduct(null,"00000000-0000-4000-8000-000000000021","popular")
            customer.searchBars("synthetic legacy")

            assertEquals(4,requests.size) // One catalog request across screens/regions.
            assertEquals("/api/search/all-bars",requests.first().url.encodedPath)
            assertNull(requests.first().url.encodedQuery)
            assertEquals(listOf("/api/search/all-bars","/api/search/bars","/api/search/bars","/api/search/bars"),
                requests.map { it.url.encodedPath })
            assertEquals("100",requests[1].url.queryParameter("limit"))
            assertEquals("100",requests[2].url.queryParameter("limit"))
            val forbidden = setOf("lat","lng","latitude","longitude","south","west","north","east","radiusMeters")
            requests.forEach { request ->
                assertEquals("GET",request.method)
                assertTrue(request.url.queryParameterNames.intersect(forbidden).isEmpty())
                assertEquals(0,request.bodySize)
                assertNull(request.authorization)
            }
            // Only synthetic fixtures. This is local HTTP evidence, not a device capture.
            File("build/reports/p21-network.log").apply {
                parentFile?.mkdirs()
                writeText("Local HTTP capture — synthetic data only\n" +
                    requests.joinToString("\n") { "${it.method} ${it.url.encodedPath}${it.url.encodedQuery?.let { query -> "?$query" }.orEmpty()}" } +
                    "\n4 requests; no customer coordinates/bounds/body/Authorization.\n")
            }
        } finally {
            server.stop(0)
        }
    }
}
