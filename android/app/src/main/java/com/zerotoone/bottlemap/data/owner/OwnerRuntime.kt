package com.zerotoone.bottlemap.data.owner

import com.zerotoone.bottlemap.ui.owner.review.ReviewSourceBitmapCache

import android.content.Context

/**
 * Real Owner runtime binding. The legacy OwnerMockRepository interface is
 * still used by the v20 UI adapter; no demo state or catalog fixture is
 * created here. Only LiveOwnerScreenRepository can serve production routes.
 */
object OwnerRuntime {
    @Volatile private var instance: OwnerMockRepository? = null
    private var boundUserId: String? = null

    /** Bind the Owner adapter to the profile already verified by /api/me.
     * Do not reuse an adapter carrying a different account's cached bars. */
    fun repository(context: Context, userId: String): OwnerMockRepository = synchronized(this) {
        require(userId.isNotBlank()) { "업주 계정을 확인해 주세요." }
        if (boundUserId != userId) {
            instance = null
            ReviewSourceBitmapCache.clearForAccountChange()
            boundUserId = userId
        }
        instance ?: LiveOwnerScreenRepository(context.applicationContext).also { instance = it }
    }

    /** Never reuse cached owner bars or imports after an account change. */
    fun invalidateForAccountChange() = synchronized(this) {
        instance = null
        boundUserId = null
        ReviewSourceBitmapCache.clearForAccountChange()
    }
}
