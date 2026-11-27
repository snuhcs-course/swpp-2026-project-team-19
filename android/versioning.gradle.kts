import java.nio.ByteBuffer
import java.nio.channels.FileChannel
import java.nio.file.StandardOpenOption
import java.time.Instant

// ValueSource is re-evaluated even with configuration caching. One allocation is
// shared by all variants/tasks in this invocation; clean never resets the counter.
abstract class BuildVersionCode : ValueSource<Int, BuildVersionCode.Parameters> {
    interface Parameters : ValueSourceParameters {
        val counterFile: RegularFileProperty
    }

    override fun obtain(): Int {
        val counter = parameters.counterFile.get().asFile
        counter.parentFile.mkdirs()
        return FileChannel.open(counter.toPath(), StandardOpenOption.CREATE,
            StandardOpenOption.READ, StandardOpenOption.WRITE).use { channel ->
            channel.lock().use {
                check(channel.size() <= 32) { "Invalid version counter: $counter" }
                val buffer = ByteBuffer.allocate(32)
                channel.read(buffer)
                buffer.flip()
                val saved = Charsets.UTF_8.decode(buffer).toString().trim()
                val previous = if (saved.isEmpty()) 1L else saved.toLongOrNull()
                    ?: error("Invalid version counter: $counter")
                check(previous in 1L until 2_100_000_000L) { "Version counter out of range: $counter" }
                // Seconds since 2020-01-01 UTC keep fresh CI checkouts ordered by
                // build time, while remaining below Android's versionCode limit.
                val next = maxOf(previous + 1, Instant.now().epochSecond - 1_577_836_800L)
                check(next in 2L..2_100_000_000L) { "versionCode exhausted" }
                channel.position(0)
                val bytes = ByteBuffer.wrap(next.toString().toByteArray(Charsets.UTF_8))
                while (bytes.hasRemaining()) channel.write(bytes)
                channel.truncate(channel.position())
                channel.force(true)
                next.toInt()
            }
        }
    }
}

// Change the public release name here (or override explicitly when preparing a release).
val appVersionName = providers.gradleProperty("BOTTLEMAP_VERSION_NAME").orElse("0.1.0").get()
require(appVersionName.matches(Regex("(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)"))) {
    "BOTTLEMAP_VERSION_NAME must be major.minor.patch, for example 0.1.0"
}
val expectedVersionTag = "android/v$appVersionName"
val headVersionTags = providers.exec {
    workingDir(rootDir)
    commandLine("git", "tag", "--points-at", "HEAD", "--list", "android/v*")
}.standardOutput.asText.get().lineSequence().filter { it.isNotBlank() }.toList()
require(headVersionTags.all { it == expectedVersionTag }) {
    "Android tag(s) $headVersionTags do not match versionName $appVersionName; expected $expectedVersionTag"
}
val appVersionCode = providers.of(BuildVersionCode::class) {
    parameters.counterFile.set(rootProject.layout.projectDirectory.file(".gradle/bottlemap/version-code"))
}.get()
logger.lifecycle("BottleMap version: $appVersionName ($appVersionCode); release tag: $expectedVersionTag")

extra["bottlemapVersionCode"] = appVersionCode
extra["bottlemapVersionName"] = appVersionName
