package com.zerotoone.bottlemap.data

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertNotEquals
import org.junit.Test

/** Real transaction cache used by MenuUploadViewModel, exercised with a fake preparer. */
class MenuUploadRetryCacheTest {
    @Test fun networkRetryReusesExactPreparedBytesAndKey() = runBlocking {
        val cache = MenuUploadRetryCache()
        var preparations = 0
        val selection = listOf(SelectedMenuImage("content://a", "a.jpg"))
        val fakePreparer: suspend (SelectedMenuImage) -> PreparedMenuImage = {
            preparations++
            PreparedMenuImage("a.jpg", "image/jpeg",
                byteArrayOf(0xff.toByte(), 0xd8.toByte(), 0xff.toByte(), preparations.toByte()))
        }
        val first = cache.prepareIfNeeded(selection, fakePreparer)
        val key = cache.key { "request-123" }
        // The HTTP response was lost; user presses retry with same selection.
        val second = cache.prepareIfNeeded(selection, fakePreparer)
        assertSame(first, second)
        assertEquals(1, preparations)
        assertEquals(key, cache.key { "request-should-not-change" })
        assertEquals(first[0].bytes.toList(), second[0].bytes.toList())
    }

    @Test fun keyConflictChangesOnlyKeyAndExplicitNewAttemptDropsCachedPayload() = runBlocking {
        val cache = MenuUploadRetryCache()
        val photos = listOf(SelectedMenuImage("content://a", "a.jpg"))
        var count = 0
        val prep: suspend (SelectedMenuImage) -> PreparedMenuImage = {
            count++
            PreparedMenuImage("a.jpg", "image/jpeg",
                byteArrayOf(0xff.toByte(), 0xd8.toByte(), 0xff.toByte()))
        }
        val first = cache.prepareIfNeeded(photos, prep)
        assertEquals("key-a", cache.key { "key-a" })
        cache.discardKey()
        assertEquals("key-b", cache.key { "key-b" })
        assertSame(first, cache.prepareIfNeeded(photos, prep))
        cache.clear()
        val after = cache.prepareIfNeeded(photos, prep)
        assertNotEquals(first, after)
        assertEquals(2, count)
        assertEquals("key-c", cache.key { "key-c" })
    }
}
