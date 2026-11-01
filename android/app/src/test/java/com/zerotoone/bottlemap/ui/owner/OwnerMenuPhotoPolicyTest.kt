package com.zerotoone.bottlemap.ui.owner

import org.junit.Assert.*
import org.junit.Test

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

    @Test fun jpegAndPngMagicAreAcceptedButUnsupportedFormatsRejected() {
        assertEquals("image/jpeg", menuPhotoSignature(byteArrayOf(
            0xff.toByte(), 0xd8.toByte(), 0xff.toByte(), 0x00, 0x00, 0x00, 0x00, 0x00)))
        assertEquals("image/png", menuPhotoSignature(byteArrayOf(
            137.toByte(), 80, 78, 71, 13, 10, 26, 10)))
        assertNull(menuPhotoSignature(byteArrayOf(0x52, 0x49, 0x46, 0x46)))
        assertNull(menuPhotoSignature(byteArrayOf()))
    }
}
