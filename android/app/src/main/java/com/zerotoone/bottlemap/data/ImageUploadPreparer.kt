// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.data

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import android.provider.OpenableColumns
import androidx.exifinterface.media.ExifInterface
import java.io.ByteArrayOutputStream
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val MAX_IMAGE_BYTES = 10 * 1024 * 1024
private const val MAX_DECODE_DIMENSION = 2400

data class PreparedMenuImage(
    val filename: String,
    val mimeType: String,
    val bytes: ByteArray,
)

data class SelectedMenuImage(
    val uri: String,
    val displayName: String,
)

class ImageUploadPreparer(
    private val contentResolver: ContentResolver,
) {
    suspend fun describe(uri: Uri): SelectedMenuImage = withContext(Dispatchers.IO) {
        SelectedMenuImage(
            uri = uri.toString(),
            displayName = queryDisplayName(uri) ?: "menu-photo",
        )
    }

    suspend fun prepare(uri: Uri): PreparedMenuImage = withContext(Dispatchers.IO) {
        val displayName = queryDisplayName(uri) ?: "menu-photo"
        val declaredType = contentResolver.getType(uri)?.lowercase()
        val orientation = readOrientation(uri)

        if (declaredType == "image/jpeg" || declaredType == "image/png") {
            val direct = readAtMost(uri, MAX_IMAGE_BYTES + 1)
            val signatureMatches = when (declaredType) {
                "image/jpeg" -> isJpeg(direct)
                "image/png" -> isPng(direct)
                else -> false
            }
            val orientationIsSafe = declaredType == "image/png" ||
                orientation == ExifInterface.ORIENTATION_NORMAL ||
                orientation == ExifInterface.ORIENTATION_UNDEFINED
            if (direct.size <= MAX_IMAGE_BYTES && signatureMatches && orientationIsSafe) {
                return@withContext PreparedMenuImage(
                    filename = displayName,
                    mimeType = declaredType,
                    bytes = direct,
                )
            }
        }

        val bitmap = decodeSampled(uri)
        val oriented = applyOrientation(bitmap, orientation)
        if (oriented !== bitmap) {
            bitmap.recycle()
        }

        try {
            val bytes = compressWithinLimit(oriented)
            PreparedMenuImage(
                filename = displayName.substringBeforeLast('.', displayName) + ".jpg",
                mimeType = "image/jpeg",
                bytes = bytes,
            )
        } finally {
            oriented.recycle()
        }
    }

    private fun queryDisplayName(uri: Uri): String? =
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
            ?.use { cursor ->
                if (!cursor.moveToFirst()) return@use null
                val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (index >= 0) cursor.getString(index) else null
            }

    private fun readAtMost(uri: Uri, limit: Int): ByteArray {
        val stream = contentResolver.openInputStream(uri)
            ?: throw IOException("Unable to open the selected image.")
        return stream.use { input ->
            val output = ByteArrayOutputStream(minOf(limit, 1024 * 1024))
            val buffer = ByteArray(64 * 1024)
            var total = 0
            while (total < limit) {
                val read = input.read(buffer, 0, minOf(buffer.size, limit - total))
                if (read < 0) break
                output.write(buffer, 0, read)
                total += read
            }
            output.toByteArray()
        }
    }

    private fun decodeSampled(uri: Uri): Bitmap {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        // With inJustDecodeBounds the call fills `bounds` and always returns null.
        val stream = contentResolver.openInputStream(uri)
            ?: throw IOException("Unable to inspect the selected image.")
        stream.use { BitmapFactory.decodeStream(it, null, bounds) }

        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
            throw IOException("This image format cannot be decoded on this device.")
        }

        var sampleSize = 1
        while (
            bounds.outWidth / sampleSize > MAX_DECODE_DIMENSION ||
            bounds.outHeight / sampleSize > MAX_DECODE_DIMENSION
        ) {
            sampleSize *= 2
        }

        val options = BitmapFactory.Options().apply {
            inSampleSize = sampleSize
            inPreferredConfig = Bitmap.Config.ARGB_8888
        }
        return contentResolver.openInputStream(uri)?.use {
            BitmapFactory.decodeStream(it, null, options)
        } ?: throw IOException("This image format cannot be decoded on this device.")
    }

    private fun readOrientation(uri: Uri): Int =
        runCatching {
            contentResolver.openInputStream(uri)?.use {
                ExifInterface(it).getAttributeInt(
                    ExifInterface.TAG_ORIENTATION,
                    ExifInterface.ORIENTATION_NORMAL,
                )
            }
        }.getOrNull() ?: ExifInterface.ORIENTATION_NORMAL

    private fun applyOrientation(bitmap: Bitmap, orientation: Int): Bitmap {
        val matrix = Matrix()
        when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
            ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
            ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.postScale(-1f, 1f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> matrix.postScale(1f, -1f)
            ExifInterface.ORIENTATION_TRANSPOSE -> {
                matrix.postRotate(90f)
                matrix.postScale(-1f, 1f)
            }
            ExifInterface.ORIENTATION_TRANSVERSE -> {
                matrix.postRotate(270f)
                matrix.postScale(-1f, 1f)
            }
            else -> return bitmap
        }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
    }

    private fun isJpeg(bytes: ByteArray): Boolean =
        bytes.size >= 3 &&
            bytes[0] == 0xFF.toByte() &&
            bytes[1] == 0xD8.toByte() &&
            bytes[2] == 0xFF.toByte()

    private fun isPng(bytes: ByteArray): Boolean {
        val signature = byteArrayOf(
            0x89.toByte(),
            0x50,
            0x4E,
            0x47,
            0x0D,
            0x0A,
            0x1A,
            0x0A,
        )
        return bytes.size >= signature.size &&
            signature.indices.all { bytes[it] == signature[it] }
    }

    private fun compressWithinLimit(bitmap: Bitmap): ByteArray {
        var quality = 90
        val output = ByteArrayOutputStream()
        while (quality >= 60) {
            output.reset()
            if (!bitmap.compress(Bitmap.CompressFormat.JPEG, quality, output)) {
                throw IOException("Failed to convert the selected image to JPEG.")
            }
            if (output.size() <= MAX_IMAGE_BYTES) {
                return output.toByteArray()
            }
            quality -= 10
        }
        throw IOException("The menu photo is still larger than 10 MB after conversion.")
    }
}
