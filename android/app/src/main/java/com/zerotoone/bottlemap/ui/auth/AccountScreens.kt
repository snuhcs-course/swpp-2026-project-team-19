// AI-assisted implementation (2026-10-17, I2-P19/P20/A5). Human verification pending.
package com.zerotoone.bottlemap.ui.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.zerotoone.bottlemap.ui.customer.I2CustomerSearchTheme

/** Figma P1 guest / P2 member account surface, available without signing in. */
@Composable
fun AccountScreen(
    state: AuthUiState,
    onBack: () -> Unit,
    onOpenLogin: () -> Unit,
    onLogout: () -> Unit,
    onRetryAccount: () -> Unit,
) {
    I2CustomerSearchTheme {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background),
        ) {
            AccountHeader("마이페이지", onBack)
            Column(
                modifier = Modifier.fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(18.dp),
            ) {
                Text(
                    "내 계정",
                    color = MaterialTheme.colorScheme.onBackground,
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                )
                when (state) {
                    AuthUiState.Initializing -> AccountPanel(
                        "세션을 확인하고 있습니다.",
                        "기존 Guest 검색은 로그인 없이 사용할 수 있습니다.",
                    ) { CircularProgressIndicator() }
                    AuthUiState.Guest -> {
                        AccountPanel(
                            "Guest로 이용 중",
                            "로그인 없이 위스키를 검색할 수 있어요.",
                        )
                        Button(onClick = onOpenLogin, modifier = Modifier.fillMaxWidth()) {
                            Text("Google 계정으로 로그인")
                        }
                    }
                    AuthUiState.SigningIn -> AccountPanel("로그인 중", "Google 계정 연결을 확인 중입니다.") {
                        CircularProgressIndicator()
                    }
                    is AuthUiState.SignedIn -> {
                        val name = state.user.displayName?.takeIf { it.isNotBlank() }
                            ?: state.user.email?.takeIf { it.isNotBlank() }
                            ?: "BottleMap 사용자"
                        AccountPanel(name, "Google 계정이 연결되어 있습니다.") {
                            state.user.email?.let {
                                Text(
                                    it,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    style = MaterialTheme.typography.bodySmall,
                                )
                            }
                            Text(
                                "로그인 상태 · " + state.user.userType,
                                color = MaterialTheme.colorScheme.primary,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        OutlinedButton(onClick = onLogout, modifier = Modifier.fillMaxWidth()) {
                            Text("로그아웃")
                        }
                    }
                    is AuthUiState.SignInError -> {
                        AccountPanel("계정 확인이 필요해요", state.message)
                        if (state.canRetryProfile) {
                            Button(onClick = onRetryAccount, modifier = Modifier.fillMaxWidth()) {
                                Text("계정 확인 다시 시도")
                            }
                        } else {
                            Button(onClick = onOpenLogin, modifier = Modifier.fillMaxWidth()) {
                                Text("Google 계정으로 로그인")
                            }
                        }
                        OutlinedButton(onClick = onLogout, modifier = Modifier.fillMaxWidth()) {
                            Text("Guest로 계속")
                        }
                    }
                }
                Text(
                    "위스키 검색·바 상세·지도는 로그인 없이 이용할 수 있습니다.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/** Figma A1 / A2 login, reached only when the user explicitly requests it. */
@Composable
fun GoogleLoginScreen(
    state: AuthUiState,
    authViewModel: AuthViewModel,
    onBack: () -> Unit,
    onContinueGuest: () -> Unit,
) {
    I2CustomerSearchTheme {
        Column(
            modifier = Modifier.fillMaxSize()
                .background(MaterialTheme.colorScheme.background),
        ) {
            AccountHeader("로그인", onBack)
            Column(
                modifier = Modifier.fillMaxSize().padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(20.dp),
            ) {
                Text(
                    "Google 계정으로 선택적으로 로그인해요.",
                    color = MaterialTheme.colorScheme.onBackground,
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    "로그인하지 않아도 BottleMap의 검색, 바 상세, 지도를 사용할 수 있어요.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyMedium,
                )
                when (state) {
                    AuthUiState.SigningIn, AuthUiState.Initializing -> {
                        CircularProgressIndicator()
                        Text("로그인을 처리하고 있습니다.")
                    }
                    is AuthUiState.SignInError -> {
                        Text(state.message, color = MaterialTheme.colorScheme.error)
                    }
                    is AuthUiState.SignedIn -> Text("Google 로그인 성공", color = MaterialTheme.colorScheme.primary)
                    AuthUiState.Guest -> Unit
                }
                GoogleSignInButton(
                    viewModel = authViewModel,
                    enabled = state is AuthUiState.Guest || state is AuthUiState.SignInError,
                )
                OutlinedButton(
                    onClick = onContinueGuest,
                    enabled = state != AuthUiState.SigningIn,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("취소하고 Guest로 계속") }
                Text(
                    "로그인 취소/실패 후에도 검색할 수 있습니다.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Composable
private fun AccountHeader(title: String, onBack: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        TextButton(onClick = onBack) { Text("←") }
        Text(
            title,
            color = MaterialTheme.colorScheme.onBackground,
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun AccountPanel(
    title: String,
    message: String,
    additional: @Composable () -> Unit = {},
) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = title,
                color = MaterialTheme.colorScheme.onSurface,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = message,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
            additional()
        }
    }
}
