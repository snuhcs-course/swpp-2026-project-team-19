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
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import java.text.NumberFormat
import java.util.Locale
import kotlinx.coroutines.delay

@Composable
fun SearchResultsScreen(
    query: String,
    onBack: () -> Unit,
) {
    var retrying by rememberSaveable { mutableStateOf(false) }
    var retryCount by rememberSaveable { mutableIntStateOf(0) }

    LaunchedEffect(retrying) {
        if (retrying) {
            // P22-only fake retry. P25 will replace this with the real GET search request.
            delay(600)
            retrying = false
            retryCount += 1
        }
    }

    val state = when {
        retrying -> CustomerSearchUiState.Loading
        retryCount > 0 -> CustomerSearchUiState.Success(mockSearchResults)
        else -> mockSearchStateForQuery(query)
    }

    SearchResultsContent(
        query = query,
        state = state,
        onBack = onBack,
        onRetry = { retrying = true },
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
                TextButton(onClick = onBack) {
                    Text("Back")
                }
                Text(
                    text = "Search Results",
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
        }

        when (state) {
            CustomerSearchUiState.Idle -> Unit

            CustomerSearchUiState.Loading -> ResultsLoadingState(query = query)

            is CustomerSearchUiState.Success -> ResultsSuccessState(
                query = query,
                results = state.results,
            )

            is CustomerSearchUiState.Empty -> ResultsEmptyState(
                query = query,
                reason = state.reason,
                onBack = onBack,
            )

            is CustomerSearchUiState.Error -> ResultsErrorState(
                query = query,
                message = state.message,
                onRetry = onRetry,
                onBack = onBack,
            )
        }
    }
}

@Composable
private fun ResultsLoadingState(
    query: String,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = "Search: $query",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        CircularProgressIndicator()
        Text(
            text = "Searching bars…",
            style = MaterialTheme.typography.titleMedium,
        )
    }
}

@Composable
private fun ResultsSuccessState(
    query: String,
    results: List<MockSearchResult>,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = "Search: $query",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Text(
            text = "${results.size} bars found",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Medium,
        )

        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(results) { result ->
                SearchResultCard(result = result)
            }
        }
    }
}

@Composable
private fun SearchResultCard(
    result: MockSearchResult,
) {
    val priceFormatter = NumberFormat.getIntegerInstance(Locale.KOREA)

    Surface(
        shape = RoundedCornerShape(12.dp),
        tonalElevation = 1.dp,
        modifier = Modifier
            .fillMaxWidth()
            .border(
                width = 1.dp,
                color = MaterialTheme.colorScheme.outlineVariant,
                shape = RoundedCornerShape(12.dp),
            ),
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

            result.options.forEach { option ->
                Text(
                    text = "₩${priceFormatter.format(option.priceKrw)} · ${option.pourMl} ml",
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
        EmptySearchReason.NO_BARS -> "No matching bars found"
    }
    val message = when (reason) {
        EmptySearchReason.UNKNOWN_PRODUCT ->
            "Try another spelling or a different whisky name."
        EmptySearchReason.NO_BARS ->
            "We know this whisky, but no current menu lists it."
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            text = "Search: $query",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = title,
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = message,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedButton(onClick = onBack) {
            Text("Back to Search")
        }
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
        Text(
            text = "Search: $query",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

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

        Row(
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Button(onClick = onRetry) {
                Text("Retry")
            }
            OutlinedButton(onClick = onBack) {
                Text("Back")
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun SearchResultsSuccessPreview() {
    SearchResultsContent(
        query = "Deanston 12",
        state = CustomerSearchUiState.Success(mockSearchResults),
        onBack = {},
        onRetry = {},
    )
}

@Preview(showBackground = true)
@Composable
private fun SearchResultsLoadingPreview() {
    SearchResultsContent(
        query = "Deanston 12",
        state = CustomerSearchUiState.Loading,
        onBack = {},
        onRetry = {},
    )
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

@Preview(showBackground = true)
@Composable
private fun SearchResultsErrorPreview() {
    SearchResultsContent(
        query = "Deanston 12",
        state = CustomerSearchUiState.Error("We couldn't load search results."),
        onBack = {},
        onRetry = {},
    )
}
