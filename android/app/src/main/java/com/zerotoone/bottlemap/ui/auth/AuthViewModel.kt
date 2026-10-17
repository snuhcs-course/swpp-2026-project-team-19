// AI-assisted implementation (2026-10-17, I2-P19/P20/A5). Human verification pending.
package com.zerotoone.bottlemap.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.AppAuth
import com.zerotoone.bottlemap.data.AuthGateway
import com.zerotoone.bottlemap.data.AuthSessionEvent
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.CurrentUserDto
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

sealed interface AuthUiState {
    data object Initializing : AuthUiState
    data object Guest : AuthUiState
    data object SigningIn : AuthUiState
    data class SignedIn(val user: CurrentUserDto) : AuthUiState
    data class SignInError(val message: String) : AuthUiState
}

/** One auth state source shared by Login, My Page and navigation. */
class AuthViewModel(
    private val gateway: AuthGateway = AppAuth.gateway,
) : ViewModel() {
    private val _state = MutableStateFlow<AuthUiState>(AuthUiState.Initializing)
    val state: StateFlow<AuthUiState> = _state.asStateFlow()
    private var signingIn = false

    init {
        viewModelScope.launch {
            gateway.events.collectLatest { event ->
                when (event) {
                    AuthSessionEvent.Initializing -> {
                        if (!signingIn) _state.value = AuthUiState.Initializing
                    }
                    AuthSessionEvent.Guest -> {
                        if (!signingIn && _state.value !is AuthUiState.SignInError) {
                            _state.value = AuthUiState.Guest
                        }
                    }
                    AuthSessionEvent.Refreshing -> {
                        // Transient offline refresh does not destroy a stored session.
                        if (_state.value !is AuthUiState.SignedIn && !signingIn) {
                            _state.value = AuthUiState.Initializing
                        }
                    }
                    AuthSessionEvent.Authenticated -> {
                        signingIn = false
                        loadProfile()
                    }
                }
            }
        }
    }

    /** Called once per user click before launching Credential Manager. */
    fun beginGoogleSignIn(): Boolean {
        if (_state.value == AuthUiState.SigningIn ||
            _state.value == AuthUiState.Initializing ||
            _state.value is AuthUiState.SignedIn
        ) return false
        signingIn = true
        _state.value = AuthUiState.SigningIn
        return true
    }

    fun acceptGoogleCredential(idToken: String, rawNonce: String) {
        if (!signingIn) return
        viewModelScope.launch {
            try {
                gateway.signInWithGoogleIdToken(idToken, rawNonce)
                // SDK emits Authenticated, which calls GET /api/me through loadProfile().
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                signingIn = false
                _state.value = AuthUiState.SignInError(
                    "로그인을 완료하지 못했습니다. 설정과 네트워크를 확인한 뒤 다시 시도해 주세요.",
                )
            }
        }
    }

    fun googleCancelled() {
        if (!signingIn) return
        signingIn = false
        _state.value = AuthUiState.Guest
    }

    fun googleFailed() {
        if (!signingIn) return
        signingIn = false
        _state.value = AuthUiState.SignInError(
            "Google 계정을 연결하지 못했습니다. 다시 시도할 수 있습니다.",
        )
    }

    fun continueAsGuest() {
        signingIn = false
        viewModelScope.launch {
            try {
                gateway.logout()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                // Guest access must not be blocked by sign-out network errors.
            }
            _state.value = AuthUiState.Guest
        }
    }

    fun logout() = continueAsGuest()

    fun retryAccountSync() {
        if (_state.value !is AuthUiState.SignInError) return
        viewModelScope.launch { loadProfile() }
    }

    private suspend fun loadProfile() {
        _state.value = AuthUiState.Initializing
        try {
            val user = gateway.fetchCurrentUser()
            _state.value = AuthUiState.SignedIn(user)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: BottleMapApiException) {
            _state.value = AuthUiState.SignInError(
                when (error.code) {
                    "UNAUTHENTICATED" -> "세션이 만료되었습니다. 다시 로그인해 주세요."
                    "SERVICE_UNAVAILABLE" -> "인증 서버를 일시적으로 이용할 수 없습니다."
                    "NETWORK_ERROR" -> "네트워크 연결을 확인해 주세요."
                    else -> "계정 정보를 불러오지 못했습니다."
                },
            )
        } catch (_: Exception) {
            _state.value = AuthUiState.SignInError("계정 정보를 확인하지 못했습니다.")
        }
    }
}
