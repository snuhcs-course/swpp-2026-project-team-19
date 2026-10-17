// AI-assisted implementation draft (2026-10-17, I2-P24). Human verification pending.
package com.zerotoone.bottlemap.ui.customer

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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel

@Composable
fun BarDetailScreen(
    barId: String,
    onBack: () -> Unit,
    onBackAndRefreshResults: () -> Unit = onBack,
    viewModel: BarDetailViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(barId) { viewModel.load(barId) }

    I2CustomerSearchTheme {
        BarDetailContent(
            state = state,
            onBack = onBack,
            onBackAndRefreshResults = onBackAndRefreshResults,
            onRetry = viewModel::retry,
        )
    }
}

@Composable
private fun BarDetailContent(
    state: BarDetailUiState,
    onBack: () -> Unit,
    onBackAndRefreshResults: () -> Unit = onBack,
    onRetry: () -> Unit,
) {
    val effectiveBack = if (
        state is BarDetailUiState.Error && state.refreshResultsOnBack
    ) onBackAndRefreshResults else onBack
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
            TextButton(onClick = effectiveBack) { Text("←") }
            Text(
                text = "바 상세",
                color = MaterialTheme.colorScheme.onBackground,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
        }

        when (state) {
            BarDetailUiState.Loading -> BarDetailMessage(
                title = "메뉴를 불러오는 중입니다",
                description = "현재 게시된 바 메뉴를 확인하고 있어요.",
                showProgress = true,
            )

            is BarDetailUiState.Success -> BarDetailMenuList(
                bar = state.bar,
                emptyReason = null,
            )

            is BarDetailUiState.Empty -> BarDetailMenuList(
                bar = state.bar,
                emptyReason = state.reason,
            )

            is BarDetailUiState.Error -> BarDetailMessage(
                title = "메뉴를 불러오지 못했어요",
                description = state.message,
                buttonLabel = if (state.canRetry) "다시 시도" else "검색 결과로 돌아가기",
                onButtonClick = if (state.canRetry) onRetry else effectiveBack,
            )
        }
    }
}

@Composable
private fun BarDetailMenuList(
    bar: BarDetailUiModel,
    emptyReason: EmptyMenuReason?,
) {
    // A single LazyColumn scrolls the identity, update date, and entire menu.
    // No visible scrollbar or nested vertically scrollable containers.
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Surface(
                color = Color(0xFF1A304B),
                shape = RoundedCornerShape(18.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .border(
                        1.dp,
                        MaterialTheme.colorScheme.outlineVariant,
                        RoundedCornerShape(18.dp),
                    ),
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text(
                        text = "REGISTERED BAR",
                        color = MaterialTheme.colorScheme.primary,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = bar.name,
                        color = MaterialTheme.colorScheme.onBackground,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = bar.address,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    bar.phone?.takeIf { it.isNotBlank() }?.let { phone ->
                        Text(
                            text = phone,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }
            }
        }

        item {
            // I2-P25 implements location/map navigation. Keep the design slot
            // without presenting a dead clickable map action as working.
            OutlinedButton(
                onClick = {},
                enabled = false,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("지도에서 위치 보기 · 다음 작업")
            }
        }

        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = "현재 메뉴",
                    color = MaterialTheme.colorScheme.onBackground,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = bar.publishedAtText ?: "갱신 기록 없음",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

        if (emptyReason != null) {
            item {
                val message = when (emptyReason) {
                    EmptyMenuReason.NO_PUBLISHED_MENU -> "등록된 메뉴가 없습니다."
                    EmptyMenuReason.NO_CURRENT_ITEMS -> "현재 판매 중인 메뉴가 없습니다."
                }
                Surface(
                    color = MaterialTheme.colorScheme.surface,
                    shape = RoundedCornerShape(15.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        text = message,
                        color = MaterialTheme.colorScheme.onSurface,
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.padding(20.dp),
                    )
                }
            }
        } else {
            items(
                items = bar.items,
                key = { it.menuBoardEntryId },
            ) { menuItem ->
                BarMenuItemCard(menuItem)
            }
            item {
                Text(
                    text = "메뉴 정보는 마지막 갱신일 기준입니다.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(bottom = 8.dp),
                )
            }
        }
    }
}

@Composable
private fun BarMenuItemCard(item: BarMenuItemUiModel) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(15.dp),
        modifier = Modifier
            .fillMaxWidth()
            .border(
                1.dp,
                MaterialTheme.colorScheme.outlineVariant,
                RoundedCornerShape(15.dp),
            ),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                text = "WHISKY MENU",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = item.menuDisplayName,
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurface,
                fontWeight = FontWeight.Bold,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
            )
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            if (item.options.isEmpty()) {
                // Defensive UI for a malformed response; the API promises >=1.
                Text(
                    text = "가격·용량 정보 없음",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyMedium,
                )
            } else {
                item.options.forEach { option ->
                    Text(
                        text = option.text,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun BarDetailMessage(
    title: String,
    description: String,
    showProgress: Boolean = false,
    buttonLabel: String? = null,
    onButtonClick: () -> Unit = {},
) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 18.dp, vertical = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            if (showProgress) CircularProgressIndicator()
            Text(
                text = title,
                color = MaterialTheme.colorScheme.onSurface,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = description,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
            if (buttonLabel != null) {
                Button(onClick = onButtonClick) { Text(buttonLabel) }
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun BarDetailSuccessPreview() {
    I2CustomerSearchTheme {
        BarDetailContent(
            state = BarDetailUiState.Success(
                BarDetailUiModel(
                    barId = "preview",
                    name = "관악 위스키 바",
                    address = "서울특별시 관악구 관악로 1, 2층",
                    phone = null,
                    latitude = 37.4783,
                    longitude = 126.9512,
                    publishedAtText = "갱신 2026.10.04",
                    items = listOf(
                        BarMenuItemUiModel(
                            menuBoardEntryId = "preview-item",
                            productId = "preview-product",
                            menuDisplayName = "Deanston 12",
                            options = listOf(BarMenuOptionUiModel("30 ml  ₩15,000")),
                        ),
                    ),
                ),
            ),
            onBack = {},
            onRetry = {},
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun BarDetailErrorPreview() {
    I2CustomerSearchTheme {
        BarDetailContent(
            state = BarDetailUiState.Error("네트워크 연결을 확인해 주세요."),
            onBack = {},
            onRetry = {},
        )
    }
}
