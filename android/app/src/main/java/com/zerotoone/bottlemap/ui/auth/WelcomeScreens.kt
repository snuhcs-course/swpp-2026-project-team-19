package com.zerotoone.bottlemap.ui.auth

import android.content.Context
import androidx.core.content.edit
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.ui.common.BmLineIcon
import com.zerotoone.bottlemap.ui.common.BmLineIconId
import com.zerotoone.bottlemap.ui.common.UxColor
import com.zerotoone.bottlemap.ui.common.UxMainButton
import com.zerotoone.bottlemap.ui.common.UxSecondaryButton
import com.zerotoone.bottlemap.ui.common.quietClick
import com.zerotoone.bottlemap.ui.common.uxText

/**
 * Whether the first-launch welcome was completed. Kept apart from the auth session: a
 * guest finishes the welcome too, and logging out does not show it again.
 */
interface FirstLaunchStore {
    fun isDone(): Boolean
    fun markDone()
}

class SharedPrefsFirstLaunchStore(context: Context) : FirstLaunchStore {
    private val prefs = context.applicationContext.getSharedPreferences("bottlemap-first-launch", Context.MODE_PRIVATE)
    override fun isDone() = prefs.getBoolean(KEY_DONE, false)
    override fun markDone() = prefs.edit { putBoolean(KEY_DONE, true) }

    /** Debug builds only: show the welcome again for UX review. */
    fun reset() = prefs.edit { remove(KEY_DONE) }

    private companion object {
        const val KEY_DONE = "welcome-done"
    }
}

/** First-launch welcome (v18 `welcome`). The bottom tabs are hidden here. */
@Composable
fun WelcomeScreen(
    onBrowseAsGuest: () -> Unit,
    onGoogle: () -> Unit,
    onOwner: () -> Unit,
    busy: Boolean = false,
    inlineError: String? = null,
) {
    // .welcome: min-height calc(100% - 70px), actions pushed to the bottom (margin-top: auto).
    BoxWithConstraints(Modifier.fillMaxSize().background(UxColor.bg).testTag("welcome-screen")) {
        val minHeight = maxHeight - 70.dp
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            Column(
                Modifier.fillMaxWidth().heightIn(min = minHeight)
                    .padding(start = 20.dp, end = 20.dp, top = 100.dp, bottom = 33.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.SpaceBetween,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box {
                        // .logo-large with its cap (::before) drawn 12dp above the frame, outside its box.
                        Box(Modifier.size(75.dp, 85.dp).border(2.dp, UxColor.gold, RoundedCornerShape(18.dp)),
                            contentAlignment = Alignment.Center) {
                            Text("B", style = uxText(47f, 700, UxColor.gold, lineHeight = 1.2f, serif = true))
                        }
                        Box(Modifier.align(Alignment.TopCenter).offset(y = (-12).dp).size(22.dp, 8.dp)
                            .background(UxColor.gold, RoundedCornerShape(5.dp)))
                    }
                    Spacer(Modifier.height(22.dp))
                    Text("BottleMap", style = uxText(28f, 700, serif = true, letterSpacing = (-1).sp))
                    Text("마시고 싶은 위스키, 어디에서 만날까요?", style = uxText(13f, 400, UxColor.sub),
                        textAlign = TextAlign.Center, modifier = Modifier.padding(vertical = 13.dp))
                }
                Column(Modifier.fillMaxWidth().padding(top = 24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        UxMainButton("로그인 없이 둘러보기", onBrowseAsGuest, Modifier.testTag("welcome-guest"), enabled = !busy)
                        UxSecondaryButton("Google로 계속", onGoogle, Modifier.testTag("welcome-google"), enabled = !busy)
                        if (inlineError != null) InlineAlert(inlineError)
                    }
                    Row(Modifier.padding(top = 18.dp), verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp, Alignment.CenterHorizontally)) {
                        Text("매장을 운영하시나요?", style = uxText(12f, 400, UxColor.muted))
                        Box(Modifier.heightIn(min = 48.dp).quietClick(enabled = !busy, onClick = onOwner)
                            .testTag("welcome-owner"), contentAlignment = Alignment.Center) {
                            Text("매장 등록 · 관리", style = uxText(12f, 700, UxColor.gold))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun InlineAlert(message: String) {
    Box(Modifier.fillMaxWidth().background(UxColor.alertBg, RoundedCornerShape(10.dp))
        .border(1.dp, UxColor.alertBorder, RoundedCornerShape(10.dp)).padding(horizontal = 12.dp, vertical = 11.dp)) {
        Text(message, style = uxText(12f, 400, UxColor.error))
    }
}

/**
 * Full-screen sign-in failure (v18 `loginError`): "다시 시도" opens the Google account
 * picker again at once. Also used for an expired session with [title] "로그인이 만료됐어요.".
 */
@Composable
fun LoginErrorScreen(
    title: String,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onBrowseAsGuest: () -> Unit,
    busy: Boolean = false,
) {
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(UxColor.bg).testTag("login-error-screen")) {
        Row(Modifier.fillMaxWidth().height(59.dp).padding(horizontal = 20.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(9.dp)) {
            Box(Modifier.size(48.dp).quietClick(onClick = onBack).semantics { contentDescription = "뒤로" },
                contentAlignment = Alignment.Center) {
                BmLineIcon(BmLineIconId.BACK, 19.dp, UxColor.sub)
            }
            Text("로그인", style = uxText(17f, 750, letterSpacing = (-0.45).sp))
        }
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
                .padding(start = 24.dp, end = 24.dp, top = 65.dp, bottom = 22.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(13.dp),
        ) {
            Box(Modifier.padding(bottom = 8.dp).size(68.dp).background(UxColor.surface, CircleShape)
                .border(1.dp, UxColor.line, CircleShape), contentAlignment = Alignment.Center) {
                BmLineIcon(BmLineIconId.ALERT, 28.dp, UxColor.error)
            }
            Text(title, style = uxText(23f, 700, lineHeight = 1.4f, serif = true), textAlign = TextAlign.Center,
                modifier = Modifier.widthIn(max = 342.dp).testTag("login-error-title"))
            Column(Modifier.fillMaxWidth().padding(top = 15.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                UxMainButton("다시 시도", onRetry, Modifier.testTag("login-error-retry"), enabled = !busy)
                UxSecondaryButton("로그인 없이 둘러보기", onBrowseAsGuest, Modifier.testTag("login-error-guest"), enabled = !busy)
            }
        }
    }
}
