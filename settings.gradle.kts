// AI-generated with ChatGPT (Hojin Nam, 2026-10-03, PR #1, #7). Reviewed by Hojin Nam.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "BottleMap"
include(":app")
project(":app").projectDir = file("android/app")
