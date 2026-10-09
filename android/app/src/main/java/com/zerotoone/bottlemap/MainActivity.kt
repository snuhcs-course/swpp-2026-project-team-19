// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #7). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.zerotoone.bottlemap.navigation.BottleMapNavHost
import com.zerotoone.bottlemap.ui.theme.BottleMapTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            BottleMapTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    BottleMapNavHost()
                }
            }
        }
    }
}
