package com.zerotoone.bottlemap.data.owner

import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class PendingOwnerCoverStoreTest {
    @get:Rule val temp = TemporaryFolder()
    private val jpeg = byteArrayOf(0xff.toByte(), 0xd8.toByte(), 1, 2, 3, 0xff.toByte(), 0xd9.toByte())

    @Test fun coverSurvivesProcessRestartAndIsScopedToOwnerAndApplication() {
        val first = PendingOwnerCoverStore(temp.root)
        first.stage("owner-a", "1234567891", jpeg)
        first.attach("owner-a", "1234567891", "application-1")
        val restored = PendingOwnerCoverStore(temp.root)
        assertArrayEquals(jpeg, restored.read("owner-a", "application-1"))
        assertNull(restored.read("owner-b", "application-1"))
        assertNull(restored.read("owner-a", "application-2"))
        val filenames = temp.root.walkTopDown().filter { it.isFile }.map { it.name }.toList()
        assertTrue(filenames.all { "1234567891" !in it && "owner-a" !in it })
    }

    @Test fun responseLossCanBeRecoveredByMatchingDraftToApplication() {
        val beforePost = PendingOwnerCoverStore(temp.root)
        beforePost.stage("owner-a", "1234567891", jpeg)
        // HTTP 201 succeeded, but Android process was killed before receiving its id.
        val afterRestart = PendingOwnerCoverStore(temp.root)
        afterRestart.attach("owner-a", "1234567891", "recovered-application")
        assertArrayEquals(jpeg, afterRestart.read("owner-a", "recovered-application"))
    }

    @Test fun cancellationRemovesOnlyCorrectOwnersPendingPhoto() {
        val store = PendingOwnerCoverStore(temp.root)
        store.stage("owner-a", "1234567891", jpeg)
        store.stage("owner-b", "1234567891", jpeg)
        store.attach("owner-a", "1234567891", "app-a")
        store.attach("owner-b", "1234567891", "app-b")
        store.remove("owner-a", "app-a", "1234567891")
        assertNull(store.read("owner-a", "app-a"))
        assertArrayEquals(jpeg, store.read("owner-b", "app-b"))
    }

    @Test fun nonJpegAndTooLargePhotosAreRejectedBeforeSubmission() {
        val store = PendingOwnerCoverStore(temp.root)
        assertThrows(IllegalArgumentException::class.java) {
            store.stage("owner", "123", byteArrayOf(1,2,3))
        }
        assertThrows(IllegalArgumentException::class.java) {
            store.stage("owner", "123", ByteArray(2_097_153).apply {
                this[0]=0xff.toByte(); this[1]=0xd8.toByte()
            })
        }
    }
}
