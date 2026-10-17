// AI-assisted implementation (2026-10-17, I2-P19/P20/A5). Device verification pending.
package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.BuildConfig
import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.CurrentUserDto
import io.github.jan.supabase.auth.Auth
import io.github.jan.supabase.auth.auth
import io.github.jan.supabase.auth.providers.Google
import io.github.jan.supabase.auth.providers.IDToken
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
                // Broken developer console configuration must not crash Guest UX.
                emit(AuthSessionEvent.Guest)
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
                client.auth.refreshCurrentSession().accessToken
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: IOException) {
                // Offline refresh is transient: preserve the SDK-stored session.
                null
            } catch (_: Exception) {
                runCatching { client.auth.signOut() }
                client.auth.clearSession()
                null
            }
        }
    }

    override suspend fun fetchCurrentUser(): CurrentUserDto {
        val token = currentAccessTokenOrNull()
            ?: throw BottleMapApiException(code = "UNAUTHENTICATED", message = "로그인 세션이 없습니다.")
        return try {
            ApiClient.call { ApiClient.api.getMe("Bearer $token") }
        } catch (error: BottleMapApiException) {
            if (error.code != "UNAUTHENTICATED") throw error
            val refreshed = refreshAccessTokenAfter401(token)
                ?: throw BottleMapApiException(
                    code = "UNAUTHENTICATED",
                    message = "세션이 만료되었습니다. 다시 로그인해 주세요.",
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
