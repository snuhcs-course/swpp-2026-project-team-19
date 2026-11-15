package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewRepository
import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewScenario
import com.zerotoone.bottlemap.data.owner.review.PhotoReviewRepository
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewScreen
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewViewModel
import kotlinx.coroutines.CompletableDeferred
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PhotoReviewPublicationLoadingComposeTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun publishingReusesPhotoGlassAnimationInsteadOfSpinnerAndProgressBar() {
        val release = CompletableDeferred<Unit>()
        val base = MockPhotoReviewRepository(MockPhotoReviewScenario.READY)
        val repository = object : PhotoReviewRepository by base {
            override suspend fun publish(state: PhotoReviewState) {
                release.await()
            }
        }
        val vm = PhotoReviewViewModel(repository)
        compose.setContent {
            MaterialTheme {
                PhotoReviewScreen(vm = vm, onLeave = {})
            }
        }
        compose.runOnIdle {
            vm.requestPublish()
            vm.confirmPublish()
        }
        compose.onNodeWithTag("review-publish-result").assertExists()
        compose.onNodeWithTag("review-publish-loading-glass").assertExists()
        compose.onNodeWithText("메뉴를 게시하고 있어요.").assertExists()
        release.complete(Unit)
    }
}
