// I2 A15: FileProvider-backed, app-private JPEG capture files; Developer flavor only.
package com.zerotoone.bottlemap.data

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.core.content.FileProvider
import java.io.File
import java.io.IOException
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val CAMERA_DIRECTORY = "owner-menu-captures"
private const val PROVIDER_SUFFIX = ".owner.camera.provider"
private val CAPTURE_NAME = Regex("menu-[0-9a-f-]{36}\\.jpg")

/**
 * URI is shared only with the system camera via TakePicture's temporary URI permission.
 * The underlying JPEG remains private to the Developer app; no public gallery write.
 */
class OwnerCameraPhotoStorage(private val context: Context) : CameraPhotoStorage {
    private val captureDirectory: File
        get() = File(context.filesDir, CAMERA_DIRECTORY)
    private val authority: String
        get() = context.packageName + PROVIDER_SUFFIX

    override fun create(): CameraPhoto {
        val directory = captureDirectory
        if (!directory.isDirectory && !directory.mkdirs()) {
            throw IOException("Unable to create private camera directory; check available storage.")
        }
        val file = File(directory, "menu-${UUID.randomUUID()}.jpg")
        if (!file.createNewFile()) throw IOException("Unable to reserve camera output file.")
        return CameraPhoto(file.name, fileUri(file).toString())
    }

    override fun restore(fileName: String): CameraPhoto? {
        val file = ownedFile(fileName) ?: return null
        return CameraPhoto(fileName, fileUri(file).toString())
    }

    override suspend fun validate(photo: CameraPhoto): Unit = withContext(Dispatchers.IO) {
        val file = ownedFile(photo.fileName)
            ?: throw IOException("Camera output filename is invalid.")
        if (!file.isFile || file.length() < 4L) {
            throw IOException("The camera did not save a photo or the file is empty.")
        }
        val header = ByteArray(3)
        file.inputStream().use { stream ->
            if (stream.read(header) != header.size ||
                header[0] != 0xff.toByte() ||
                header[1] != 0xd8.toByte() ||
                header[2] != 0xff.toByte()
            ) throw IOException("The camera output is not a JPEG image.")
        }
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
            throw IOException("The camera output is damaged or cannot be decoded.")
        }
        // Verify the same content URI used by A14's image preparer is still accessible.
        val opened = context.contentResolver.openInputStream(Uri.parse(photo.uri))
            ?: throw IOException("The captured photo URI can no longer be opened.")
        opened.use { if (it.read() < 0) throw IOException("The captured photo is empty.") }
    }

    override fun delete(photo: CameraPhoto) {
        ownedFile(photo.fileName)?.delete()
    }

    /** Never touch a gallery URI; only a URI matching one of our own FileProvider files. */
    override fun deleteIfOwned(uri: String) {
        captureDirectory.listFiles().orEmpty().forEach { file ->
            if (ownedFile(file.name) != null && fileUri(file).toString() == uri) {
                file.delete()
            }
        }
    }

    /** Collect abandoned attempts, but never touch recent files or state-restored selections. */
    fun pruneOldOrphans(keepUris: Set<String>, cutoffMillis: Long) {
        captureDirectory.listFiles().orEmpty().forEach { file ->
            if (ownedFile(file.name) != null &&
                file.lastModified() < cutoffMillis &&
                fileUri(file).toString() !in keepUris
            ) file.delete()
        }
    }

    private fun ownedFile(fileName: String): File? {
        if (!CAPTURE_NAME.matches(fileName)) return null
        return File(captureDirectory, fileName)
    }

    private fun fileUri(file: File): Uri =
        FileProvider.getUriForFile(context, authority, file)
}
