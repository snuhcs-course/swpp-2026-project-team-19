// AI-assisted navigation placeholder (2026-10-13, I2-P14). Full bar detail is I2-P24.
package com.zerotoone.bottlemap.ui.customer

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * Preserves the selected barId and back stack until the actual I2-P24 bar detail.
 * No bar-detail API call or fabricated menu information is shown here.
 */
@Composable
fun BarDetailPendingScreen(
    barId: String,
    onBack: () -> Unit,
) {
    I2CustomerSearchTheme {
        Column(
            modifier = Modifier.fillMaxSize().padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            Text("바 상세", style = MaterialTheme.typography.headlineMedium)
            Text("선택한 바의 상세 화면은 I2-P24에서 연결됩니다.")
            Text("개발 확인용 바 ID: " + barId, style = MaterialTheme.typography.bodySmall)
            OutlinedButton(onClick = onBack) { Text("검색 결과로 돌아가기") }
        }
    }
}
