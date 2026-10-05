package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

@Composable
fun MenuUploadScreen(
    onOpenReview: () -> Unit,
) {
    var stateName by rememberSaveable {
        mutableStateOf(MenuUploadUiState.EMPTY.name)
    }
    val state = MenuUploadUiState.valueOf(stateName)

    LaunchedEffect(state) {
        if (state == MenuUploadUiState.PROCESSING) {
            // P19-only fake processing delay. No API call is made here.
            delay(900)
            stateName = MenuUploadUiState.SELECTED.name
            onOpenReview()
        }
    }

    MenuUploadContent(
        state = state,
        onChoosePhoto = { stateName = MenuUploadUiState.SELECTED.name },
        onTakePhoto = { stateName = MenuUploadUiState.SELECTED.name },
        onChangePhoto = { stateName = MenuUploadUiState.EMPTY.name },
        onUpload = { stateName = MenuUploadUiState.PROCESSING.name },
        onRetry = { stateName = MenuUploadUiState.PROCESSING.name },
        onPreviewError = { stateName = MenuUploadUiState.ERROR.name },
    )
}

@Composable
private fun MenuUploadContent(
    state: MenuUploadUiState,
    onChoosePhoto: () -> Unit,
    onTakePhoto: () -> Unit,
    onChangePhoto: () -> Unit,
    onUpload: () -> Unit,
    onRetry: () -> Unit,
    onPreviewError: () -> Unit,
) {
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

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            when (state) {
                MenuUploadUiState.EMPTY -> EmptyUploadState(
                    onChoosePhoto = onChoosePhoto,
                    onTakePhoto = onTakePhoto,
                )

                MenuUploadUiState.SELECTED -> SelectedUploadState(
                    onChangePhoto = onChangePhoto,
                    onUpload = onUpload,
                    onPreviewError = onPreviewError,
                )

                MenuUploadUiState.PROCESSING -> ProcessingUploadState()

                MenuUploadUiState.ERROR -> ErrorUploadState(
                    onRetry = onRetry,
                    onChangePhoto = onChangePhoto,
                )
            }
        }
    }
}

@Composable
private fun EmptyUploadState(
    onChoosePhoto: () -> Unit,
    onTakePhoto: () -> Unit,
) {
    Text(
        text = "Upload a whisky menu",
        style = MaterialTheme.typography.headlineSmall,
        fontWeight = FontWeight.Bold,
    )
    Text(
        text = "Choose an existing image or use the system camera.",
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    MenuImageArea(selected = false)

    Row(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        OutlinedButton(onClick = onChoosePhoto) {
            Text("Choose Photo")
        }
        OutlinedButton(onClick = onTakePhoto) {
            Text("Take Photo")
        }
    }

    Button(
        onClick = {},
        enabled = false,
    ) {
        Text("Upload & Extract")
    }
}

@Composable
private fun SelectedUploadState(
    onChangePhoto: () -> Unit,
    onUpload: () -> Unit,
    onPreviewError: () -> Unit,
) {
    Text(
        text = "Check this menu photo",
        style = MaterialTheme.typography.headlineSmall,
        fontWeight = FontWeight.Bold,
    )

    MenuImageArea(selected = true)

    Text(
        text = "menu_photo.jpg · ready to upload",
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    Row(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        OutlinedButton(onClick = onChangePhoto) {
            Text("Change Photo")
        }
        Button(onClick = onUpload) {
            Text("Upload & Extract")
        }
    }

    TextButton(onClick = onPreviewError) {
        Text("Simulate upload error (P19 mock)")
    }
}

@Composable
private fun ProcessingUploadState() {
    MenuImageArea(selected = true)

    Spacer(modifier = Modifier.height(6.dp))

    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        CircularProgressIndicator()
        Text(
            text = "Uploading menu…",
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }

    Text(
        text = "Reading menu after upload: product name, price, and pour size.",
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun ErrorUploadState(
    onRetry: () -> Unit,
    onChangePhoto: () -> Unit,
) {
    Text(
        text = "We couldn't process this menu",
        style = MaterialTheme.typography.headlineSmall,
        fontWeight = FontWeight.Bold,
    )

    MenuImageArea(selected = true)

    Surface(
        color = MaterialTheme.colorScheme.errorContainer,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text = "Upload failed. Retry with the same image or choose another photo.",
            color = MaterialTheme.colorScheme.onErrorContainer,
            modifier = Modifier.padding(16.dp),
        )
    }

    Row(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Button(onClick = onRetry) {
            Text("Retry")
        }
        OutlinedButton(onClick = onChangePhoto) {
            Text("Change Photo")
        }
    }
}

@Composable
private fun MenuImageArea(
    selected: Boolean,
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(220.dp)
            .background(
                color = if (selected) {
                    MaterialTheme.colorScheme.surface
                } else {
                    MaterialTheme.colorScheme.surfaceVariant
                },
                shape = RoundedCornerShape(12.dp),
            )
            .border(
                width = 1.dp,
                color = MaterialTheme.colorScheme.outlineVariant,
                shape = RoundedCornerShape(12.dp),
            ),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = if (selected) "MENU PHOTO" else "PHOTO",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                text = if (selected) "menu_photo.jpg" else "Choose a menu photo",
                style = MaterialTheme.typography.titleMedium,
            )
            if (selected) {
                Text(
                    text = "Selected image preview",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun EmptyUploadPreview() {
    MenuUploadContent(
        state = MenuUploadUiState.EMPTY,
        onChoosePhoto = {},
        onTakePhoto = {},
        onChangePhoto = {},
        onUpload = {},
        onRetry = {},
        onPreviewError = {},
    )
}

@Preview(showBackground = true)
@Composable
private fun SelectedUploadPreview() {
    MenuUploadContent(
        state = MenuUploadUiState.SELECTED,
        onChoosePhoto = {},
        onTakePhoto = {},
        onChangePhoto = {},
        onUpload = {},
        onRetry = {},
        onPreviewError = {},
    )
}

@Preview(showBackground = true)
@Composable
private fun ProcessingUploadPreview() {
    MenuUploadContent(
        state = MenuUploadUiState.PROCESSING,
        onChoosePhoto = {},
        onTakePhoto = {},
        onChangePhoto = {},
        onUpload = {},
        onRetry = {},
        onPreviewError = {},
    )
}

@Preview(showBackground = true)
@Composable
private fun ErrorUploadPreview() {
    MenuUploadContent(
        state = MenuUploadUiState.ERROR,
        onChoosePhoto = {},
        onTakePhoto = {},
        onChangePhoto = {},
        onUpload = {},
        onRetry = {},
        onPreviewError = {},
    )
}
