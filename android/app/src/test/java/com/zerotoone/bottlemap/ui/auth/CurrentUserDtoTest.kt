package com.zerotoone.bottlemap.ui.auth

import com.squareup.moshi.JsonDataException
import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.CurrentUserDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

/** Exact response contract of GET /api/me (API specification 3.2). */
class CurrentUserDtoTest {
    private val adapter = ApiClient.moshi.adapter(CurrentUserDto::class.java)

    @Test
    fun readsSignedInCustomerIncludingNullableProfile() {
        val user = adapter.fromJson(
            """
            {
                "userId":"11111111-1111-4111-8111-111111111111",
                "email":null,
                "displayName":null,
                "userType":"customer",
                "updatedAt":"2026-10-13T09:00:00Z"
            }
            """.trimIndent(),
        )!!
        assertEquals("customer", user.userType)
        assertNull(user.email)
        assertNull(user.displayName)
    }

    @Test
    fun missingRequiredUserIdFailsRatherThanFabricatingAccount() {
        assertThrows(JsonDataException::class.java) {
            adapter.fromJson(
                """
                {
                    "email":"user@example.com",
                    "displayName":"BottleMap",
                    "userType":"customer",
                    "updatedAt":"2026-10-13T09:00:00Z"
                }
                """.trimIndent(),
            )
        }
    }
}
