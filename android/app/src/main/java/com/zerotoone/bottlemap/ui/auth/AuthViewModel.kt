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
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlin.coroutines.coroutineContext

sealed interface AuthUiState {
    data object Initializing : AuthUiState
    data object Guest : AuthUiState
    data object SigningIn : AuthUiState
    data class SignedIn(val user: CurrentUserDto) : AuthUiState
    /** Retry account sync only when a potentially valid Supabase session remains. */
    data class SignInError(
        val message: String,
        val canRetryProfile: Boolean = false,
    ) : AuthUiState
}

/**
 * One Activity-scoped UI state source. Every operation has a generation so a
 * previous /api/me result cannot resurrect a signed-out user's identity.
 */
class AuthViewModel(
    private val gateway: AuthGateway = AppAuth.gateway,
) : ViewModel() {
    private val _state = MutableStateFlow<AuthUiState>(AuthUiState.Initializing)
    val state: StateFlow<AuthUiState> = _state.asStateFlow()

    private var generation = 0L
    private var signingIn = false
    private var awaitingGoogleCredential = false
    private var logoutInProgress = false
    // Ignore a late SDK Authenticated emission after explicit logout until
    // the user intentionally begins a fresh Google sign-in.
    private var suppressAuthenticatedEventsUntilSignIn = false
    private var signInJob: Job? = null

    init {
        viewModelScope.launch {
            gateway.events.collectLatest { event ->
                when (event) {
                    AuthSessionEvent.Initializing -> {
                        if (!signingIn && !logoutInProgress &&
                            _state.value !is AuthUiState.SignedIn
                        ) {
                            _state.value = AuthUiState.Initializing
                        }
                    }
                    AuthSessionEvent.Guest -> {
                        // A definitive SDK sign-out always wins over a prior
                        // SignInError; a temporary backend 503 does not emit Guest.
                        if (!signingIn) {
                            if (!logoutInProgress) generation++
                            _state.value = AuthUiState.Guest
                        }
                    }
                    AuthSessionEvent.Refreshing -> {
                        // Supabase RefreshFailure is transient (network/server).
                        // Preserve a previously displayed identity; otherwise
                        // show a retryable message instead of endless loading.
                        if (!signingIn && !logoutInProgress &&
                            _state.value !is AuthUiState.SignedIn
                        ) {
                            _state.value = AuthUiState.SignInError(
                                "세션을 갱신하지 못했습니다. 연결을 확인하고 다시 시도해 주세요.",
                                canRetryProfile = true,
                            )
                        }
                    }
                    AuthSessionEvent.Authenticated -> {
                        if (!logoutInProgress && !suppressAuthenticatedEventsUntilSignIn) {
                            signingIn = false
                            awaitingGoogleCredential = false
                            loadProfile(++generation)
                        }
                    }
                }
            }
        }
    }

    /** Called once per user click before opening Credential Manager. */
    fun beginGoogleSignIn(): Boolean {
        if (signingIn || logoutInProgress ||
            _state.value == AuthUiState.Initializing ||
            _state.value is AuthUiState.SignedIn
        ) return false
        generation++
        suppressAuthenticatedEventsUntilSignIn = false
        signingIn = true
        awaitingGoogleCredential = true
        _state.value = AuthUiState.SigningIn
        return true
    }

    fun acceptGoogleCredential(idToken: String, rawNonce: String) {
        if (!signingIn || !awaitingGoogleCredential || logoutInProgress) return
        awaitingGoogleCredential = false
        val operationGeneration = generation
        signInJob = viewModelScope.launch {
            try {
                gateway.signInWithGoogleIdToken(idToken, rawNonce)
                // Authenticated SDK event triggers GET /api/me.
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                if (operationGeneration == generation && !logoutInProgress) {
                    signingIn = false
                    _state.value = AuthUiState.SignInError(
                        "로그인을 완료하지 못했습니다. 설정과 네트워크를 확인한 뒤 다시 시도해 주세요.",
                    )
                }
            } finally {
                if (signInJob === coroutineContext[Job]) signInJob = null
            }
        }
    }

    fun googleCancelled() {
        if (!signingIn || !awaitingGoogleCredential) return
        generation++
        signingIn = false
        awaitingGoogleCredential = false
        _state.value = AuthUiState.Guest
    }

    fun googleFailed() {
        if (!signingIn || !awaitingGoogleCredential) return
        generation++
        signingIn = false
        awaitingGoogleCredential = false
        _state.value = AuthUiState.SignInError(
            "Google 계정을 연결하지 못했습니다. 다시 시도할 수 있습니다.",
        )
    }

    /** Called on composition disposal (back, recreation) before token exchange. */
    fun cancelCredentialSelectionIfPending() = googleCancelled()

    fun continueAsGuest() {
        if (logoutInProgress) return
        // Immediately invalidate in-flight profile/sign-in work and hide the
        // old identity; do not wait for an SDK event or remote sign-out.
        val operationGeneration = ++generation
        logoutInProgress = true
        suppressAuthenticatedEventsUntilSignIn = true
        signingIn = false
        awaitingGoogleCredential = false
        signInJob?.cancel()
        _state.value = AuthUiState.Guest

        viewModelScope.launch {
            try {
                gateway.logout()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                // Gateway clears local Supabase credentials even if remote fails.
            } finally {
                if (generation == operationGeneration) logoutInProgress = false
            }
        }
    }

    fun logout() = continueAsGuest()

    fun retryAccountSync() {
        val error = _state.value as? AuthUiState.SignInError ?: return
        if (!error.canRetryProfile || logoutInProgress) return
        val operationGeneration = ++generation
        viewModelScope.launch { loadProfile(operationGeneration) }
    }

    private suspend fun loadProfile(operationGeneration: Long) {
        if (operationGeneration != generation || logoutInProgress) return
        _state.value = AuthUiState.Initializing
        try {
            val user = gateway.fetchCurrentUser()
            if (operationGeneration == generation && !logoutInProgress) {
                _state.value = AuthUiState.SignedIn(user)
            }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: BottleMapApiException) {
            if (operationGeneration != generation || logoutInProgress) return
            when (error.code) {
                "UNAUTHENTICATED" -> {
                    // Confirmed invalid session, not a network/503 outage.
                    // Guest is a normal usable state; do not retry /api/me.
                    continueAsGuest()
                }
                "SERVICE_UNAVAILABLE", "NETWORK_ERROR" -> {
                    _state.value = AuthUiState.SignInError(
                        if (error.code == "NETWORK_ERROR") {
                            "네트워크 연결을 확인해 주세요."
                        } else {
                            "인증 서버를 일시적으로 이용할 수 없습니다."
                        },
                        canRetryProfile = true,
                    )
                }
                else -> {
                    _state.value = AuthUiState.SignInError(
                        "계정 정보를 불러오지 못했습니다.",
                        canRetryProfile = true,
                    )
                }
            }
        } catch (_: Exception) {
            if (operationGeneration == generation && !logoutInProgress) {
                _state.value = AuthUiState.SignInError(
                    "계정 정보를 확인하지 못했습니다.",
                    canRetryProfile = true,
                )
            }
        }
    }
}
