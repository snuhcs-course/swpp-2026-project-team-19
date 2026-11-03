package com.zerotoone.bottlemap.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import retrofit2.http.DELETE
import retrofit2.http.POST
import retrofit2.http.PUT

/** Contract tests for API spec §3.11.16 and §3.11.17 (routes may deploy later). */
class OwnerPreapplicationContractTest {
    @Test fun businessPrecheckResultHasOnlyResultField() {
        val adapter=ApiClient.moshi.adapter(OwnerBusinessVerificationDto::class.java)
        assertEquals("matched",adapter.fromJson("""{"result":"matched"}""")?.result)
        assertEquals("not_matched",adapter.fromJson("""{"result":"not_matched"}""")?.result)
        assertEquals("unavailable",adapter.fromJson("""{"result":"unavailable"}""")?.result)
    }

    @Test fun pendingNewBarApplicationDeserializesPrivateCoverUrls() {
        val json="""
          {
            "applicationId":"application-1",
            "applicationType":"new_bar",
            "status":"pending",
            "createdAt":"2026-11-03T00:00:00Z",
            "coverPhoto":{
              "imageUrl":"https://example.invalid/private-cover",
              "thumbnailUrl":"https://example.invalid/private-thumb",
              "imageUrlExpiresAt":null
            }
          }
        """.trimIndent()
        val adapter=ApiClient.moshi.adapter(OwnerApplicationDto::class.java)
        val item=adapter.fromJson(json)
        assertEquals("https://example.invalid/private-cover",item?.coverPhoto?.imageUrl)
        assertNotNull(item?.coverPhoto)
        assertNull(item?.coverPhoto?.imageUrlExpiresAt)
        assertNull(adapter.fromJson(
            """{"applicationId":"a","applicationType":"new_bar","status":"approved","createdAt":"2026-11-03T00:00:00Z"}"""
        )?.coverPhoto)
    }

    @Test fun routePathsMatchCurrentContract() {
        val functions=OwnerApi::class.java.declaredMethods.associateBy { it.name }
        assertEquals("api/owner-applications/business-verification",
            functions.getValue("verifyBusinessRegistration")
                .getAnnotation(POST::class.java)?.value)
        val upload="api/owner-applications/{applicationId}/cover-photo"
        assertEquals(upload,functions.getValue("uploadApplicationCoverPhoto")
            .getAnnotation(PUT::class.java)?.value)
        assertEquals(upload,functions.getValue("removeApplicationCoverPhoto")
            .getAnnotation(DELETE::class.java)?.value)
    }
}
