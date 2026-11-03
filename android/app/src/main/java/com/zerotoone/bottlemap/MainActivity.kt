package com.zerotoone.bottlemap

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.LocalIndication
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LocalRippleConfiguration
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.zerotoone.bottlemap.ui.common.dismissKeyboardOnOutsideTap
import com.zerotoone.bottlemap.navigation.BottleMapNavHost
import com.zerotoone.bottlemap.ui.theme.BottleMapTheme

@OptIn(ExperimentalMaterial3Api::class)
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            BottleMapTheme {
                // All customer and owner interactions are quiet: no flash, highlight or ripple.
                CompositionLocalProvider(
                    LocalIndication provides null,
                    LocalRippleConfiguration provides null,
                ) {
                Surface(
                    modifier = Modifier.fillMaxSize().safeDrawingPadding().imePadding()
                        .dismissKeyboardOnOutsideTap(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    BottleMapNavHost()
                }
                }
            }
        }
    }
}
