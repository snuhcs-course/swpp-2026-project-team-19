package com.zerotoone.bottlemap.data.owner

import android.content.Context

/**
 * Real Owner runtime binding. The legacy OwnerMockRepository interface is
 * still used by the v20 UI adapter; no demo state or catalog fixture is
 * created here. Only LiveOwnerScreenRepository can serve production routes.
 */
object OwnerRuntime {
    @Volatile private var instance: OwnerMockRepository? = null

    fun repository(context: Context): OwnerMockRepository = instance ?: synchronized(this) {
        instance ?: LiveOwnerScreenRepository(context.applicationContext).also { instance = it }
    }

    /** Never reuse cached owner bars or imports after an account change. */
    fun invalidateForAccountChange() = synchronized(this) { instance = null }
}
