package com.zerotoone.bottlemap.navigation

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

/** Protects the release source set from returning to retired UX/Mock routes. */
class AndroidReleaseSourceBoundaryTest {
    @Test fun mainSourcesNeverReferenceDebugOnlyOcrFixturesOrRetiredRoutes() {
        val cwd = File(System.getProperty("user.dir")).absoluteFile
        val sourceRoot = generateSequence(cwd) { it.parentFile }
            .flatMap { ancestor ->
                sequenceOf(
                    File(ancestor, "android/app/src/main/java"),
                    File(ancestor, "app/src/main/java"),
                )
            }.firstOrNull { it.isDirectory }
        assertTrue("Cannot locate Android production source directory", sourceRoot != null)
        val retired = listOf(
            "MockPhotoReviewRepository",
            "MockPhotoReviewScenario",
            "PreviewOnlyPhotoReviewRepository",
            "OwnerMockFixtures",
            "AndroidOwnerMockStateStore",
            "OwnerMockRuntime",
            "OwnerRoutes.LEGACY_UPLOAD",
            "TabRoutes.DEV_PHOTO_REVIEW",
        )
        val violations = sourceRoot!!.walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .flatMap { file ->
                retired.asSequence().filter { token -> file.readText().contains(token) }
                    .map { token -> "${file.name}: $token" }
            }.toList()
        assertTrue("Release still references debug-only fixtures: $violations",
            violations.isEmpty())
    }
}
