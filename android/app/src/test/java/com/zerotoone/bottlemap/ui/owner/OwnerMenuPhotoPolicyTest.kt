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

    @Test fun jpegAndPngMagicAreAcceptedButUnsupportedFormatsRejected() {
        assertEquals("image/jpeg", menuPhotoSignature(byteArrayOf(
            0xff.toByte(), 0xd8.toByte(), 0xff.toByte(), 0x00, 0x00, 0x00, 0x00, 0x00)))
        assertEquals("image/png", menuPhotoSignature(byteArrayOf(
            137.toByte(), 80, 78, 71, 13, 10, 26, 10)))
        assertNull(menuPhotoSignature(byteArrayOf(0x52, 0x49, 0x46, 0x46)))
        assertNull(menuPhotoSignature(byteArrayOf()))
    }
}
