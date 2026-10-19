// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #7, #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.ui.owner

import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import com.zerotoone.bottlemap.data.MAX_MENU_PHOTOS
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.Dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel

@Composable
fun MenuUploadScreen(
    onOpenReview: (String) -> Unit,
    viewModel: MenuUploadViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val picker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickMultipleVisualMedia(MAX_MENU_PHOTOS),
    ) { uris ->
        // Picker grants temporary read access; persist it when supported so
        // SavedStateHandle URIs can survive process recreation.
        uris.forEach { uri ->
            runCatching {
                viewModel.getApplication<android.app.Application>().contentResolver
                    .takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
        }
        viewModel.addImages(uris)
    }
    // External TakePicture has no CAMERA permission requirement.
    val camera = rememberLauncherForActivityResult(
        contract = remember {
            object : ActivityResultContracts.TakePicture() {
                override fun createIntent(context: Context, input: Uri): Intent =
                    super.createIntent(context, input).apply {
                        clipData = ClipData.newUri(context.contentResolver, "Menu photo", input)
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                    }
            }
        },
    ) { success -> viewModel.onCameraCaptureResult(success) }
    fun launchCamera(retake: Boolean) {
        val uri = viewModel.startCameraCapture(retake) ?: return
        try {
            camera.launch(uri)
        } catch (error: Exception) {
            viewModel.cameraLaunchFailed(error.message ?: "Camera unavailable.")
        }
    }

    LaunchedEffect(state.openReviewImportId) {
        val importId = state.openReviewImportId ?: return@LaunchedEffect
        onOpenReview(importId)
        viewModel.consumeReviewNavigation()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        Surface(
            tonalElevation = 1.dp,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                text = "Register Menu",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 16.dp),
            )
        }

        when {
            state.loadingBars -> LoadingOwnerState()
            state.bars.isEmpty() -> EmptyBarsState(
                message = state.errorMessage ?: "No active bars are available.",
                onRetry = viewModel::loadBars,
            )
            else -> OwnerUploadContent(
                state = state,
                onSelectBar = viewModel::selectBar,
                onPickPhoto = {
                    picker.launch(
                        PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                    )
                },
                onRemovePhoto = viewModel::removeImage,
                onTakePhoto = { launchCamera(false) },
                onRetakePhoto = { launchCamera(true) },
                onUseCameraPhoto = viewModel::useCapturedPhoto,
                onDiscardCameraPreview = viewModel::discardCameraPreview,
                onRecoverCamera = viewModel::recoverInterruptedCamera,
                onDiscardPendingCamera = viewModel::discardInterruptedCamera,
                onNewAttempt = viewModel::startNewAttemptAfterFailure,
                onSetMode = viewModel::setMode,
                onUpload = viewModel::upload,
                onContinueImport = viewModel::continueActiveImport,
                onReloadBars = viewModel::loadBars,
            )
        }
    }
}

@Composable
private fun LoadingOwnerState() {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        CircularProgressIndicator()
        Text("Signing in and loading bars…")
    }
}

@Composable
private fun EmptyBarsState(
    message: String,
    onRetry: () -> Unit,
) {
    Column(
        modifier = Modifier.padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(message)
        Button(onClick = onRetry) { Text("Retry") }
    }
}

