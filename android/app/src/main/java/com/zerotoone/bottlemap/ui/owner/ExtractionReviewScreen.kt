package com.zerotoone.bottlemap.ui.owner

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
import androidx.compose.material3.TextButton
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
fun ExtractionReviewScreen(
    menuImportId: String,
    onBack: () -> Unit,
    viewModel: ExtractionReviewViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(menuImportId) {
        viewModel.load(menuImportId)
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
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onBack) { Text("Back") }
                Text(
                    text = "Extraction Review",
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
        }

        when (val current = state) {
            ExtractionReviewUiState.Loading -> ReviewLoadingState()
            is ExtractionReviewUiState.Ready -> ReviewReadyState(
                current,
                onApply = viewModel::applyDefaultReview,
            )
            is ExtractionReviewUiState.Applying -> ReviewApplyingState(current.review)
            is ExtractionReviewUiState.Applied -> ReviewAppliedState(current.result, onBack)
            is ExtractionReviewUiState.Error -> ReviewErrorState(
                current.message,
                onRetry = { viewModel.load(menuImportId, force = true) },
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
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        CircularProgressIndicator()
        Text("Loading review data…")
    }
}

@Composable
private fun ReviewReadyState(
    state: ExtractionReviewUiState.Ready,
    onApply: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(
                "Review backend proposals before publishing.",
                style = MaterialTheme.typography.bodyLarge,
            )
        }

        if (state.message != null) {
            item {
                Surface(
                    color = MaterialTheme.colorScheme.errorContainer,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        state.message,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        modifier = Modifier.padding(14.dp),
                    )
                }
            }
        }

        items(
            items = state.review.items,
            key = { it.extractedItemId },
        ) { item ->
            ReviewItemCard(item)
        }

        if (state.review.proposedChanges.isNotEmpty()) {
            item {
                Text(
                    "Proposed menu changes",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
            }
            items(state.review.proposedChanges) { summary ->
                Text("• " + summary)
            }
        }

        item {
            Surface(
                color = MaterialTheme.colorScheme.secondaryContainer,
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    "Confirm & Publish accepts the backend's current product proposals and applies every proposed menu change. Items without a match use the backend new-product draft.",
                    modifier = Modifier.padding(14.dp),
                    color = MaterialTheme.colorScheme.onSecondaryContainer,
                )
            }
        }

        item {
            Button(onClick = onApply) {
                Text("Confirm & Publish")
            }
        }
    }
}

@Composable
private fun ReviewItemCard(item: ReviewItemUiModel) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        tonalElevation = 1.dp,
        modifier = Modifier
            .fillMaxWidth()
            .border(
                1.dp,
                if (item.needsReview) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.outlineVariant,
                RoundedCornerShape(12.dp),
            ),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    item.title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.weight(1f),
                )
                if (item.needsReview) {
                    Text(
                        "Needs Review",
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.labelMedium,
                    )
                }
            }
            Text(
                item.lineType,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (item.rawText != item.title) {
                Text(
                    item.rawText,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            item.options.forEach { option ->
                Text(option.label + ": " + option.priceText)
            }
            Text(
                item.decisionText,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
            )
        }
    }
}

@Composable
private fun ReviewApplyingState(review: ReviewUiModel) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        CircularProgressIndicator()
        Text("Publishing reviewed menu…")
        Text(
            review.items.size.toString() + " extracted item(s)",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ReviewAppliedState(
    result: AppliedUiModel,
    onBack: () -> Unit,
) {
    Column(
        modifier = Modifier.padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            "Menu published",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )
        Text("The backend returned status=applied.")
        if (result.added != null) {
            Text(
                "Added " + result.added +
                    " · Updated " + result.updated +
                    " · Removed " + result.removed +
                    " · Ignored " + result.ignored
            )
        }
        Text(
            "Switch to Customer mode and search for a product from this menu to verify the final P25 slice.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Button(onClick = onBack) {
            Text("Back to Owner")
        }
    }
}

@Composable
private fun ReviewErrorState(
    message: String,
    onRetry: () -> Unit,
    onBack: () -> Unit,
) {
    Column(
        modifier = Modifier.padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Surface(
            color = MaterialTheme.colorScheme.errorContainer,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                message,
                color = MaterialTheme.colorScheme.onErrorContainer,
                modifier = Modifier.padding(16.dp),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onRetry) { Text("Retry") }
            OutlinedButton(onClick = onBack) { Text("Back") }
        }
    }
}
