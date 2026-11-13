package com.zerotoone.bottlemap.ui.auth

import android.content.Context
import androidx.core.content.edit
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import com.zerotoone.bottlemap.R
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

/** First-launch welcome. Exact v20 `.welcome` geometry at a 390dp reference width.
 * The pin is the isolated transparent artwork embedded in the supplied v20 HTML.
 * Login remains a one-tap Credential Manager action owned by the caller.
 */
@Composable
fun WelcomeScreen(
    onBrowseAsGuest: () -> Unit,
    onGoogle: () -> Unit,
    onOwner: () -> Unit,
    busy: Boolean = false,
    inlineError: String? = null,
) {
    BoxWithConstraints(Modifier.fillMaxSize().background(UxColor.bg).testTag("welcome-screen")) {
        // CSS: .welcome { height:100%; min-height:630px; padding:0 20px }
        val contentHeight = maxOf(maxHeight, 630.dp)
        val pinHeight = minOf(194.dp, contentHeight * 0.33f)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            Box(Modifier.fillMaxWidth().height(contentHeight)) {
                // v20: left 20; pin bottom exactly 22dp above the 50% headline line.
                Image(
                    painter = painterResource(R.drawable.bottlemap_welcome_pin),
                    contentDescription = "위스키 잔이 담긴 지도 핀",
                    modifier = Modifier.offset(x = 20.dp, y = contentHeight / 2 - 22.dp - pinHeight)
                        .size(width = 158.dp, height = pinHeight)
                        .testTag("welcome-pin"),
                    contentScale = ContentScale.Fit,
                    alignment = Alignment.BottomStart,
                )
                Text(
                    "Find the bottle first,\nthen the bar.",
                    style = uxText(30f, 700, UxColor.text, 1.27f, serif = true,
                        letterSpacing = (-0.9).sp),
                    textAlign = TextAlign.Start,
                    modifier = Modifier.offset(x = 20.dp, y = contentHeight / 2)
                        .widthIn(max = 350.dp).testTag("welcome-headline"),
                )
                Column(
                    Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                        .padding(start = 20.dp, end = 20.dp, bottom = 23.dp),
                ) {
                    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        UxMainButton("Google로 계속", onGoogle,
                            Modifier.testTag("welcome-google"), enabled = !busy)
                        UxSecondaryButton("로그인 없이 둘러보기", onBrowseAsGuest,
                            Modifier.testTag("welcome-guest"), enabled = !busy)
                        if (inlineError != null) InlineAlert(inlineError)
                    }
                    Row(
                        Modifier.fillMaxWidth().padding(top = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(5.dp, Alignment.CenterHorizontally),
                    ) {
                        Text("사장님이신가요?", style = uxText(12f, 400, UxColor.muted))
                        Box(Modifier.heightIn(min = 48.dp)
                            .quietClick(enabled = !busy, onClick = onOwner)
                            .testTag("welcome-owner"), contentAlignment = Alignment.Center) {
                            Text("매장 등록하기", style = uxText(12f, 700, UxColor.gold))
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
