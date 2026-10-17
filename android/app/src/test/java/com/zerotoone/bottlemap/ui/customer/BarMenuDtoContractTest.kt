// AI-assisted tests (2026-10-17, I2-P24). Execute with :app:testDebugUnitTest.
package com.zerotoone.bottlemap.ui.customer

import com.squareup.moshi.JsonDataException
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.zerotoone.bottlemap.network.BarMenuResponseDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

/** Uses the exact JSON keys/nullability from API contract section 3.9. */
class BarMenuDtoContractTest {
    private val adapter = Moshi.Builder()
        .addLast(KotlinJsonAdapterFactory())
        .build()
        .adapter(BarMenuResponseDto::class.java)

    @Test
    fun decodesPublishedMenuWithNullablePourAndLabels() {
        val json = """
            {
              "barId":"22222222-2222-4222-8222-222222222222",
              "name":"관악 위스키 바",
              "address":"관악로 1 2층",
              "latitude":37.478321,
              "longitude":126.951234,
              "phone":null,
              "menuBoardId":"66666666-6666-4666-8666-666666666666",
              "publishedAt":"2026-10-04T09:15:00Z",
              "items":[{
                "menuBoardEntryId":"88888888-8888-4888-8888-888888888881",
                "barMenuItemId":"99999999-9999-4999-8999-999999999991",
                "productId":"44444444-4444-4444-8444-444444444444",
                "displayName":"글렌피딕 12년",
                "sortOrder":1,
                "options":[{
                  "menuEntryOptionId":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                  "optionLabel":null,
                  "pourMl":null,
                  "priceKrw":17000,
                  "sortOrder":1
                }]
              }]
            }
        """.trimIndent()
        val response = requireNotNull(adapter.fromJson(json))
        assertEquals("관악 위스키 바", response.name)
        assertNull(response.phone)
        assertEquals("글렌피딕 12년", response.items.single().displayName)
        assertNull(response.items.single().options.single().pourMl)
        assertNull(response.items.single().options.single().optionLabel)
        assertEquals(17000, response.items.single().options.single().priceKrw)
    }

    @Test
    fun decodesBarWithoutPublishedMenu() {
        val json = """
            {
              "barId":"22222222-2222-4222-8222-222222222222",
              "name":"관악 위스키 바",
              "address":"관악로 1 2층",
              "latitude":37.478321,
              "longitude":126.951234,
              "phone":null,
              "menuBoardId":null,
              "publishedAt":null,
              "items":[]
            }
        """.trimIndent()
        val response = requireNotNull(adapter.fromJson(json))
        assertNull(response.menuBoardId)
        assertNull(response.publishedAt)
        assertEquals(0, response.items.size)
        assertEquals(
            EmptyMenuReason.NO_PUBLISHED_MENU,
            (response.toBarDetailUiState() as BarDetailUiState.Empty).reason,
        )
    }

    @Test
    fun missingRequiredBarNameIsRejectedRatherThanFabricated() {
        val json = """
            {
              "barId":"22222222-2222-4222-8222-222222222222",
              "address":"관악로 1 2층",
              "latitude":37.478321,
              "longitude":126.951234,
              "phone":null,
              "menuBoardId":null,
              "publishedAt":null,
              "items":[]
            }
        """.trimIndent()
        assertThrows(JsonDataException::class.java) {
            adapter.fromJson(json)
        }
    }
}
