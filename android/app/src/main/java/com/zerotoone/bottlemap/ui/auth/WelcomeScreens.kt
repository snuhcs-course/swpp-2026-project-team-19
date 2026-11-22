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
import com.zerotoone.bottlemap.ui.common.BmLineIcon
import com.zerotoone.bottlemap.ui.common.BmLineIconId
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.platform.LocalContext
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.toggleable
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
    fun isAgeConfirmed(): Boolean = false
    fun confirmAge() {}
}

class SharedPrefsFirstLaunchStore(context: Context) : FirstLaunchStore {
    private val prefs = context.applicationContext.getSharedPreferences("bottlemap-first-launch", Context.MODE_PRIVATE)
    override fun isDone() = prefs.getBoolean(KEY_DONE, false) && isAgeConfirmed()
    override fun isAgeConfirmed() = prefs.getBoolean("age-18-confirmed", false)
    override fun confirmAge() = prefs.edit { putBoolean("age-18-confirmed", true) }
    override fun markDone() {
        check(isAgeConfirmed()) { "Age self-confirmation is required before entry" }
        prefs.edit { putBoolean(KEY_DONE, true) }
    }

    /** Debug builds only: show the welcome again for UX review. */
    fun reset() = prefs.edit { remove(KEY_DONE); remove("age-18-confirmed") }

    private companion object {
        const val KEY_DONE = "welcome-done"
    }
}

/** Approved Welcome HTML: original pin, headline, actions, owner link, aligned checks, policy. */
@Composable
fun WelcomeScreen(
    onBrowseAsGuest: () -> Unit,
    onGoogle: () -> Unit,
    onOwner: () -> Unit,
    busy: Boolean = false,
    inlineError: String? = null,
    onAgeConfirmed: () -> Unit = {},
    onNotice: (String) -> Unit = {},
) {
    val context = LocalContext.current
    val privacy = remember(context) { UserPrivacySettings.get(context) }
    val usageEnabled by privacy.usageEnabled.collectAsState()
    var ageChecked by rememberSaveable { mutableStateOf(false) }
    fun enter(action: () -> Unit) {
        if (ageChecked && !busy) { onAgeConfirmed(); action() }
    }
    BoxWithConstraints(Modifier.fillMaxSize().background(UxColor.bg).testTag("welcome-screen")) {
        val narrow = maxWidth < 350.dp
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        Column(Modifier.fillMaxWidth().heightIn(min = maxHeight)
            .padding(start = 20.dp, end = 20.dp, top = 22.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.SpaceBetween) {
            Image(painterResource(R.drawable.bottlemap_welcome_pin), "위스키 잔을 담은 지도 핀",
                Modifier.size(width = 79.dp, height = 97.dp).testTag("welcome-pin"),
                contentScale = ContentScale.Fit, alignment = Alignment.BottomStart)
            Text("Find the bottle first,\nthen the bar.",
                style = uxText(28f, 700, UxColor.text, 1.27f, serif = true, letterSpacing = (-0.9).sp),
                modifier = Modifier.fillMaxWidth().testTag("welcome-headline"))
            Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
                UxMainButton("Google로 계속", { enter(onGoogle) }, Modifier.testTag("welcome-google"), ageChecked && !busy)
                UxSecondaryButton("로그인 없이 둘러보기", { enter(onBrowseAsGuest) }, Modifier.testTag("welcome-guest"), ageChecked && !busy)
                if (inlineError != null) InlineAlert(inlineError)
            }
            Row(Modifier.fillMaxWidth().padding(top = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp, Alignment.CenterHorizontally)) {
                Text("사장님이신가요?", style = uxText(12f, 400, UxColor.muted))
                Box(Modifier.heightIn(min = 48.dp).quietClick(ageChecked && !busy) { enter(onOwner) }
                    .testTag("welcome-owner"), contentAlignment = Alignment.Center) {
                    Text("매장 등록하기", style = uxText(12f, 700, UxColor.gold))
                }
            }
            Row(Modifier.fillMaxWidth().padding(top = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(if(narrow) 10.dp else 16.dp, Alignment.CenterHorizontally),
                verticalAlignment = Alignment.CenterVertically) {
                WelcomeCheck("만 18세 이상인가요?", ageChecked, { ageChecked = it },
                    "welcome-age-confirmation", narrow)
                WelcomeCheck("사용 기록 보내기", usageEnabled, privacy::setUsageEnabled,
                    "welcome-usage-consent", narrow)
            }
            Text("사용 기록은 앱 개선에 사용해요.", style = uxText(11f, 400, UxColor.muted),
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp), textAlign = TextAlign.Center)
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                Text("개인정보처리방침", style = uxText(11f, 400, UxColor.sub),
                    textDecoration = TextDecoration.Underline,
                    modifier = Modifier.quietClick { openPrivacyPolicy(context, onNotice) }
                        .padding(6.dp).testTag("welcome-privacy"))
            }
        }
        }
    }
}

@Composable
private fun WelcomeCheck(label: String, checked: Boolean, onChecked: (Boolean) -> Unit, tag: String, narrow: Boolean) {
    Row(Modifier.heightIn(min = 44.dp).toggleable(checked, role = Role.Checkbox, onValueChange = onChecked)
        .testTag(tag), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(if(narrow) 6.dp else 7.dp)) {
        Box(Modifier.size(18.dp).background(if(checked) UxColor.gold else UxColor.surface, RoundedCornerShape(3.dp))
            .border(1.dp, if(checked) UxColor.gold else UxColor.outline, RoundedCornerShape(3.dp)),
            contentAlignment = Alignment.Center) {
            if(checked) BmLineIcon(BmLineIconId.CHECK,14.dp,UxColor.goldOn)
        }
        Text(label, style = uxText(if(narrow) 11f else 12f, 500, UxColor.text))
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
