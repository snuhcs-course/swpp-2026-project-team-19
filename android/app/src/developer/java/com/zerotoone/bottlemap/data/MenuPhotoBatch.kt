// I2-A14: pure selection and one-transaction preparation rules, Developer only.
package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.MenuImportAcceptedDto
import kotlinx.coroutines.CancellationException

const val MAX_MENU_PHOTOS = 5
const val MAX_MENU_PHOTO_BYTES = 10 * 1024 * 1024
const val MAX_MENU_TOTAL_BYTES = 30 * 1024 * 1024

data class PhotoSelectionResult(
    val images: List<SelectedMenuImage>,
    val duplicates: Int,
    val overLimit: Int,
)

/** Selection is additive; a canceled picker returns [] and does not clear photos. */
fun appendMenuPhotos(
    existing: List<SelectedMenuImage>,
    incoming: List<SelectedMenuImage>,
): PhotoSelectionResult {
    val known = existing.mapTo(mutableSetOf()) { it.uri }
    var duplicates = 0
    var overLimit = 0
    val selected = existing.toMutableList()
    incoming.forEach { photo ->
        when {
            !known.add(photo.uri) -> duplicates++
            selected.size >= MAX_MENU_PHOTOS -> overLimit++
            else -> selected.add(photo)
        }
    }
    return PhotoSelectionResult(selected, duplicates, overLimit)
}

fun removeMenuPhoto(
    photos: List<SelectedMenuImage>, uri: String,
): List<SelectedMenuImage> = photos.filterNot { it.uri == uri }

/** UI reports exactly which local image needs replacing; no partial server request is sent. */
class MenuPhotoPreparationException(
    val imageOrder: Int,
    cause: Throwable,
) : Exception("Photo #$imageOrder: ${cause.message ?: "cannot be prepared"}", cause)

private fun validImageBytes(image: PreparedMenuImage): Boolean {
    val data = image.bytes
    return when (image.mimeType) {
        "image/jpeg" -> data.size >= 3 && data[0] == 0xff.toByte() &&
            data[1] == 0xd8.toByte() && data[2] == 0xff.toByte()
        "image/png" -> data.size >= 8 &&
            data.copyOfRange(0, 8).contentEquals(byteArrayOf(
                0x89.toByte(), 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
            ))
        else -> false
    }
}

/** Validate EVERY page, its order, and aggregate size before beginning the HTTP request. */
suspend fun prepareMenuBatch(
    photos: List<SelectedMenuImage>,
    prepare: suspend (SelectedMenuImage) -> PreparedMenuImage,
    onPrepared: (Int) -> Unit = {},
): List<PreparedMenuImage> {
    require(photos.size in 1..MAX_MENU_PHOTOS) { "Select 1 to 5 photos." }
    var bytes = 0L
    val result = ArrayList<PreparedMenuImage>(photos.size)
    photos.forEachIndexed { index, photo ->
        val order = index + 1
        try {
            val image = prepare(photo)
            require(validImageBytes(image)) { "Unsupported or invalid JPEG/PNG image." }
            require(image.bytes.size <= MAX_MENU_PHOTO_BYTES) { "Photo exceeds 10 MB." }
            bytes += image.bytes.size.toLong()
            require(bytes <= MAX_MENU_TOTAL_BYTES) { "Combined photos exceed 30 MB." }
            result.add(image)
            onPrepared(order)
        } catch (cancelled: CancellationException) {
            // Navigation away or lifecycle destruction must cancel preparation.
            throw cancelled
        } catch (error: Exception) {
            throw MenuPhotoPreparationException(order, error)
        }
    }
    return result
}

/** A single multipart transaction, never one import per image. */
suspend fun submitMenuBatch(
    photos: List<SelectedMenuImage>,
    prepare: suspend (SelectedMenuImage) -> PreparedMenuImage,
    send: suspend (List<PreparedMenuImage>) -> MenuImportAcceptedDto,
    onPrepared: (Int) -> Unit = {},
): MenuImportAcceptedDto {
    val prepared = prepareMenuBatch(photos, prepare, onPrepared)
    return send(prepared)
}
