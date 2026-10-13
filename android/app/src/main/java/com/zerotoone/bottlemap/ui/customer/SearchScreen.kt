// AI-assisted implementation draft (2026-10-13, I2-P13). Human build/review pending.
package com.zerotoone.bottlemap.ui.customer

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

private const val MAX_QUERY_LENGTH = 100

@Composable
fun SearchScreen(
    onOpenResults: (String) -> Unit,
) {
    var query by rememberSaveable { mutableStateOf("") }
    var navigating by rememberSaveable { mutableStateOf(false) }
    // Reset the one-shot navigation guard when returning from Search Results.
    LaunchedEffect(Unit) { navigating = false }
    val normalizedInput = query.trim()
    val tooLong = normalizedInput.length > MAX_QUERY_LENGTH
    val canSearch = normalizedInput.isNotEmpty() && !tooLong && !navigating
    val keyboard = LocalSoftwareKeyboardController.current

    val submit = {
        if (canSearch) {
            navigating = true
            keyboard?.hide()
            onOpenResults(normalizedInput)
        }
    }

    I2CustomerSearchTheme {
        SearchContent(
            query = query,
            tooLong = tooLong,
            canSearch = canSearch,
            isNavigating = navigating,
            onQueryChange = { query = it },
            onClear = { query = "" },
            onSearch = submit,
        )
    }
}

@Composable
private fun SearchContent(
    query: String,
    tooLong: Boolean,
    canSearch: Boolean,
    isNavigating: Boolean,
    onQueryChange: (String) -> Unit,
    onClear: () -> Unit,
    onSearch: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        Surface(
            color = MaterialTheme.colorScheme.background,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                text = "◉ BottleMap",
                color = MaterialTheme.colorScheme.onBackground,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 22.dp),
            )
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 22.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = "DISCOVER YOUR POUR",
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "찾는 위스키, 어디에서 마실까요?",
                color = MaterialTheme.colorScheme.onBackground,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "위스키 이름으로 취급하는 바를 찾아보세요.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                text = "위스키 검색",
                color = MaterialTheme.colorScheme.onBackground,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 12.dp),
            )

            OutlinedTextField(
                value = query,
                onValueChange = onQueryChange,
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                enabled = !isNavigating,
                placeholder = { Text("위스키 이름 입력") },
                leadingIcon = { Text("⌕") },
                trailingIcon = {
                    if (query.isNotEmpty()) {
                        TextButton(onClick = onClear) { Text("지우기") }
                    }
                },
                isError = tooLong,
                supportingText = {
                    Text(
                        if (tooLong) "검색어는 공백 제외 100자 이하여야 합니다."
                        else "한글 · English 주류명 검색",
                    )
                },
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Text,
                    imeAction = ImeAction.Search,
                ),
                keyboardActions = KeyboardActions(onSearch = { if (canSearch) onSearch() }),
            )

            Button(
                onClick = onSearch,
                enabled = canSearch,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("판매하는 바 찾기")
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun I2SearchInitialPreview() {
    I2CustomerSearchTheme {
        SearchContent("", false, false, false, {}, {}, {})
    }
}

@Preview(showBackground = true)
@Composable
private fun I2SearchEnteredPreview() {
    I2CustomerSearchTheme {
        SearchContent("Deanston 12", false, true, false, {}, {}, {})
    }
}
