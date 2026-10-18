// I2-A14: fake-only multi-image checks; no Photo Picker, Backend, or SDK calls.
package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.MenuImportAcceptedDto
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

class MenuPhotoBatchTest {
    private fun photo(id: String) = SelectedMenuImage("content://picker/" + id, id + ".jpg")
    private fun jpeg(bytes: Int = 3) = PreparedMenuImage(
        "test.jpg", "image/jpeg", byteArrayOf(0xff.toByte(), 0xd8.toByte(), 0xff.toByte()) +
            ByteArray(bytes - 3)
    )
    private val accepted = MenuImportAcceptedDto(
        menuImportId = "one-import", status = "processing", imageCount = 3,
        statusUrl = "/api/menu-imports/one-import", pollAfterMs = 3000,
    )

    @Test fun selectMultipleAndAddMaintainsOrder() {
        val first = appendMenuPhotos(emptyList(), listOf(photo("a"), photo("b"), photo("c")))
        val added = appendMenuPhotos(first.images, listOf(photo("d"), photo("e")))
        assertEquals(listOf("a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg"), added.images.map { it.displayName })
    }

    @Test fun canceledSelectionKeepsExisting() {
        val existing = listOf(photo("a"), photo("b"))
        assertEquals(existing, appendMenuPhotos(existing, emptyList()).images)
    }

    @Test fun repeatedUrisAreDeduplicatedAndLimitIsEnforced() {
        val r = appendMenuPhotos(listOf(photo("a")), listOf(
            photo("a"), photo("b"), photo("b"), photo("c"), photo("d"), photo("e"), photo("f"),
        ))
        assertEquals(2, r.duplicates)
        assertEquals(1, r.overLimit)
        assertEquals(listOf("a", "b", "c", "d", "e").map { photo(it) }, r.images)
    }

    @Test fun removeOnlyChosenImage() {
        assertEquals(listOf(photo("a"), photo("c")),
            removeMenuPhoto(listOf(photo("a"), photo("b"), photo("c")), photo("b").uri))
    }

    @Test fun noPhotosDoesNotSubmit() {
        var sent = false
        assertThrows(IllegalArgumentException::class.java) {
            runBlocking {
                submitMenuBatch(emptyList(), { jpeg() }, { sent = true; accepted })
            }
        }
        assertFalse(sent)
    }

    @Test fun unsupportedContentFailsBeforeAnyUpload() {
        var sent = 0
        val issue = assertThrows(MenuPhotoPreparationException::class.java) {
            runBlocking {
                submitMenuBatch(listOf(photo("a")), {
                    PreparedMenuImage("unknown.heic", "image/heic", byteArrayOf(0, 1, 2))
                }, { sent++; accepted })
            }
        }
        assertEquals(1, issue.imageOrder)
        assertEquals(0, sent)
    }

    @Test fun accessFailureOnSecondPageDoesNotUploadOnlyFirstPage() {
        var sent = false
        val error = assertThrows(MenuPhotoPreparationException::class.java) {
            runBlocking {
                submitMenuBatch(listOf(photo("a"), photo("b"), photo("c")), {
                    if (it.uri.endsWith("/b")) throw IOException("Photo access revoked")
                    jpeg()
                }, { sent = true; accepted })
            }
        }
        assertEquals(2, error.imageOrder)
        assertFalse(sent)
    }

    @Test fun allLocalImagesUnavailableDoNotCreateImport() {
        var called = 0
        assertThrows(MenuPhotoPreparationException::class.java) {
            runBlocking {
                submitMenuBatch(listOf(photo("a"), photo("b")), {
                    throw IOException("No access")
                }, { called++; accepted })
            }
        }
        assertEquals(0, called)
    }

    @Test fun allSuccessUploadsOnceInExactImageOrder() = runBlocking {
        val preparedOrder = mutableListOf<Int>()
        var posts = 0
        val input = listOf(photo("a"), photo("b"), photo("c"))
        val response = submitMenuBatch(input, {
            jpeg(bytes = when (it.displayName) {
                "a.jpg" -> 4
                "b.jpg" -> 5
                else -> 6
            })
        }, { files ->
            posts++
            assertEquals(listOf(4, 5, 6), files.map { it.bytes.size })
            accepted
        }, onPrepared = preparedOrder::add)
        assertEquals(accepted, response)
        assertEquals(listOf(1, 2, 3), preparedOrder)
        assertEquals(1, posts)
    }

    @Test fun serverNetworkFailureIsNotRetriedAutomatically() {
        var posts = 0
        assertThrows(IOException::class.java) {
            runBlocking {
                submitMenuBatch(listOf(photo("a"), photo("b")), { jpeg() }, {
                    posts++
                    throw IOException("Timeout: result unknown")
                })
            }
        }
        assertEquals(1, posts)
    }

    @Test fun totalSizeOverflowFailsBeforePost() {
        var posts = 0
        val issue = assertThrows(MenuPhotoPreparationException::class.java) {
            runBlocking {
                submitMenuBatch(listOf(photo("a"), photo("b"), photo("c"), photo("d")), {
                    jpeg(9 * 1024 * 1024)
                }, { posts++; accepted })
            }
        }
        assertEquals(4, issue.imageOrder)
        assertEquals(0, posts)
    }

    @Test fun oversizedIndividualImageFails() {
        val issue = assertThrows(MenuPhotoPreparationException::class.java) {
            runBlocking { prepareMenuBatch(listOf(photo("a")), { jpeg(MAX_MENU_PHOTO_BYTES + 1) }) }
        }
        assertEquals(1, issue.imageOrder)
    }

    @Test fun emptyOrTooManyPhotosAreRejected() {
        assertThrows(IllegalArgumentException::class.java) {
            runBlocking { prepareMenuBatch(emptyList(), { jpeg() }) }
        }
        assertThrows(IllegalArgumentException::class.java) {
            runBlocking { prepareMenuBatch((1..6).map { photo(it.toString()) }, { jpeg() }) }
        }
    }

    @Test fun duplicateUriAddedAgainDoesNotChangeSelection() {
        val input = listOf(photo("a"))
        val result = appendMenuPhotos(input, listOf(photo("a")))
        assertEquals(input, result.images)
        assertTrue(result.duplicates > 0)
    }
}
