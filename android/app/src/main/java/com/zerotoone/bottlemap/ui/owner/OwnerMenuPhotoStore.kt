package com.zerotoone.bottlemap.ui.owner

import android.content.Context
import android.graphics.BitmapFactory
import android.graphics.Bitmap
import android.graphics.Matrix
import androidx.exifinterface.media.ExifInterface
import android.graphics.ImageDecoder
import android.os.Build
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
/** Recover incomplete private copies; never touch successfully stored JPG/PNG photos. */
internal fun removeInterruptedMenuPhotoArtifacts(dir: File, activePaths: Set<String> = emptySet()): Int =
    dir.listFiles().orEmpty().count { file ->
        file.isFile && file.extension in setOf("part", "oriented") &&
            file.absolutePath !in activePaths && file.delete()
    }

/** Delete only abandoned app-owned camera output files, never a live capture. */
internal fun removeAbandonedOwnerCaptures(dir: File, protectedPaths: Set<String>): Int =
    dir.listFiles().orEmpty().count { file ->
        file.isFile && file.name.startsWith("menu-capture-") &&
            file.extension == "jpg" && file.absolutePath !in protectedPaths &&
            file.delete()
    }

/** Prevent recovery from racing a camera destination created in the same process. */
internal object OwnerMenuCaptureGuard {
    val lock = Any()
    val livePaths = mutableSetOf<String>()
}

/** Reconcile only completed private copies from a prior interrupted process.
 * The caller supplies saved picker entries and ALL repository import references.
 */
internal fun removeUnreferencedOwnerPhotoFiles(
    dir: File, retainedPaths: Set<String>, activePaths: Set<String> = emptySet(),
): Int {
    val finalPhotoName = Regex("[0-9a-fA-F-]{36}\\.(jpg|png)")
    return dir.listFiles().orEmpty().count { file ->
        file.isFile && finalPhotoName.matches(file.name) &&
            file.absolutePath !in retainedPaths && file.absolutePath !in activePaths &&
            file.delete()
    }
}

internal class OwnerMenuPhotoStore(context: Context) {
    private companion object {
        // Shared by store instances in this process so a screen re-entry cannot
        // delete another coroutine's in-progress image normalization.
        val tempLock = Any()
        val inFlightPaths = mutableSetOf<String>()
        // Protect newly completed batches from a second screen created while
        // the composing coroutine is still committing its saved picker entries.
        val producedThisProcess = mutableSetOf<String>()
    }
    private val app = context.applicationContext
    private val dir = File(app.noBackupFilesDir, "owner-menu-photo-drafts").apply {
        mkdirs()
        synchronized(tempLock) { removeInterruptedMenuPhotoArtifacts(this, inFlightPaths) }
    }

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

    /** Only call after the persisted repository snapshot and picker state load. */
    fun pruneUnreferencedCopies(retained: List<MockPhoto>): Int {
        val referenced = retained.mapNotNull {
            runCatching { fileFor(it).absolutePath }.getOrNull()
        }.toSet()
        return synchronized(tempLock) {
            removeUnreferencedOwnerPhotoFiles(dir,referenced,producedThisProcess + inFlightPaths)
        }
    }

    /** HEIC/HEIF is an Android picker input type, not an upload format.
     * The app stores only re-encoded JPEG, bounded to 4096px on the long edge.
     * ImageDecoder applies source orientation before conversion.
     */
    private fun convertHeicToJpeg(uri: Uri, output: File): Long {
        if(Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            throw IllegalArgumentException(
                "이 기기에서 HEIC 사진을 변환할 수 없어요. JPEG로 변환해 다시 선택해 주세요.")
        }
        val bitmap = try {
            ImageDecoder.decodeBitmap(ImageDecoder.createSource(app.contentResolver,uri)) {
                    decoder, info, _ ->
                val largest=maxOf(info.size.width,info.size.height)
                require(largest>0) { "사진 크기를 읽을 수 없어요." }
                decoder.setAllocator(ImageDecoder.ALLOCATOR_SOFTWARE)
                if(largest>4096)decoder.setTargetSampleSize((largest+4095)/4096)
            }
        } catch (e: Exception) {
            throw IllegalArgumentException("HEIC 사진을 변환하지 못했어요. JPEG로 바꿔 주세요.",e)
        }
        try {
            for(quality in listOf(85,75,65)) {
                val encoded=FileOutputStream(output).use {
                    bitmap.compress(Bitmap.CompressFormat.JPEG,quality,it)
                }
                require(encoded) { "사진을 JPEG로 저장하지 못했어요." }
                if(output.length() in 1..OWNER_MENU_MAX_PHOTO_BYTES)return output.length()
            }
        } finally { bitmap.recycle() }
        error("변환한 사진이 10MB를 초과해요. 더 작은 사진을 선택해 주세요.")
    }

