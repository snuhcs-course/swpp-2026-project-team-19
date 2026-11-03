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
                    BottleMapNavHost()
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
