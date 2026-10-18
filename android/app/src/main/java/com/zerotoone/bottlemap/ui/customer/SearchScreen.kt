// AI-assisted implementation draft (2026-10-13, I2-P13). Human build/review pending.
package com.zerotoone.bottlemap.ui.customer

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.Alignment
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
    onOpenAccount: () -> Unit = {},
    onOpenNearby: () -> Unit = {},
    serverValidationErrorCode: String? = null,
    onClearServerValidation: () -> Unit = {},
) {
    var query by rememberSaveable { mutableStateOf("") }
    var navigating by rememberSaveable { mutableStateOf(false) }
    // Reset the one-shot navigation guard when returning from Search Results.
    LaunchedEffect(Unit) { navigating = false }
    LaunchedEffect(serverValidationErrorCode) {
        if (serverValidationErrorCode != null) navigating = false
    }
    val normalizedInput = query.trim()
    val tooLong = normalizedInput.length > MAX_QUERY_LENGTH
    val canSearch = normalizedInput.isNotEmpty() && !tooLong &&
        !navigating && serverValidationErrorCode == null
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
            serverValidationErrorCode = serverValidationErrorCode,
            onQueryChange = {
                query = it
                onClearServerValidation()
            },
            onClear = {
                query = ""
                onClearServerValidation()
            },
            onSearch = submit,
            onOpenAccount = onOpenAccount,
            onOpenNearby = onOpenNearby,
        )
    }
}

@Composable
private fun SearchContent(
    query: String,
    tooLong: Boolean,
    canSearch: Boolean,
    isNavigating: Boolean,
    serverValidationErrorCode: String?,
    onQueryChange: (String) -> Unit,
    onClear: () -> Unit,
    onSearch: () -> Unit,
    onOpenAccount: () -> Unit,
    onOpenNearby: () -> Unit,
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
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "◉ BottleMap",
                    color = MaterialTheme.colorScheme.onBackground,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                TextButton(onClick = onOpenAccount) { Text("마이페이지") }
            }
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
                isError = tooLong || serverValidationErrorCode != null,
                supportingText = {
                    Text(
                        when {
                            tooLong -> "검색어는 공백 제외 100자 이하여야 합니다."
                            serverValidationErrorCode != null ->
                                searchValidationMessage(serverValidationErrorCode)
                            else -> "한글 · English 주류명 검색"
                        },
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
            // The I2 wireflow S0 shows a "내 주변 바" section alongside a
            // "지도에서 보기" entry. Actual cards stay in the Nearby route
            // until the Backend provides a complete public nearby catalog;
            // never show fabricated bar cards on the search home screen.
            Text(
                text = "내 주변 바",
                color = MaterialTheme.colorScheme.onBackground,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 8.dp),
            )
            OutlinedButton(
                onClick = onOpenNearby,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("500m 내 주변 바 · 지도에서 보기 →")
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun I2SearchInitialPreview() {
    I2CustomerSearchTheme {
        SearchContent("", false, false, false, null, {}, {}, {}, {}, {})
    }
}

@Preview(showBackground = true)
@Composable
private fun I2SearchEnteredPreview() {
    I2CustomerSearchTheme {
        SearchContent("Deanston 12", false, true, false, null, {}, {}, {}, {}, {})
    }
}

/** This mapping is display-only. The backend remains the validation authority. */
internal fun searchValidationMessage(fieldCode: String): String = when (fieldCode) {
    "MISSING", "BLANK" -> "검색어를 입력해 주세요."
    "STRING_TOO_LONG" -> "검색어는 100자 이하여야 합니다."
    "NOT_SEARCHABLE" -> "검색할 수 있는 문자가 없습니다. 제품명을 입력해 주세요."
    else -> "검색어를 확인해 주세요."
}
