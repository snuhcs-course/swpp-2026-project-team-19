package com.zerotoone.bottlemap.ui.owner

import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.nio.file.Files

class OwnerMenuPhotoPolicyTest {
    @Test fun countAndSizeBoundariesCoverZeroOneFifteenSixteen() {
        assertNotNull(validateMenuPhotoSizes(emptyList()))
        assertNull(validateMenuPhotoSizes(listOf(1L)))
        assertNull(validateMenuPhotoSizes(List(15) { 1L }))
        assertNotNull(validateMenuPhotoSizes(List(16) { 1L }))
        assertNull(validateMenuPhotoSizes(List(6) { 10L * 1024 * 1024 }))
        assertNotNull(validateMenuPhotoSizes(List(7) { 10L * 1024 * 1024 }))
        assertNotNull(validateMenuPhotoSizes(listOf(10L * 1024 * 1024 + 1)))
        assertNotNull(validateMenuPhotoSizes(listOf(0L)))
        assertNotNull(validateMenuPhotoSizes(listOf(-1L)))
    }

    @Test fun recoveryRemovesInterruptedCopiesButPreservesStoredAndActiveImages() {
        val dir=Files.createTempDirectory("owner-menu-recovery").toFile()
        try {
            val abandoned=File(dir,"old.part").apply { writeText("private data") }
            val oriented=File(dir,"old.oriented").apply { writeText("private data") }
            val active=File(dir,"active.part").apply { writeText("still copying") }
            val stored=File(dir,"persisted.jpg").apply { writeText("published/reference") }
            assertEquals(2,removeInterruptedMenuPhotoArtifacts(dir,setOf(active.absolutePath)))
            assertFalse(abandoned.exists())
            assertFalse(oriented.exists())
            assertTrue(active.exists())
            assertTrue(stored.exists())
            assertEquals(1,removeInterruptedMenuPhotoArtifacts(dir))
            assertFalse(active.exists())
            assertTrue(stored.exists())
        } finally { dir.deleteRecursively() }
    }

    @Test fun orphanCameraFilesAreDeletedWithoutTouchingLiveCaptures() {
        val dir=Files.createTempDirectory("owner-menu-capture-recovery").toFile()
        try {
            val orphan=File(dir,"menu-capture-stale.jpg").apply {writeText("private")}
            val active=File(dir,"menu-capture-active.jpg").apply {writeText("active")}
            val other=File(dir,"unrelated.jpg").apply {writeText("keep")}
            assertEquals(1,removeAbandonedOwnerCaptures(dir,setOf(active.absolutePath)))
            assertFalse(orphan.exists())
            assertTrue(active.exists())
            assertTrue(other.exists())
            assertEquals(1,removeAbandonedOwnerCaptures(dir,emptySet()))
            assertFalse(active.exists())
            assertTrue(other.exists())
        } finally {dir.deleteRecursively()}
    }

    @Test fun priorProcessOrphanFinalsAreReconciledWithRetainedAndLivePhotos() {
        val dir=Files.createTempDirectory("owner-photo-final-recovery").toFile()
        try {
            val orphan=File(dir,"00000000-0000-4000-8000-000000000001.jpg")
                .apply {writeText("orphan")}
            val retained=File(dir,"00000000-0000-4000-8000-000000000002.png")
                .apply {writeText("saved picker/import")}
            val active=File(dir,"00000000-0000-4000-8000-000000000003.jpg")
                .apply {writeText("being copied")}
            val unrelated=File(dir,"user-provided.jpg").apply {writeText("not managed")}
            assertEquals(1,removeUnreferencedOwnerPhotoFiles(dir,
                setOf(retained.absolutePath),setOf(active.absolutePath)))
            assertFalse(orphan.exists())
            assertTrue(retained.exists())
            assertTrue(active.exists())
            assertTrue(unrelated.exists())
        } finally {dir.deleteRecursively()}
    }

    @Test fun recoveryGuardPreservesCaptureCreatedAfterPriorProtectionSnapshot() {
        val dir=Files.createTempDirectory("owner-camera-lock-recovery").toFile()
        try {
            val capture=File(dir,"menu-capture-new.jpg").apply{writeText("active")}
            synchronized(OwnerMenuCaptureGuard.lock) {
                OwnerMenuCaptureGuard.livePaths += capture.absolutePath
                assertEquals(0,removeAbandonedOwnerCaptures(dir,
                    OwnerMenuCaptureGuard.livePaths))
            }
            assertTrue(capture.exists())
            synchronized(OwnerMenuCaptureGuard.lock) {
                OwnerMenuCaptureGuard.livePaths.remove(capture.absolutePath)
            }
            assertEquals(1,removeAbandonedOwnerCaptures(dir,emptySet()))
        } finally {dir.deleteRecursively()}
    }

    @Test fun jpegAndPngMagicAreAcceptedButUnsupportedFormatsRejected() {
        assertEquals("image/jpeg", menuPhotoSignature(byteArrayOf(
            0xff.toByte(), 0xd8.toByte(), 0xff.toByte(), 0x00, 0x00, 0x00, 0x00, 0x00)))
        assertEquals("image/png", menuPhotoSignature(byteArrayOf(
            137.toByte(), 80, 78, 71, 13, 10, 26, 10)))
        assertNull(menuPhotoSignature(byteArrayOf(0x52, 0x49, 0x46, 0x46)))
        assertNull(menuPhotoSignature(byteArrayOf()))
    }
}
