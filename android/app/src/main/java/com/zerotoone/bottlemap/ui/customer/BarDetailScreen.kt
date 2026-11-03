package com.zerotoone.bottlemap.ui.customer

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zerotoone.bottlemap.ui.common.BmIconId

/**
 * Only the P18 / Owner customer-preview detail UI is navigable.
 * The legacy Iteration-2 Bar Detail loading/success surface is intentionally removed.
 */
@Composable
fun BarDetailScreen(
    barId: String,
    onBack: () -> Unit,
    onBackAndRefreshResults: () -> Unit = onBack,
    onOpenMap: (String) -> Unit = {},
    viewModel: BarDetailViewModel = viewModel(),
    highlightProductId: String? = null,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(barId) { viewModel.load(barId) }
    val effectiveBack = if (state is BarDetailUiState.Error &&
        (state as BarDetailUiState.Error).refreshResultsOnBack
    ) onBackAndRefreshResults else onBack
    BackHandler(enabled = state is BarDetailUiState.Error &&
        (state as BarDetailUiState.Error).refreshResultsOnBack) {
        effectiveBack()
    }
    I2CustomerSearchTheme {
        when(val current = state) {
            is BarDetailUiState.Success -> CustomerP18BarDetail(
                bar=current.bar, empty=null, onBack=onBack,
                highlightProductId=highlightProductId)
            is BarDetailUiState.Empty -> CustomerP18BarDetail(
                bar=current.bar, empty=current.reason, onBack=onBack,
                highlightProductId=highlightProductId)
            else -> Column(Modifier.fillMaxSize().background(P18Bg)) {
                Row(Modifier.fillMaxWidth().height(72.dp).padding(start=8.dp),
                    verticalAlignment=Alignment.CenterVertically) {
                    P18Back(effectiveBack)
                }
                when(current) {
                    BarDetailUiState.Loading ->
                        P18LoadingBody("매장 찾는 중",Modifier.weight(1f))
                    is BarDetailUiState.Error ->
                        P18FailureBody("매장을 불러오지 못했어요",
                            current.message,
                            if(current.canRetry)"다시 시도" else "검색 결과로 돌아가기",
                            BmIconId.ERROR,
                            if(current.canRetry)viewModel::retry else effectiveBack,
                            modifier=Modifier.weight(1f),primary=current.canRetry,
                            topInset=120)
                    else -> Unit
                }
            }
        }
    }
}