    /** Validate actual image pixels, then normalize EXIF orientation before persisting.
     * Source overlays use coordinates after orientation; preview uses stored upright pixels.
     * Called on the picker IO coroutine, never during composition.
     */
    private fun normalizeAndValidate(file: File, photoId: String,
        created: MutableList<File>): Boolean {
        val bounds=BitmapFactory.Options().apply {inJustDecodeBounds=true}
        BitmapFactory.decodeFile(file.absolutePath,bounds)
        require(bounds.outWidth>0 && bounds.outHeight>0) {
            "사진을 읽을 수 없어요. 다시 선택해 주세요."
        }
        var sample=1
        while(bounds.outWidth/sample>4096 || bounds.outHeight/sample>4096)sample*=2
        val decoded=BitmapFactory.decodeFile(file.absolutePath,
            BitmapFactory.Options().apply {inSampleSize=sample})
            ?: error("사진 전체를 읽을 수 없어요. 다시 선택해 주세요.")
        val orientation=runCatching {
            ExifInterface(file.absolutePath).getAttributeInt(
                ExifInterface.TAG_ORIENTATION,ExifInterface.ORIENTATION_NORMAL)
        }.getOrDefault(ExifInterface.ORIENTATION_NORMAL)
        val matrix=Matrix()
        when(orientation) {
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.setScale(-1f,1f)
            ExifInterface.ORIENTATION_ROTATE_180 -> matrix.setRotate(180f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> matrix.setScale(1f,-1f)
            ExifInterface.ORIENTATION_TRANSPOSE -> {matrix.setRotate(90f);matrix.postScale(-1f,1f)}
            ExifInterface.ORIENTATION_ROTATE_90 -> matrix.setRotate(90f)
            ExifInterface.ORIENTATION_TRANSVERSE -> {matrix.setRotate(-90f);matrix.postScale(-1f,1f)}
            ExifInterface.ORIENTATION_ROTATE_270 -> matrix.setRotate(-90f)
        }
        if(matrix.isIdentity) {
            decoded.recycle()
            return false
        }
        val upright=try {
            Bitmap.createBitmap(decoded,0,0,decoded.width,decoded.height,matrix,true)
        } finally {decoded.recycle()}
        val output=File(dir,"$photoId.oriented")
        created.add(output)
        try {
            for(quality in listOf(85,75,65)) {
                val ok=FileOutputStream(output).use {
                    upright.compress(Bitmap.CompressFormat.JPEG,quality,it)
                }
                require(ok) { "사진 방향을 바로잡지 못했어요." }
                if(output.length() in 1..OWNER_MENU_MAX_PHOTO_BYTES)break
            }
        } finally {if(!upright.isRecycled)upright.recycle()}
        require(output.length() in 1..OWNER_MENU_MAX_PHOTO_BYTES) {
            "사진 방향을 보정한 결과가 10MB를 초과해요."
        }
        require(file.delete() && output.renameTo(file)) {
            "사진 방향을 저장하지 못했어요. 다시 선택해 주세요."
        }
        created.remove(output)
        return true
    }

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
        val claimedTempPaths = mutableSetOf<String>()
        var completed = false
        var total = existing.sumOf(::size)
        try {
            val additions = sources.map { uri ->
                val declared = app.contentResolver.getType(uri)
                val heic=declared in setOf("image/heic","image/heif",
                    "image/heic-sequence","image/heif-sequence")
                require(declared == null || declared == "image/jpeg" ||
                    declared == "image/png" || heic) {
                    "JPEG, PNG 또는 HEIC 사진을 선택해 주세요."
                }
                val photoId = UUID.randomUUID().toString()
                val temp = File(dir, "$photoId.part")
                // Claim both intermediate names before creating either file.
                synchronized(tempLock) {
                    claimedTempPaths += temp.absolutePath
                    claimedTempPaths += File(dir, "$photoId.oriented").absolutePath
                    inFlightPaths.addAll(claimedTempPaths)
                }
                created += temp
                val originalLength = if(heic) convertHeicToJpeg(uri,temp) else
                    app.contentResolver.openInputStream(uri)?.use { source ->
                        FileOutputStream(temp).use { sink ->
                            val buffer=ByteArray(16*1024)
                            var count=0L
                            while(true) {
                                val n=source.read(buffer)
                                if(n<0)break
                                count+=n
                                require(count<=OWNER_MENU_MAX_PHOTO_BYTES) {
                                    "사진 한 장은 최대 10MB까지 가능해요."
                                }
                                require(total+count<=OWNER_MENU_MAX_TOTAL_BYTES) {
                                    "전체 사진은 60MB 이하여야 해요."
                                }
                                sink.write(buffer,0,n)
                            }
                            count
                        }
                    } ?: error("사진 URI를 읽을 수 없어요. 다시 선택해 주세요.")
                require(total+originalLength<=OWNER_MENU_MAX_TOTAL_BYTES) {
                    "전체 사진은 60MB 이하여야 해요."
                }
                require(originalLength > 0) { "빈 사진은 등록할 수 없어요." }
                val magic = temp.inputStream().use { input ->
                    ByteArray(8).let { it.copyOf(input.read(it).coerceAtLeast(0)) }
                }
                val signature = menuPhotoSignature(magic)
                require(signature != null && (heic || declared == null || declared == signature)) {
                    "JPEG 또는 PNG 사진만 올릴 수 있어요."
                }
                val normalized=normalizeAndValidate(temp,photoId,created)
                val resultingType=if(normalized)"image/jpeg" else signature
                val length=temp.length()
                require(total+length<=OWNER_MENU_MAX_TOTAL_BYTES) {
                    "전체 사진은 60MB 이하여야 해요."
                }
                val stored = File(dir, "$photoId.${if (resultingType == "image/png") "png" else "jpg"}")
                synchronized(tempLock) {
                    require(temp.renameTo(stored)) { "사진을 보관하지 못했어요." }
                    producedThisProcess += stored.absolutePath
                }
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
            synchronized(tempLock) {
                if(!completed)producedThisProcess.removeAll(created.map {it.absolutePath}.toSet())
                inFlightPaths.removeAll(claimedTempPaths)
            }
        }
    }

    fun delete(photo: MockPhoto) {
        runCatching {
            val file=fileFor(photo)
            synchronized(tempLock) {
                file.delete()
                producedThisProcess.remove(file.absolutePath)
            }
        }
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
