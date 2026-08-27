package com.drowned.control

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

internal data class ControlUpdateInfo(
    val versionName: String,
    val versionCode: Int,
    val buildSha: String,
    val url: String,
    val sha256: String,
)

internal enum class InstallRequestResult {
    INSTALLER_OPENED,
    PERMISSION_REQUIRED,
}

internal object UpdateManager {
    private const val RELEASE_API =
        "https://api.github.com/repos/thedrowned925/drowned1/releases/tags/control-nightly"
    private const val MANIFEST_ASSET = "control-update.json"
    private const val EXPECTED_APK_PREFIX =
        "https://github.com/thedrowned925/drowned1/releases/download/control-nightly/"
    private const val USER_AGENT = "Drowned-Control-Updater/1.0"

    suspend fun checkForUpdate(): ControlUpdateInfo? = withContext(Dispatchers.IO) {
        val release = getJson(RELEASE_API) ?: return@withContext null
        val assets = release.optJSONArray("assets") ?: return@withContext null
        var manifestUrl: String? = null
        for (index in 0 until assets.length()) {
            val asset = assets.optJSONObject(index) ?: continue
            if (asset.optString("name") == MANIFEST_ASSET) {
                manifestUrl = asset.optString("browser_download_url").takeIf { it.startsWith("https://") }
                break
            }
        }
        val rawManifestUrl = manifestUrl ?: return@withContext null
        val separator = if (rawManifestUrl.contains('?')) "&" else "?"
        val manifest = getJson("$rawManifestUrl${separator}nocache=${System.nanoTime()}")
            ?: return@withContext null
        val android = manifest.optJSONObject("android") ?: return@withContext null
        if (!android.optBoolean("available", false)) return@withContext null

        val versionCode = android.optInt("version_code", 0)
        if (versionCode <= BuildConfig.VERSION_CODE) return@withContext null

        val url = android.optString("url")
        val sha256 = android.optString("sha256").lowercase()
        if (!url.startsWith(EXPECTED_APK_PREFIX)) return@withContext null
        if (!sha256.matches(Regex("[0-9a-f]{64}"))) return@withContext null

        ControlUpdateInfo(
            versionName = manifest.optString("version", versionCode.toString()),
            versionCode = versionCode,
            buildSha = manifest.optString("build_sha"),
            url = url,
            sha256 = sha256,
        )
    }

    suspend fun download(context: Context, update: ControlUpdateInfo): File = withContext(Dispatchers.IO) {
        val directory = File(context.cacheDir, "updates").apply { mkdirs() }
        directory.listFiles()?.forEach { file ->
            if (file.name.endsWith(".apk") || file.name.endsWith(".part")) {
                runCatching { file.delete() }
            }
        }

        val partial = File(directory, "Drowned-Control-${update.versionCode}.apk.part")
        val target = File(directory, "Drowned-Control-${update.versionCode}.apk")
        val digest = MessageDigest.getInstance("SHA-256")

        val connection = open(update.url)
        try {
            val code = connection.responseCode
            if (code !in 200..299) error("GitHub APK indirme hatası: HTTP $code")
            connection.inputStream.use { input ->
                partial.outputStream().use { output ->
                    val buffer = ByteArray(1024 * 1024)
                    while (true) {
                        val count = input.read(buffer)
                        if (count <= 0) break
                        digest.update(buffer, 0, count)
                        output.write(buffer, 0, count)
                    }
                }
            }
        } finally {
            connection.disconnect()
        }

        val actual = digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
        if (actual != update.sha256) {
            partial.delete()
            error("APK SHA-256 doğrulaması başarısız.")
        }
        if (target.exists()) target.delete()
        if (!partial.renameTo(target)) {
            partial.delete()
            error("APK güncelleme dosyası hazırlanamadı.")
        }
        target
    }

    fun requestInstall(context: Context, apk: File): InstallRequestResult {
        if (!context.packageManager.canRequestPackageInstalls()) {
            val settings = Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:${context.packageName}"),
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(settings)
            return InstallRequestResult.PERMISSION_REQUIRED
        }

        val uri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            apk,
        )
        val install = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(install)
        return InstallRequestResult.INSTALLER_OPENED
    }

    private fun getJson(url: String): JSONObject? {
        val connection = open(url)
        return try {
            val code = connection.responseCode
            if (code == 404) return null
            if (code !in 200..299) error("GitHub güncelleme hatası: HTTP $code")
            val text = connection.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            JSONObject(text)
        } finally {
            connection.disconnect()
        }
    }

    private fun open(url: String): HttpURLConnection {
        return (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 8_000
            readTimeout = 30_000
            instanceFollowRedirects = true
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("User-Agent", USER_AGENT)
            setRequestProperty("Cache-Control", "no-cache")
        }
    }
}
