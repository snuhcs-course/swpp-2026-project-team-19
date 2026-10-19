// I2 A15: Fake capture storage; no physical camera, files, or network services.
package com.zerotoone.bottlemap.data

import java.io.IOException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraCaptureSessionTest {
    private class FakeCameraStorage : CameraPhotoStorage {
        private var counter = 0
        val files = linkedMapOf<String, Boolean>()
        val deleted = mutableListOf<String>()
        override fun create(): CameraPhoto {
            val name = "capture-" + (++counter) + ".jpg"
            files[name] = false // pending file is initially empty
            return CameraPhoto(name, "content://camera/" + name)
        }
        override fun restore(fileName: String): CameraPhoto? =
            if (fileName in files) CameraPhoto(fileName, "content://camera/" + fileName) else null
        override suspend fun validate(photo: CameraPhoto) {
            if (files[photo.fileName] != true) throw IOException("Empty or invalid camera JPEG.")
        }
        override fun delete(photo: CameraPhoto) {
            files.remove(photo.fileName)
            deleted.add(photo.fileName)
        }
        override fun deleteIfOwned(uri: String) {
            files.keys.firstOrNull { "content://camera/" + it == uri }?.let { key ->
                delete(CameraPhoto(key, uri))
            }
        }
        fun take(photo: CameraPhoto) { files[photo.fileName] = true }
    }

    private fun selected(photo: CameraPhoto) = SelectedMenuImage(photo.uri, photo.fileName)
    private fun gallery(id: String) = SelectedMenuImage("content://gallery/" + id, "menu-" + id + ".jpg")

    @Test fun successfulCaptureNeedsUserAcceptanceThenAddsToExistingGallery() = runBlocking {
        val store = FakeCameraStorage()
        val capture = CameraCaptureSession(store)
        val pending = capture.start()
        assertEquals(pending, capture.pending)
        store.take(pending)
        assertEquals(CameraCaptureResult.PreviewReady(pending), capture.finish(true))
        assertNull(capture.pending)
        assertEquals(pending, capture.preview)
        val photo = (capture.accept() as CameraCaptureResult.Accepted).photo
        val selected = appendMenuPhotos(listOf(gallery("a")), listOf(selected(photo))).images
        assertEquals(listOf(gallery("a"), selected(photo)), selected)
        assertNull(capture.preview)
        assertTrue(photo.fileName in store.files)
    }

    @Test fun cameraCancelDeletesOnlyDraftAndPreservesGalleryBatch() = runBlocking {
        val store = FakeCameraStorage()
        val capture = CameraCaptureSession(store)
        val selected = listOf(gallery("a"), gallery("b"))
        val photo = capture.start()
        assertEquals(CameraCaptureResult.Canceled, capture.finish(false))
        assertEquals(selected, appendMenuPhotos(selected, emptyList()).images)
        assertFalse(store.files.containsKey(photo.fileName))
    }

    @Test fun failedOrEmptyCameraOutputIsRejectedAndDeleted() = runBlocking {
        val store = FakeCameraStorage()
        val capture = CameraCaptureSession(store)
        val pending = capture.start()
        assertTrue(capture.finish(true) is CameraCaptureResult.Invalid)
        assertNull(capture.preview)
        assertFalse(store.files.containsKey(pending.fileName))
    }

    @Test fun retakeCancelKeepsOldPreviewWithoutDeletingPreviousAcceptedPhotos() = runBlocking {
        val store = FakeCameraStorage()
        val capture = CameraCaptureSession(store)
        val accepted = store.create().also { store.take(it) }
        val selected = listOf(gallery("a"), selected(accepted))
        val first = capture.start()
        store.take(first)
        capture.finish(true)
        val retake = capture.retake()
        assertNotEquals(first.fileName, retake.fileName)
        assertEquals(CameraCaptureResult.Canceled, capture.finish(false))
        assertEquals(first, capture.preview)
        assertEquals(selected, selected)
        assertTrue(first.fileName in store.files)
        assertTrue(accepted.fileName in store.files)
    }

    @Test fun successfulRetakeReplacesOnlyUnconfirmedPreview() = runBlocking {
        val store = FakeCameraStorage()
        val capture = CameraCaptureSession(store)
        val first = capture.start()
        store.take(first)
        capture.finish(true)
        val second = capture.retake()
        store.take(second)
        assertEquals(CameraCaptureResult.PreviewReady(second), capture.finish(true))
        assertFalse(store.files.containsKey(first.fileName))
        assertEquals(second, capture.preview)
        assertEquals(CameraCaptureResult.Accepted(second), capture.accept())
    }

    @Test fun failedRetakePreservesPriorPreview() = runBlocking {
        val store = FakeCameraStorage()
        val capture = CameraCaptureSession(store)
        val first = capture.start()
        store.take(first)
        capture.finish(true)
        val retake = capture.retake()
        assertTrue(capture.finish(true) is CameraCaptureResult.Invalid)
        assertFalse(store.files.containsKey(retake.fileName))
        assertEquals(first, capture.preview)
    }

    @Test fun fiveMixedPhotosPreserveSelectionOrderAndEnforceLimit() = runBlocking {
        val store = FakeCameraStorage()
        val capture = CameraCaptureSession(store)
        var selected = appendMenuPhotos(emptyList(), listOf(gallery("a"), gallery("b"))).images
        repeat(3) {
            val photo = capture.start()
            store.take(photo)
            capture.finish(true)
            val accepted = (capture.accept() as CameraCaptureResult.Accepted).photo
            selected = appendMenuPhotos(selected, listOf(selected(accepted))).images
        }
        assertEquals(5, selected.size)
        assertEquals(listOf("menu-a.jpg", "menu-b.jpg", "capture-1.jpg",
            "capture-2.jpg", "capture-3.jpg"), selected.map { it.displayName })
        assertEquals(1, appendMenuPhotos(selected, listOf(gallery("c"))).overLimit)
    }

    @Test fun duplicateCameraPhotoIsNotInsertedTwice() = runBlocking {
        val store = FakeCameraStorage()
        val capture = CameraCaptureSession(store)
        val photo = capture.start()
        store.take(photo)
        capture.finish(true)
        val confirmed = (capture.accept() as CameraCaptureResult.Accepted).photo
        val first = appendMenuPhotos(emptyList(), listOf(selected(confirmed))).images
        val repeated = appendMenuPhotos(first, listOf(selected(confirmed)))
        assertEquals(1, repeated.duplicates)
        assertEquals(first, repeated.images)
    }

    @Test fun removalDeletesOwnPhotoButNeverDeletesExternalGallery() = runBlocking {
        val store = FakeCameraStorage()
        val capture = CameraCaptureSession(store)
        val photo = capture.start()
        store.take(photo)
        capture.finish(true)
        capture.accept()
        val selected = listOf(gallery("a"), selected(photo))
        capture.deleteIfOwned(gallery("a").uri)
        assertTrue(photo.fileName in store.files)
        capture.deleteIfOwned(photo.uri)
        assertEquals(listOf(gallery("a")), removeMenuPhoto(selected, photo.uri))
        assertFalse(store.files.containsKey(photo.fileName))
    }

    @Test fun fileNameCanRestorePendingOutputAfterProcessRecreation() = runBlocking {
        val store = FakeCameraStorage()
        val earlier = CameraCaptureSession(store)
        val pending = earlier.start()
        store.take(pending)
        val restored = CameraCaptureSession(store, restoredPending = store.restore(pending.fileName))
        assertEquals(pending, restored.pending)
        assertEquals(CameraCaptureResult.PreviewReady(pending), restored.finish(true))
        assertEquals(pending, restored.preview)
    }

    @Test fun restoredPreviewCanStillBeUsedOrDiscarded() = runBlocking {
        val store = FakeCameraStorage()
        val earlier = CameraCaptureSession(store)
        val pending = earlier.start()
        store.take(pending)
        earlier.finish(true)
        val restored = CameraCaptureSession(store, restoredPreview = store.restore(pending.fileName))
        assertEquals(CameraCaptureResult.Accepted(pending), restored.accept())
        val next = restored.start()
        store.take(next)
        restored.finish(true)
        restored.discardPreview()
        assertFalse(store.files.containsKey(next.fileName))
    }

    @Test fun launchFailureDiscardsPendingAndAllowsNewCapture() {
        val store = FakeCameraStorage()
        val capture = CameraCaptureSession(store)
        val pending = capture.start()
        capture.discardPending()
        assertFalse(store.files.containsKey(pending.fileName))
        assertNull(capture.pending)
        val retry = capture.start()
        assertNotEquals(pending.fileName, retry.fileName)
    }

    @Test fun preventsConcurrentCaptureWhileOutputIsPending() {
        val capture = CameraCaptureSession(FakeCameraStorage())
        capture.start()
        assertThrows(IllegalStateException::class.java) { capture.start() }
    }

    @Test fun noPendingResultCannotEraseSelectedPhotos() = runBlocking {
        val capture = CameraCaptureSession(FakeCameraStorage())
        assertEquals(CameraCaptureResult.NoPendingCapture, capture.finish(false))
        assertEquals(CameraCaptureResult.NoPendingCapture, capture.accept())
    }
}
