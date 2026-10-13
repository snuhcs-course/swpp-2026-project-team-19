// AI-assisted implementation draft (2026-10-13, I2-P13/P14). Human build/review pending.
package com.zerotoone.bottlemap.ui.customer

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.material3.HorizontalDivider
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
    onOpenBarDetail: (String) -> Unit,
    viewModel: SearchResultsViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(query) { viewModel.search(query) }

    I2CustomerSearchTheme {
        SearchResultsContent(
            query = query,
            state = state,
            onBack = onBack,
            onOpenBarDetail = onOpenBarDetail,
            onRetry = viewModel::retry,
        )
    }
}

@Composable
private fun SearchResultsContent(
    query: String,
    state: CustomerSearchUiState,
    onBack: () -> Unit,
    onOpenBarDetail: (String) -> Unit,
    onRetry: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = onBack) { Text("←") }
            Text(
                text = "검색 결과",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
        }

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            Text(
                text = "PRODUCT SEARCH",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = query,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "검색한 위스키를 제공하는 바",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        when (state) {
            CustomerSearchUiState.Loading -> SearchStatusPanel(
                title = "검색 중입니다",
                description = "등록된 메뉴를 확인하고 있어요.",
                isLoading = true,
            )
            is CustomerSearchUiState.Success -> ResultsSuccess(
                state = state,
                onOpenBarDetail = onOpenBarDetail,
                modifier = Modifier.weight(1f),
            )
            is CustomerSearchUiState.Empty -> {
                val unknown = state.reason == EmptySearchReason.UNKNOWN_PRODUCT
                SearchStatusPanel(
                    title = if (unknown) "일치하는 주류가 없어요" else "등록된 판매 바가 없어요",
                    description = if (unknown) {
                        "다른 철자나 제품명을 입력해 보세요."
                    } else {
                        "다른 위스키를 검색해 보세요."
                    },
                    actionLabel = "검색어 변경",
                    onAction = onBack,
                )
            }
            is CustomerSearchUiState.Error -> SearchStatusPanel(
                title = "결과를 불러오지 못했어요",
                description = state.message,
                actionLabel = "다시 시도",
                onAction = onRetry,
                secondaryAction = onBack,
            )
        }
    }
}

@Composable
private fun ResultsSuccess(
    state: CustomerSearchUiState.Success,
    onOpenBarDetail: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    // The results are allocated the remaining height by the parent Column.
    // Keep the count/notice inside the same LazyColumn, allowing every card
    // to scroll on small phones without adding a visible scrollbar.
    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(
                text = "검색 결과 (" + state.results.size + ")",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onBackground,
            )
        }
        if (state.truncated) {
            item {
                Text(
                    text = "검색 결과 일부만 표시 중입니다. 검색어를 구체적으로 입력해 주세요.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        items(
            items = state.results,
            key = { it.barId + ":" + it.productId },
        ) { result ->
            SearchResultCard(
                result = result,
                onClick = { onOpenBarDetail(result.barId) },
            )
        }
    }
}

@Composable
private fun SearchResultCard(
    result: SearchResultUiModel,
    onClick: () -> Unit,
) {
    val formatter = NumberFormat.getIntegerInstance(Locale.KOREA)

    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier
            .fillMaxWidth()
            .border(
                1.dp,
                MaterialTheme.colorScheme.outlineVariant,
                RoundedCornerShape(16.dp),
            )
            .clickable(onClick = onClick),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = "MATCHING WHISKY",
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                text = result.barName,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            if (result.address.isNotBlank()) {
                Text(
                    text = result.address,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Text(
                text = result.productDisplayName,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (result.menuDisplayName.isNotBlank() &&
                result.menuDisplayName != result.productDisplayName
            ) {
                Text(
                    text = "메뉴 표기: " + result.menuDisplayName,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            if (result.options.isEmpty()) {
                Text(
                    text = "가격·용량 정보 없음",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                result.options.forEach { option ->
                    val optionInfo = listOfNotNull(
                        option.optionLabel?.takeIf { it.isNotBlank() },
                        option.pourMl?.let { it.toString() + " ml" },
                    ).joinToString(" · ")
                    Text(
                        text = (if (optionInfo.isBlank()) "" else optionInfo + "  ") +
                            "₩" + formatter.format(option.priceKrw),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                    )
                }
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
private fun SearchStatusPanel(
    title: String,
    description: String,
    isLoading: Boolean = false,
    actionLabel: String? = null,
    onAction: () -> Unit = {},
    secondaryAction: (() -> Unit)? = null,
) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp, vertical = 34.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(15.dp),
        ) {
            if (isLoading) CircularProgressIndicator()
            Text(
                text = title,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = description,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (actionLabel != null) {
                Button(onClick = onAction) { Text(actionLabel) }
            }
            if (secondaryAction != null) {
                OutlinedButton(onClick = secondaryAction) { Text("검색어 변경") }
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun ResultsSuccessPreview() {
    I2CustomerSearchTheme {
        SearchResultsContent(
            query = "Deanston 12",
            state = CustomerSearchUiState.Success(
                results = listOf(
                    SearchResultUiModel(
                        barId = "bar-preview",
                        barName = "관악 위스키 바",
                        address = "서울특별시 관악구",
                        productId = "product-preview",
                        productDisplayName = "Deanston 12",
                        menuDisplayName = "딘스톤 12년",
                        options = listOf(
                            SearchOptionUiModel(8000, null, 15),
                            SearchOptionUiModel(15000, null, 30),
                        ),
                        menuUpdatedText = "갱신 2026.10.04",
                    ),
                ),
                truncated = false,
            ),
            onBack = {},
            onOpenBarDetail = {},
            onRetry = {},
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun ResultsErrorPreview() {
    I2CustomerSearchTheme {
        SearchResultsContent(
            query = "Deanston 12",
            state = CustomerSearchUiState.Error("네트워크 연결을 확인해 주세요."),
            onBack = {},
            onOpenBarDetail = {},
            onRetry = {},
        )
    }
}
