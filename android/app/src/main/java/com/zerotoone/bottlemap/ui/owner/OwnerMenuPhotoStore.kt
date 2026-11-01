package com.zerotoone.bottlemap.ui.owner

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import com.zerotoone.bottlemap.data.owner.MockPhoto
import com.zerotoone.bottlemap.data.owner.MockPhotoKind
import java.io.File
import java.io.FileOutputStream
import java.util.UUID

internal const val OWNER_MENU_MAX_PHOTOS = 15
internal const val OWNER_MENU_MAX_PHOTO_BYTES = 10L * 1024L * 1024L
internal const val OWNER_MENU_MAX_TOTAL_BYTES = 60L * 1024L * 1024L
internal const val OWNER_MENU_MAX_EXTRACTED_PRICE_KRW = 99_999_999

/** Validation is deliberately independent of Android storage for JVM tests. */
internal fun validateMenuPhotoSizes(sizes: List<Long>): String? = when {
    sizes.isEmpty() -> "메뉴판 사진을 한 장 이상 선택해 주세요."
    sizes.size > OWNER_MENU_MAX_PHOTOS -> "사진은 최대 15장까지 선택할 수 있어요."
    sizes.any { it <= 0L } -> "읽을 수 없는 사진이 있어요. 다시 선택해 주세요."
    sizes.any { it > OWNER_MENU_MAX_PHOTO_BYTES } -> "사진 한 장은 최대 10MB까지 가능해요."
    sizes.sum() > OWNER_MENU_MAX_TOTAL_BYTES -> "전체 사진은 60MB 이하여야 해요."
    else -> null
}

internal fun menuPhotoSignature(bytes: ByteArray): String? = when {
    bytes.size >= 3 &&
        (bytes[0].toInt() and 255) == 0xff &&
        (bytes[1].toInt() and 255) == 0xd8 &&
        (bytes[2].toInt() and 255) == 0xff -> "image/jpeg"
    bytes.size >= 8 &&
        bytes.take(8).map { it.toInt() and 255 } ==
            listOf(137, 80, 78, 71, 13, 10, 26, 10) -> "image/png"
    else -> null
}

/**
 * Stage 7 owns app-private *no-backup* copies. Image bytes never enter
 * ViewModel/SavedState, a repository snapshot, Git or a public URL.
 * Copy on Dispatchers.IO; a transient Photo Picker grant is then sufficient.
 */
internal class OwnerMenuPhotoStore(context: Context) {
    private val app = context.applicationContext
    private val dir = File(app.noBackupFilesDir, "owner-menu-photo-drafts").apply { mkdirs() }

    fun isReadable(photo: MockPhoto): Boolean = try {
        val file = fileFor(photo)
        file.isFile && file.canRead() &&
            file.length() in 1..OWNER_MENU_MAX_PHOTO_BYTES &&
            file.inputStream().use { input ->
                val magic = ByteArray(8)
                menuPhotoSignature(magic.copyOf(input.read(magic).coerceAtLeast(0))) != null
            }
    } catch (_: Exception) { false }

    fun size(photo: MockPhoto): Long = fileFor(photo).length()

    private fun fileFor(photo: MockPhoto): File {
        val path = Uri.parse(photo.uri).path ?: error("사진 경로가 없어요.")
        val file = File(path).canonicalFile
        require(file.parentFile == dir.canonicalFile) { "앱 내부 사진이 아닙니다." }
        return file
    }

    /**
     * Atomic batch addition: any URI/size/type failure removes all new files
     * from this selection, leaving the previous ordered photo list unchanged.
     */
    fun add(existing: List<MockPhoto>, sources: List<Uri>): List<MockPhoto> {
        require(existing.size + sources.size <= OWNER_MENU_MAX_PHOTOS) {
            "사진은 최대 15장까지 선택할 수 있어요."
        }
        val created = mutableListOf<File>()
        var completed = false
        var total = existing.sumOf(::size)
        try {
            val additions = sources.map { uri ->
                val declared = app.contentResolver.getType(uri)
                require(declared == null || declared == "image/jpeg" || declared == "image/png") {
                    "JPEG 또는 PNG 사진만 올릴 수 있어요."
                }
                val photoId = UUID.randomUUID().toString()
                val temp = File(dir, "$photoId.part")
                created += temp
                val length = app.contentResolver.openInputStream(uri)?.use { source ->
                    FileOutputStream(temp).use { sink ->
                        val buffer = ByteArray(16 * 1024)
                        var count = 0L
                        while (true) {
                            val n = source.read(buffer)
                            if (n < 0) break
                            count += n
                            require(count <= OWNER_MENU_MAX_PHOTO_BYTES) {
                                "사진 한 장은 최대 10MB까지 가능해요."
                            }
                            require(total + count <= OWNER_MENU_MAX_TOTAL_BYTES) {
                                "전체 사진은 60MB 이하여야 해요."
                            }
                            sink.write(buffer, 0, n)
                        }
                        count
                    }
                } ?: error("사진 URI를 읽을 수 없어요. 다시 선택해 주세요.")
                require(length > 0) { "빈 사진은 등록할 수 없어요." }
                val magic = temp.inputStream().use { input ->
                    ByteArray(8).let { it.copyOf(input.read(it).coerceAtLeast(0)) }
                }
                val signature = menuPhotoSignature(magic)
                require(signature != null && (declared == null || declared == signature)) {
                    "JPEG 또는 PNG 사진만 올릴 수 있어요."
                }
                val dimensions = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeFile(temp.absolutePath, dimensions)
                require(dimensions.outWidth > 0 && dimensions.outHeight > 0) {
                    "사진을 읽을 수 없어요. 다시 선택해 주세요."
                }
                val stored = File(dir, "$photoId.${if (signature == "image/png") "png" else "jpg"}")
                require(temp.renameTo(stored)) { "사진을 보관하지 못했어요." }
                created += stored
                created.remove(temp)
                total += length
                MockPhoto(photoId, Uri.fromFile(stored).toString(), MockPhotoKind.MENU_CAPTURE)
            }
            require(validateMenuPhotoSizes((existing + additions).map(::size)) == null) {
                validateMenuPhotoSizes((existing + additions).map(::size)).orEmpty()
            }
            completed = true
            return existing + additions
        } catch (oom: OutOfMemoryError) {
            throw IllegalStateException("사진을 처리할 메모리가 부족해요. 사진을 줄여 다시 선택해 주세요.")
        } finally {
            // A failed batch must never retain partial or successfully copied
            // images from the same selection. Earlier selected photos survive.
            if (!completed) created.forEach { it.delete() }
            else created.filter { it.extension == "part" }.forEach { it.delete() }
        }
    }

    fun delete(photo: MockPhoto) {
        runCatching { fileFor(photo).delete() }
    }

    fun preview(photo: MockPhoto, size: Int = 320): android.graphics.Bitmap? {
        if (!isReadable(photo)) return null
        val path = fileFor(photo).absolutePath
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(path, bounds)
        var sample = 1
        while (bounds.outWidth / sample > size * 2 ||
            bounds.outHeight / sample > size * 2) sample *= 2
        return BitmapFactory.decodeFile(path,
            BitmapFactory.Options().apply { inSampleSize = sample })
    }
}
