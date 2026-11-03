package com.zerotoone.bottlemap.data.owner

import java.io.File
import java.security.MessageDigest

/**
 * New-bar representative photo bridge for the existing backend contract.
 * Owner applications cannot accept a cover image; the approved bar can.
 *
 * Only the normalized JPEG is saved in the app's noBackupFilesDir. No business
 * number, user id or application id appears in a filename or preferences.
 * A staged draft is recovered by the server application's business number
 * if Android is killed between a successful POST and attachment.
 */
internal class PendingOwnerCoverStore(private val root: File) {
    private fun folder(): File = File(root, "owner-application-covers").also {
        check(it.isDirectory || it.mkdirs()) { "대표 사진 보관 공간을 만들지 못했어요." }
    }

    private fun key(user: String, kind: String, identity: String): String {
        val bytes = "$user|$kind|$identity".toByteArray(Charsets.UTF_8)
        return MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") {
            "%02x".format(it.toInt() and 0xff)
        }
    }

    private fun draftFile(user: String, businessNumber: String) =
        File(folder(), key(user, "draft", businessNumber) + ".jpg")

    private fun applicationFile(user: String, applicationId: String) =
        File(folder(), key(user, "application", applicationId) + ".jpg")

    @Synchronized
    fun stage(user: String, businessNumber: String, jpeg: ByteArray) {
        require(jpeg.size in 1..2_097_152) { "대표 사진은 2MB 이하여야 해요." }
        require(jpeg.size > 2 && jpeg[0] == 0xff.toByte() && jpeg[1] == 0xd8.toByte()) {
            "대표 사진은 JPEG 형식이어야 해요."
        }
        val dest = draftFile(user, businessNumber)
        val tmp = File.createTempFile("cover-", ".tmp", folder())
        try {
            tmp.outputStream().use { it.write(jpeg) }
            if(!tmp.renameTo(dest)) {
                tmp.copyTo(dest, overwrite = true)
            }
        } finally {
            tmp.delete()
        }
    }

    @Synchronized
    fun attach(user: String, businessNumber: String, applicationId: String) {
        val source = draftFile(user, businessNumber)
        if(!source.isFile) return
        val destination = applicationFile(user, applicationId)
        if(!source.renameTo(destination)) {
            source.copyTo(destination, overwrite = true)
            source.delete()
        }
    }

    @Synchronized
    fun read(user: String, applicationId: String): ByteArray? =
        applicationFile(user, applicationId).takeIf {
            it.isFile && it.length() in 1..2_097_152
        }?.readBytes()

    @Synchronized
    fun remove(user: String, applicationId: String, businessNumber: String? = null) {
        applicationFile(user, applicationId).delete()
        if(businessNumber != null) draftFile(user, businessNumber).delete()
    }
}
