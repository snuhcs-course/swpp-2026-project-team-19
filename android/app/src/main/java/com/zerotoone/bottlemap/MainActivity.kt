package com.zerotoone.bottlemap

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.LocalIndication
import androidx.compose.foundation.IndicationNodeFactory
import androidx.compose.foundation.interaction.InteractionSource
import androidx.compose.ui.graphics.drawscope.ContentDrawScope
import androidx.compose.ui.node.DelegatableNode
import androidx.compose.ui.node.DrawModifierNode
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
import com.zerotoone.bottlemap.BuildConfig
import com.zerotoone.bottlemap.ui.theme.BottleMapTheme

@OptIn(ExperimentalMaterial3Api::class)
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            BottleMapTheme {
                // All customer and owner interactions are quiet: no flash, highlight or ripple.
                CompositionLocalProvider(
                    LocalIndication provides QuietIndication,
                    LocalRippleConfiguration provides null,
                ) {
                Surface(
                    modifier = Modifier.fillMaxSize().safeDrawingPadding().imePadding()
                        .dismissKeyboardOnOutsideTap(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    // Debug-only UX review hooks (ignored in release builds):
                    // --es bm_ux_review <scenario>  opens a v18 mock review scenario,
                    // --ez bm_ux_reset_welcome true  shows the first-launch welcome again.
                    BottleMapNavHost(
                        devReviewScenario = if (BuildConfig.DEBUG) intent?.getStringExtra("bm_ux_review") else null,
                        resetWelcome = BuildConfig.DEBUG &&
                            intent?.getBooleanExtra("bm_ux_reset_welcome", false) == true,
                    )
                }
                }
            }
        }
    }
}

/**
 * Compose LocalIndication is non-null. A drawing-through no-op node suppresses
 * foundation click feedback while preserving accessibility/click semantics.
 */
private object QuietIndication : IndicationNodeFactory {
    override fun create(interactionSource: InteractionSource): DelegatableNode =
        object : Modifier.Node(), DrawModifierNode {
            override fun ContentDrawScope.draw() { drawContent() }
        }

    override fun equals(other: Any?): Boolean = other === this
    override fun hashCode(): Int = 0
}
