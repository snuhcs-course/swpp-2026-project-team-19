package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

@Composable
fun ExtractionReviewScreen(
    onBack: () -> Unit,
) {
    ExtractionReviewContent(
        state = ExtractionReviewUiState.Success(mockExtractedMenuItems),
        onBack = onBack,
    )
}

@Composable
private fun ExtractionReviewContent(
    state: ExtractionReviewUiState,
    onBack: () -> Unit,
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
                text = "Extraction Review",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 16.dp),
            )
        }

        when (state) {
            ExtractionReviewUiState.Loading -> ReviewLoadingState()

            is ExtractionReviewUiState.Success -> ReviewSuccessState(
                items = state.items,
                onBack = onBack,
            )

            ExtractionReviewUiState.Empty -> ReviewEmptyState(onBack = onBack)

            is ExtractionReviewUiState.Error -> ReviewErrorState(
                message = state.message,
                onBack = onBack,
            )
        }
    }
}

@Composable
private fun ReviewLoadingState() {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        CircularProgressIndicator()
        Text(
            text = "Preparing extracted items…",
            style = MaterialTheme.typography.titleMedium,
        )
    }
}

@Composable
private fun ReviewSuccessState(
    items: List<MockExtractedMenuItem>,
    onBack: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            text = "Review the extracted items before publishing.",
            style = MaterialTheme.typography.bodyLarge,
        )

        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(items) { item ->
                ExtractedMenuItemRow(item = item)
            }
        }

        Text(
            text = "Editing and publishing are intentionally deferred beyond P19.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Row(
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            OutlinedButton(onClick = onBack) {
                Text("Back")
            }
            Button(
                onClick = {},
                enabled = false,
            ) {
                Text("Confirm & Publish")
            }
        }
    }
}

@Composable
private fun ExtractedMenuItemRow(
    item: MockExtractedMenuItem,
) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        tonalElevation = 1.dp,
        modifier = Modifier
            .fillMaxWidth()
            .border(
                width = 1.dp,
                color = if (item.needsReview) {
                    MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.outlineVariant
                },
                shape = RoundedCornerShape(12.dp),
            ),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = item.productName,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Medium,
                )
                if (item.needsReview) {
                    Text(
                        text = "Needs Review",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }

            Row(
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                ReadOnlyField(
                    label = "Price",
                    value = item.priceText,
                    modifier = Modifier.weight(1f),
                )
                ReadOnlyField(
                    label = "Pour",
                    value = item.pourSizeText,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

@Composable
private fun ReadOnlyField(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .border(
                width = 1.dp,
                color = MaterialTheme.colorScheme.outlineVariant,
                shape = RoundedCornerShape(8.dp),
            )
            .padding(10.dp),
        verticalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Medium,
        )
    }
}

@Composable
private fun ReviewEmptyState(
    onBack: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            text = "No menu items were extracted.",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = "Try another menu image when the upload flow is connected.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedButton(onClick = onBack) {
            Text("Back")
        }
    }
}

@Composable
private fun ReviewErrorState(
    message: String,
    onBack: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Surface(
            color = MaterialTheme.colorScheme.errorContainer,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                text = message,
                color = MaterialTheme.colorScheme.onErrorContainer,
                modifier = Modifier.padding(16.dp),
            )
        }
        OutlinedButton(onClick = onBack) {
            Text("Back")
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun ReviewSuccessPreview() {
    ExtractionReviewContent(
        state = ExtractionReviewUiState.Success(mockExtractedMenuItems),
        onBack = {},
    )
}

@Preview(showBackground = true)
@Composable
private fun ReviewLoadingPreview() {
    ExtractionReviewContent(
        state = ExtractionReviewUiState.Loading,
        onBack = {},
    )
}

@Preview(showBackground = true)
@Composable
private fun ReviewEmptyPreview() {
    ExtractionReviewContent(
        state = ExtractionReviewUiState.Empty,
        onBack = {},
    )
}

@Preview(showBackground = true)
@Composable
private fun ReviewErrorPreview() {
    ExtractionReviewContent(
        state = ExtractionReviewUiState.Error("Extraction failed. Try another menu image."),
        onBack = {},
    )
}
