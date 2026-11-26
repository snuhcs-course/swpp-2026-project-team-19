package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.MapBarsResponseDto
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Spec 3.19 has the same response as map-bars, with no location parameters.
 * Share public bar metadata in memory across nearby/map screens. A short TTL
 * lets newly approved/deactivated bars appear without restarting the app.
 * Neither customer coordinates nor a location-derived result is cached here.
 */
class AllBarsRepository(
    private val fetch: suspend () -> MapBarsResponseDto = {
        ApiClient.call { ApiClient.api.getAllBars() }
    },
    private val clock: () -> Long = { System.nanoTime() / 1_000_000 },
) {
    private val mutex = Mutex()
    private var cached: List<MapBar>? = null
    private var loadedAt = 0L

    suspend fun listBars(): List<MapBar> = mutex.withLock {
        cached?.let { bars ->
            if (clock() - loadedAt < CACHE_TTL_MS) return@withLock bars
        }
        // Store only a completely decoded/validated success, including [].
        // Failed/cancelled requests must remain retryable and release the lock.
        fetch().toMapBars().also {
            cached = it
            loadedAt = clock()
        }
    }

    internal companion object {
        const val CACHE_TTL_MS = 60_000L
    }
}
