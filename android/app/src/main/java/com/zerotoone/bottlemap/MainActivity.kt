package com.zerotoone.bottlemap

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.safeDrawingPadding
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
                    modifier = Modifier.fillMaxSize().safeDrawingPadding().imePadding(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    BottleMapNavHost()
                }
            }
        }
    }
}
