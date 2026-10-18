// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #7). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.ui.mode

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun ModeSelectionScreen(
    onCustomerSelected: () -> Unit,
    onOwnerSelected: () -> Unit,
) {
    // Temporary P10-only entry point for verifying the two navigation flows.
    // This is not a final product UX or authentication/role decision.
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(
            space = 16.dp,
            alignment = Alignment.CenterVertically,
        ),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = "BottleMap",
            style = MaterialTheme.typography.headlineMedium,
        )
        Text(
            text = "Temporary mode selection for P10",
            style = MaterialTheme.typography.bodyMedium,
        )
        Button(onClick = onCustomerSelected) {
            Text("Customer")
        }
        Button(onClick = onOwnerSelected) {
            Text("Owner / Operator")
        }
    }
}
