package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BottleMapApi
import java.io.File
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

class OnDeviceLocationNetworkTest {
    @Test fun discoveryAndBothSearchModesSendNoCustomerCoordinatesOrBounds() = runTest {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""{"items":[{"barId":"bar-a","name":"Synthetic bar","address":"Synthetic address","latitude":37.478321,"longitude":126.951234,"menuUpdatedAt":null,"coverThumbnailUrl":null}]}"""))
            repeat(3) { server.enqueue(MockResponse().setBody("""{"query":null,"matchType":"none","items":[],"matchedProducts":[],"truncated":false}""")) }
            server.start()
            val api = Retrofit.Builder().baseUrl(server.url("/"))
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

            assertEquals(4,server.requestCount) // One catalog request across screens/regions.
            val requests = (1..4).map { requireNotNull(server.takeRequest(5,TimeUnit.SECONDS)) }
            assertEquals("/api/search/all-bars",requests.first().path)
            assertEquals(listOf("/api/search/all-bars","/api/search/bars","/api/search/bars","/api/search/bars"),
                requests.map { it.requestUrl!!.encodedPath })
            assertEquals("100",requests[1].requestUrl!!.queryParameter("limit"))
            assertEquals("100",requests[2].requestUrl!!.queryParameter("limit"))
            val forbidden = setOf("lat","lng","latitude","longitude","south","west","north","east","radiusMeters")
            requests.forEach { request ->
                assertEquals("GET",request.method)
                assertTrue(request.requestUrl!!.queryParameterNames.intersect(forbidden).isEmpty())
                assertEquals(0L,request.bodySize)
                assertNull(request.getHeader("Authorization"))
            }
            // Only synthetic fixtures. This is local HTTP evidence, not a device capture.
            File("build/reports/p21-network.log").apply {
                parentFile.mkdirs()
                writeText("MockWebServer HTTP capture — synthetic data only\n" +
                    requests.joinToString("\n") { "${it.method} ${it.path}" } +
                    "\n4 requests; no customer coordinates/bounds/body/Authorization.\n")
            }
        }
    }
}
