// I2 A15: unit-testable external-camera capture state; no camera hardware dependency.
package com.zerotoone.bottlemap.data

import kotlinx.coroutines.CancellationException

data class CameraPhoto(val fileName: String, val uri: String)

interface CameraPhotoStorage {
    fun create(): CameraPhoto
    fun restore(fileName: String): CameraPhoto?
    suspend fun validate(photo: CameraPhoto)
    fun delete(photo: CameraPhoto)
    fun deleteIfOwned(uri: String)
}

sealed interface CameraCaptureResult {
    data class PreviewReady(val photo: CameraPhoto) : CameraCaptureResult
    data class Accepted(val photo: CameraPhoto) : CameraCaptureResult
    data class Invalid(val message: String) : CameraCaptureResult
    data object Canceled : CameraCaptureResult
    data object NoPendingCapture : CameraCaptureResult
}

/** Only one unconfirmed capture may exist. Already selected gallery/camera URIs live in A14. */
class CameraCaptureSession(
    private val storage: CameraPhotoStorage,
    restoredPending: CameraPhoto? = null,
    restoredPreview: CameraPhoto? = null,
) {
    var pending: CameraPhoto? = restoredPending
        private set
    var preview: CameraPhoto? = restoredPreview
        private set

    fun start(): CameraPhoto {
        check(pending == null && preview == null) { "Finish or discard the current camera photo first." }
        return storage.create().also { pending = it }
    }

    suspend fun finish(success: Boolean): CameraCaptureResult {
        val photo = pending ?: return CameraCaptureResult.NoPendingCapture
        pending = null
        if (!success) {
            storage.delete(photo)
            return CameraCaptureResult.Canceled
        }
        return try {
            storage.validate(photo)
            preview?.let(storage::delete) // only replace preview after a successful retake
            preview = photo
            CameraCaptureResult.PreviewReady(photo)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            storage.delete(photo)
            CameraCaptureResult.Invalid(error.message ?: "Captured photo is not readable.")
        }
    }

    suspend fun accept(): CameraCaptureResult {
        val photo = preview ?: return CameraCaptureResult.NoPendingCapture
        return try {
            storage.validate(photo)
            preview = null
            CameraCaptureResult.Accepted(photo)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            preview = null
            storage.delete(photo)
            CameraCaptureResult.Invalid(error.message ?: "Captured photo is no longer readable.")
        }
    }

    fun retake(): CameraPhoto {
        check(pending == null && preview != null) { "Only an unconfirmed preview can be retaken." }
        // Preserve the previous unconfirmed photo if camera launch/capture is cancelled.
        return storage.create().also { pending = it }
    }

    fun discardPreview() {
        preview?.let(storage::delete)
        preview = null
    }

    fun discardPending() {
        pending?.let(storage::delete)
        pending = null
    }

    fun deleteIfOwned(uri: String) = storage.deleteIfOwned(uri)
}
