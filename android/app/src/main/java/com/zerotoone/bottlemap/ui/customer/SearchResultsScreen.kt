package com.zerotoone.bottlemap.ui.customer

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
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import java.text.NumberFormat
import java.util.Locale

@Composable
fun SearchResultsScreen(
    query: String,
    onBack: () -> Unit,
    viewModel: SearchResultsViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(query) {
        viewModel.search(query)
    }

    SearchResultsContent(
        query = query,
        state = state,
        onBack = onBack,
        onRetry = viewModel::retry,
    )
}

@Composable
private fun SearchResultsContent(
    query: String,
    state: CustomerSearchUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
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
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onBack) { Text("Back") }
                Text(
                    text = "Search Results",
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
        }

        when (state) {
            CustomerSearchUiState.Loading -> ResultsLoadingState(query)
            is CustomerSearchUiState.Success -> ResultsSuccessState(query, state)
            is CustomerSearchUiState.Empty -> ResultsEmptyState(query, state.reason, onBack)
            is CustomerSearchUiState.Error -> ResultsErrorState(query, state.message, onRetry, onBack)
        }
    }
}

@Composable
private fun ResultsLoadingState(query: String) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = "Search: " + query,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        CircularProgressIndicator()
        Text("Searching bars…", style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
private fun ResultsSuccessState(
    query: String,
    state: CustomerSearchUiState.Success,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = "Search: " + query,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        val countLabel = if (state.results.size == 1) "1 menu result" else state.results.size.toString() + " menu results"
        Text(
            text = countLabel,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Medium,
        )
        if (state.truncated) {
            Text(
                text = "More matching menu rows exist. Refine the search to narrow the result.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(
                items = state.results,
                key = { it.barId + ":" + it.productDisplayName },
            ) { result ->
                SearchResultCard(result)
            }
        }
    }
}

@Composable
private fun SearchResultCard(result: SearchResultUiModel) {
    val priceFormatter = NumberFormat.getIntegerInstance(Locale.KOREA)
    Surface(
        shape = RoundedCornerShape(12.dp),
        tonalElevation = 1.dp,
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(12.dp)),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            Text(
                text = result.barName,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Medium,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = result.productDisplayName,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (result.menuDisplayName != result.productDisplayName) {
                Text(
                    text = "Menu: " + result.menuDisplayName,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            result.options.forEach { option ->
                val detail = listOfNotNull(
                    option.optionLabel,
                    option.pourMl?.let { it.toString() + " ml" },
                ).joinToString(" · ")
                val optionText = buildString {
                    append("₩")
                    append(priceFormatter.format(option.priceKrw))
                    if (detail.isNotBlank()) {
                        append(" · ")
                        append(detail)
                    }
                }
                Text(
                    text = optionText,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                )
            }
            Text(
                text = result.menuUpdatedText,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ResultsEmptyState(
    query: String,
    reason: EmptySearchReason,
    onBack: () -> Unit,
) {
    val title = when (reason) {
        EmptySearchReason.UNKNOWN_PRODUCT -> "We couldn't find that whisky"
        EmptySearchReason.NO_BARS -> "No current menu lists this whisky"
    }
    val message = when (reason) {
        EmptySearchReason.UNKNOWN_PRODUCT -> "Try another spelling or a different whisky name."
        EmptySearchReason.NO_BARS -> "BottleMap recognizes the product, but no published bar menu currently sells it."
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Search: " + query, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(message, color = MaterialTheme.colorScheme.onSurfaceVariant)
        OutlinedButton(onClick = onBack) { Text("Back to Search") }
    }
}

@Composable
private fun ResultsErrorState(
    query: String,
    message: String,
    onRetry: () -> Unit,
    onBack: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Search: " + query, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(onClick = onRetry) { Text("Retry") }
            OutlinedButton(onClick = onBack) { Text("Back") }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun SearchResultsUnknownPreview() {
    SearchResultsContent(
        query = "Unknown whisky",
        state = CustomerSearchUiState.Empty(EmptySearchReason.UNKNOWN_PRODUCT),
        onBack = {},
        onRetry = {},
    )
}
