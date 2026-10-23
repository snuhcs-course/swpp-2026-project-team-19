package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.BuildConfig
import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.CurrentUserDto
import io.github.jan.supabase.auth.Auth
import io.github.jan.supabase.auth.auth
import io.github.jan.supabase.auth.exception.AuthErrorCode
import io.github.jan.supabase.auth.exception.AuthRestException
import io.github.jan.supabase.auth.providers.Google
import io.github.jan.supabase.auth.providers.builtin.IDToken
import io.github.jan.supabase.auth.status.SessionStatus
import io.github.jan.supabase.createSupabaseClient
import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.collect

import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

sealed interface AuthSessionEvent {
    data object Initializing : AuthSessionEvent
    data object Guest : AuthSessionEvent
    data object Refreshing : AuthSessionEvent
    data object Authenticated : AuthSessionEvent
}

/** Minimal test seam; token storage and refresh are managed only by Supabase SDK. */
interface AuthGateway {
    val events: Flow<AuthSessionEvent>
    suspend fun signInWithGoogleIdToken(idToken: String, rawNonce: String)
    suspend fun fetchCurrentUser(): CurrentUserDto
    suspend fun logout()
}

class SupabaseGoogleAuthGateway : AuthGateway {
    private val configured = BuildConfig.SUPABASE_URL.startsWith("https://") &&
        BuildConfig.SUPABASE_PUBLISHABLE_KEY.isNotBlank()
    private val client by lazy {
        check(configured) { "Supabase is not configured for this build." }
        createSupabaseClient(
            supabaseUrl = BuildConfig.SUPABASE_URL,
            supabaseKey = BuildConfig.SUPABASE_PUBLISHABLE_KEY,
        ) {
            install(Auth) {
                autoLoadFromStorage = true
                autoSaveToStorage = true
                alwaysAutoRefresh = true
            }
        }
    }
    private val refreshMutex = Mutex()

    override val events: Flow<AuthSessionEvent> = flow {
        emit(AuthSessionEvent.Initializing)
        if (!configured) {
            emit(AuthSessionEvent.Guest)
        } else {
            try {
                client.auth.sessionStatus.collect { status ->
                    emit(when (status) {
                        SessionStatus.Initializing -> AuthSessionEvent.Initializing
                        is SessionStatus.NotAuthenticated -> AuthSessionEvent.Guest
                        is SessionStatus.Authenticated -> AuthSessionEvent.Authenticated
                        is SessionStatus.RefreshFailure -> AuthSessionEvent.Refreshing
                    })
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                // An SDK initialization outage does not prove no saved session.
                // Show a recoverable account error; Guest search is independent.
                emit(AuthSessionEvent.Refreshing)
            }
        }
    }

    override suspend fun signInWithGoogleIdToken(idToken: String, rawNonce: String) {
        check(configured) { "Google/Supabase 로그인 설정이 필요합니다." }
        client.auth.signInWith(IDToken) {
            provider = Google
            this.idToken = idToken
            nonce = rawNonce
        }
    }

    /** Always read the SDK's current session. Never cache the access token in UI state. */
    suspend fun currentAccessTokenOrNull(): String? {
        if (!configured) return null
        return try {
            client.auth.awaitInitialization()
            client.auth.currentSessionOrNull()?.accessToken
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            // Misconfiguration/temporary SDK failure cannot block guest bar data.
            null
        }
    }

    /**
     * Prevent multiple 401s from rotating the same refresh token simultaneously.
     * If another caller refreshed meanwhile, reuse its new token.
     */
    suspend fun refreshAccessTokenAfter401(staleToken: String): String? {
        if (!configured) return null
        return refreshMutex.withLock {
            val current = client.auth.currentSessionOrNull()?.accessToken ?: return@withLock null
            if (current != staleToken) return@withLock current
            try {
                client.auth.refreshCurrentSession()
                client.auth.currentSessionOrNull()?.accessToken
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: AuthRestException) {
                // Only known invalid/revoked refresh tokens justify dropping
                // local credentials. A 5xx/temporary service failure must not.
                if (error.errorCode in setOf(
                        AuthErrorCode.RefreshTokenNotFound,
                        AuthErrorCode.RefreshTokenAlreadyUsed,
                        AuthErrorCode.SessionNotFound,
                        AuthErrorCode.SessionExpired,
                        AuthErrorCode.InvalidCredentials,
                    )
                ) {
                    client.auth.clearSession()
                }
                null
            } catch (_: IOException) {
                // Offline refresh is transient: preserve the SDK-stored session.
                null
            } catch (_: Exception) {
                // Unknown SDK/transport errors should not erase valid storage.
                // The SDK may already have emitted a definitive Guest event.
                null
            }
        }
    }

    override suspend fun fetchCurrentUser(): CurrentUserDto {
        // Protected /api/me is not a Guest request. Distinguish an absent
        // Supabase session from an offline SDK initialization/refresh failure.
        val token = if (!configured) null else try {
            client.auth.awaitInitialization()
            if (client.auth.sessionStatus.value is SessionStatus.RefreshFailure) {
                throw BottleMapApiException(
                    code = "NETWORK_ERROR",
                    message = "Supabase 세션 갱신 중 연결을 확인해 주세요.",
                )
            }
            client.auth.currentSessionOrNull()?.accessToken
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: BottleMapApiException) {
            throw error
        } catch (_: Exception) {
            throw BottleMapApiException(
                code = "NETWORK_ERROR",
                message = "Supabase 세션을 확인할 수 없습니다. 다시 시도해 주세요.",
            )
        }
        if (token == null) {
            throw BottleMapApiException(
                code = "UNAUTHENTICATED",
                message = "로그인 세션이 없습니다.",
            )
        }
        return try {
            ApiClient.call { ApiClient.api.getMe("Bearer $token") }
        } catch (error: BottleMapApiException) {
            if (error.code != "UNAUTHENTICATED") throw error
            val refreshed = refreshAccessTokenAfter401(token)
                ?: throw BottleMapApiException(
                    // An offline refresh may leave a valid persisted session.
                    // Treat that as transient, not as a confirmed logout.
                    code = if (
                        client.auth.sessionStatus.value is SessionStatus.RefreshFailure ||
                        currentAccessTokenOrNull() != null
                    ) {
                        "NETWORK_ERROR"
                    } else {
                        "UNAUTHENTICATED"
                    },
                    message = "세션을 갱신할 수 없습니다. 연결 상태를 확인해 주세요.",
                )
            try {
                ApiClient.call { ApiClient.api.getMe("Bearer $refreshed") }
            } catch (retryError: BottleMapApiException) {
                if (retryError.code == "UNAUTHENTICATED") {
                    logout()
                }
                throw retryError
            }
        }
    }

    override suspend fun logout() {
        if (!configured) return
        try {
            // A remote outage must not block returning to Guest indefinitely.
            withTimeoutOrNull(3_000L) { client.auth.signOut() }
        } finally {
            // Also drop local credentials on failed/offline remote sign-out.
            client.auth.clearSession()
        }
    }
}

/** Single app-wide session source. Existing Guest search remains independent. */
object AppAuth {
    val gateway: SupabaseGoogleAuthGateway by lazy { SupabaseGoogleAuthGateway() }
}
