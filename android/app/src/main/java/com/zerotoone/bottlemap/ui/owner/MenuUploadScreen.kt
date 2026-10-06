package com.zerotoone.bottlemap.ui.owner

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel

@Composable
fun MenuUploadScreen(
    onOpenReview: (String) -> Unit,
    viewModel: MenuUploadViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val picker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
    ) { uri ->
        if (uri != null) {
            viewModel.selectImage(uri)
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
                onClearPhoto = viewModel::clearImage,
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
    onClearPhoto: () -> Unit,
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
                        enabled = !state.working && !selected,
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
                    text = "3. Choose a menu photo",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
            }

            item {
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(12.dp)),
                ) {
                    Column(
                        modifier = Modifier.padding(18.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text(
                            state.selectedImage?.displayName ?: "No photo selected",
                            style = MaterialTheme.typography.bodyLarge,
                        )
                        Text(
                            "JPEG/PNG are uploaded directly when safe; unsupported formats are converted to JPEG.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(
                                onClick = onPickPhoto,
                                enabled = !state.working,
                            ) {
                                Text(if (state.selectedImage == null) "Choose Photo" else "Change Photo")
                            }
                            if (state.selectedImage != null) {
                                OutlinedButton(
                                    onClick = onClearPhoto,
                                    enabled = !state.working,
                                ) {
                                    Text("Remove")
                                }
                            }
                        }
                    }
                }
            }

            item {
                Button(
                    onClick = onUpload,
                    enabled = !state.working && state.selectedImage != null && selectedBar != null,
                ) {
                    Text("Upload & Extract")
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