@Composable
private fun OwnerUploadContent(
    state: MenuUploadUiState,
    onSelectBar: (String) -> Unit,
    onPickPhoto: () -> Unit,
    onRemovePhoto: (String) -> Unit,
    onTakePhoto: () -> Unit,
    onRetakePhoto: () -> Unit,
    onUseCameraPhoto: () -> Unit,
    onDiscardCameraPreview: () -> Unit,
    onRecoverCamera: () -> Unit,
    onDiscardPendingCamera: () -> Unit,
    onNewAttempt: () -> Unit,
    onSetMode: (ImportModeUi) -> Unit,
    onUpload: () -> Unit,
    onContinueImport: () -> Unit,
    onReloadBars: () -> Unit,
) {
    val selectedBar = state.bars.firstOrNull { it.barId == state.selectedBarId }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Text(
                text = "1. Choose a bar",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
        }

        items(state.bars, key = { it.barId }) { bar ->
            val selected = bar.barId == state.selectedBarId
            Surface(
                shape = RoundedCornerShape(12.dp),
                tonalElevation = if (selected) 3.dp else 0.dp,
                modifier = Modifier
                    .fillMaxWidth()
                    .border(
                        1.dp,
                        if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant,
                        RoundedCornerShape(12.dp),
                    ),
            ) {
                Column(
                    modifier = Modifier.padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(bar.name, style = MaterialTheme.typography.titleMedium)
                    Text(
                        bar.address,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (bar.activeImportId != null) {
                        Text(
                            "Active import: " + bar.activeImportStatus,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                    OutlinedButton(
                        onClick = { onSelectBar(bar.barId) },
                        enabled = !state.working && !selected && !state.selectionBusy &&
                            !state.cameraPending && !state.cameraChecking &&
                            state.cameraPreviewUri == null,
                    ) {
                        Text(if (selected) "Selected" else "Select")
                    }
                }
            }
        }

        if (selectedBar?.activeImportId != null) {
            item {
                Surface(
                    color = MaterialTheme.colorScheme.secondaryContainer,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text(
                            "This bar already has an unfinished import.",
                            fontWeight = FontWeight.Medium,
                        )
                        Text(
                            "Continue it instead of creating a duplicate upload.",
                            color = MaterialTheme.colorScheme.onSecondaryContainer,
                        )
                        Button(
                            onClick = onContinueImport,
                            enabled = !state.working,
                        ) {
                            Text("Continue active import")
                        }
                    }
                }
            }
        } else {
            item {
                Text(
                    text = "2. Upload mode",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
            }

            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ImportModeUi.entries.forEach { mode ->
                        if (state.mode == mode) {
                            Button(
                                onClick = { onSetMode(mode) },
                                enabled = !state.working,
                            ) {
                                Text(mode.label)
                            }
                        } else {
                            OutlinedButton(
                                onClick = { onSetMode(mode) },
                                enabled = !state.working,
                            ) {
                                Text(mode.label)
                            }
                        }
                    }
                }
            }

            item {
                Text(
                    text = state.mode.description,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            item {
                Text(
                    text = "3. Choose menu photos (" + state.selectedImages.size + "/5)",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
            }

            item {
                Text(
                    "Select up to five pages, 10 MB each / 30 MB total. " +
                        "The order shown is the extraction order. Unsupported formats are converted to JPEG.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(
                        onClick = onPickPhoto,
                        enabled = !state.working && !state.selectionBusy && !state.cameraPending &&
                            !state.cameraChecking && state.cameraPreviewUri == null &&
                            state.selectedImages.size < MAX_MENU_PHOTOS,
                    ) { Text("Add gallery photos") }
                    OutlinedButton(
                        onClick = onTakePhoto,
                        enabled = !state.working && !state.selectionBusy && !state.cameraPending &&
                            !state.cameraChecking && state.cameraPreviewUri == null &&
                            state.selectedImages.size < MAX_MENU_PHOTOS,
                    ) { Text("Take photo") }
                }
            }

            if (state.cameraPending && !state.cameraChecking) {
                item {
                    Surface(color = MaterialTheme.colorScheme.secondaryContainer,
                        shape = RoundedCornerShape(12.dp)) {
                        Column(modifier = Modifier.padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("Camera return pending. If capture was interrupted, recover or discard it.")
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                OutlinedButton(onClick = onRecoverCamera) { Text("Recover") }
                                OutlinedButton(onClick = onDiscardPendingCamera) { Text("Discard") }
                            }
                        }
                    }
                }
            }

            if (state.cameraChecking) {
                item {
                    Row(verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        CircularProgressIndicator(modifier = Modifier.size(24.dp))
                        Text("Checking camera photo…")
                    }
                }
            }

            if (state.cameraPreviewUri != null && !state.cameraPending) {
                item {
                    Surface(shape = RoundedCornerShape(12.dp), tonalElevation = 2.dp,
                        modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text("Review captured photo", style = MaterialTheme.typography.titleMedium)
                            MenuPhotoThumbnail(state.cameraPreviewUri, 168.dp)
                            Text("The image is added to your batch only after Use photo.",
                                style = MaterialTheme.typography.bodySmall)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(onClick = onUseCameraPhoto, enabled = !state.cameraChecking) {
                                    Text("Use photo")
                                }
                                OutlinedButton(onClick = onRetakePhoto, enabled = !state.cameraChecking) {
                                    Text("Retake")
                                }
                                OutlinedButton(onClick = onDiscardCameraPreview,
                                    enabled = !state.cameraChecking) { Text("Discard") }
                            }
                        }
                    }
                }
            }

            if (state.selectionBusy) {
                item { Text("Checking selected photos…") }
            }

            if (state.selectedImages.isEmpty()) {
                item { Text("No menu photos selected. Add at least one page to continue.") }
            }

            items(state.selectedImages, key = { it.uri }) { photo ->
                val order = state.selectedImages.indexOf(photo) + 1
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    tonalElevation = 1.dp,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        MenuPhotoThumbnail(photo.uri)
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Page $order · " + photo.displayName,
                                style = MaterialTheme.typography.bodyMedium)
                            state.imagePreparation[photo.uri]?.let { status ->
                                Text(status, style = MaterialTheme.typography.labelSmall,
                                    color = if (status.startsWith("Failed"))
                                        MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary)
                            }
                        }
                        OutlinedButton(
                            onClick = { onRemovePhoto(photo.uri) },
                            enabled = !state.working && !state.selectionBusy &&
                                !state.cameraPending && !state.cameraChecking &&
                                state.cameraPreviewUri == null,
                        ) { Text("Remove") }
                    }
                }
            }

            item {
                Button(
                    onClick = onUpload,
                    enabled = !state.working && !state.selectionBusy &&
                        !state.cameraPending && !state.cameraChecking &&
                        state.cameraPreviewUri == null &&
                        state.selectedImages.isNotEmpty() && selectedBar != null &&
                        !state.failedImportRequiresNewAttempt,
                ) { Text("Upload " + state.selectedImages.size + " photos & Extract") }
            }

            if (state.failedImportRequiresNewAttempt) {
                item {
                    Surface(
                        color = MaterialTheme.colorScheme.errorContainer,
                        shape = RoundedCornerShape(12.dp),
                    ) {
                        Column(
                            modifier = Modifier.padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            Text("This extraction failed. The server cannot retry only the failed page.")
                            Text("Starting a new attempt uploads every selected page again; no failed import is published.")
                            Button(onClick = onNewAttempt, enabled = !state.working) {
                                Text("Start a new attempt")
                            }
                        }
                    }
                }
            }

        }

        if (state.working) {
            item {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    CircularProgressIndicator()
                    Text(state.statusMessage ?: "Working…")
                }
            }
        }

        if (state.extractionProgress != null) {
            item {
                val p = state.extractionProgress!!
                Text("Server extraction: " + p.completedImages + "/" + p.totalImages +
                    " completed; " + p.failedImages + " failed.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        if (state.errorMessage != null) {
            item {
                Surface(
                    color = MaterialTheme.colorScheme.errorContainer,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text(
                            state.errorMessage,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                        )
                        OutlinedButton(
                            onClick = onReloadBars,
                            enabled = !state.working,
                        ) {
                            Text("Refresh bars")
                        }
                    }
                }
            }
        }
    }
}

/** Bounded-size local thumbnail; cannot decode a full-size gallery bitmap on the UI thread. */
@Composable
private fun MenuPhotoThumbnail(uriString: String, previewSize: Dp = 76.dp) {
    val resolver = LocalContext.current.contentResolver
    val thumbnail by produceState<ImageBitmap?>(initialValue = null, key1 = uriString) {
        value = withContext(Dispatchers.IO) {
            runCatching {
                val uri = Uri.parse(uriString)
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
                if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return@runCatching null
                var sample = 1
                while (bounds.outWidth / sample > 180 || bounds.outHeight / sample > 180) sample *= 2
                val options = BitmapFactory.Options().apply { inSampleSize = sample }
                resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, options) }
                    ?.asImageBitmap()
            }.getOrNull()
        }
    }
    if (thumbnail != null) {
        Image(
            bitmap = thumbnail!!,
            contentDescription = "Selected menu photo preview",
            contentScale = ContentScale.Crop,
            modifier = Modifier.size(previewSize),
        )
    } else {
        Text("Preview unavailable", modifier = Modifier.size(previewSize),
            style = MaterialTheme.typography.labelSmall)
    }
}
