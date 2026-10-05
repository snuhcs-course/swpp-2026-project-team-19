package com.zerotoone.bottlemap.ui.customer

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
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

private const val MAX_QUERY_LENGTH = 100

@Composable
fun SearchScreen(
    onOpenResults: (String) -> Unit,
) {
    var query by rememberSaveable { mutableStateOf("") }
    var isLoading by rememberSaveable { mutableStateOf(false) }

    val trimmedQuery = query.trim()
    val queryTooLong = trimmedQuery.length > MAX_QUERY_LENGTH
    val canSearch = trimmedQuery.isNotEmpty() && !queryTooLong && !isLoading

    LaunchedEffect(isLoading) {
        if (isLoading) {
            // P22-only fake loading delay. No backend request is made here.
            delay(700)
            isLoading = false
            onOpenResults(trimmedQuery)
        }
    }

    SearchContent(
        query = query,
        state = if (isLoading) {
            CustomerSearchUiState.Loading
        } else {
            CustomerSearchUiState.Idle
        },
        queryTooLong = queryTooLong,
        canSearch = canSearch,
        onQueryChange = { query = it },
        onSearch = { isLoading = true },
    )
}

@Composable
private fun SearchContent(
    query: String,
    state: CustomerSearchUiState,
    queryTooLong: Boolean,
    canSearch: Boolean,
    onQueryChange: (String) -> Unit,
    onSearch: () -> Unit,
) {
    val isLoading = state == CustomerSearchUiState.Loading

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
                text = "BottleMap",
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
            Text(
                text = "What whisky are you looking for?",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )

            if (!isLoading) {
                Text(
                    text = "Type a whisky name to find bars that serve it.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            OutlinedTextField(
                value = query,
                onValueChange = onQueryChange,
                enabled = !isLoading,
                singleLine = true,
                label = { Text("Whisky name") },
                placeholder = { Text("e.g. Deanston 12") },
                isError = queryTooLong,
                supportingText = if (queryTooLong) {
                    {
                        Text("Search terms must be 100 characters or fewer.")
                    }
                } else {
                    null
                },
                modifier = Modifier.fillMaxWidth(),
            )

            if (isLoading) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 14.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    CircularProgressIndicator()
                    Text(
                        text = "Searching bars…",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Button(
                onClick = onSearch,
                enabled = canSearch,
            ) {
                Text("Search")
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun SearchIdlePreview() {
    SearchContent(
        query = "",
        state = CustomerSearchUiState.Idle,
        queryTooLong = false,
        canSearch = false,
        onQueryChange = {},
        onSearch = {},
    )
}

@Preview(showBackground = true)
@Composable
private fun SearchFilledPreview() {
    SearchContent(
        query = "Deanston 12",
        state = CustomerSearchUiState.Idle,
        queryTooLong = false,
        canSearch = true,
        onQueryChange = {},
        onSearch = {},
    )
}

@Preview(showBackground = true)
@Composable
private fun SearchLoadingPreview() {
    SearchContent(
        query = "Deanston 12",
        state = CustomerSearchUiState.Loading,
        queryTooLong = false,
        canSearch = false,
        onQueryChange = {},
        onSearch = {},
    )
}
