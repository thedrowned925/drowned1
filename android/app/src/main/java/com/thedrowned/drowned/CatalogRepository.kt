package com.thedrowned.drowned

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class CatalogRepository {
    suspend fun load(owner: String, repo: String, branch: String): Catalog = withContext(Dispatchers.IO) {
        val normalizedBranch = branch.ifBlank { "main" }
        val url = URL(rawUrl(owner, repo, normalizedBranch, "catalog.json"))
        val connection = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = 15_000; readTimeout = 30_000
            setRequestProperty("User-Agent", "Drowned-Mobile/0.2")
            setRequestProperty("Cache-Control", "no-cache")
        }
        try {
            if (connection.responseCode !in 200..299) error("Catalog HTTP ${connection.responseCode}")
            parse(connection.inputStream.bufferedReader().use { it.readText() }, owner, repo, normalizedBranch)
        } finally { connection.disconnect() }
    }

    @Suppress("DEPRECATION")
    private fun encodeSegment(value: String): String = URLEncoder.encode(value, "UTF-8").replace("+", "%20")

    private fun rawUrl(owner: String, repo: String, branch: String, path: String): String {
        val encodedPath = path.trim('/').split('/').joinToString("/") { encodeSegment(it) }
        return "https://raw.githubusercontent.com/${encodeSegment(owner)}/${encodeSegment(repo)}/${encodeSegment(branch)}/$encodedPath"
    }

    private fun parse(raw: String, owner: String, repo: String, branch: String): Catalog {
        val root = JSONObject(raw)
        require(root.optInt("schema_version") == 1) { "Unsupported catalog schema" }
        val list = root.getJSONArray("games")
        val games = buildList {
            for (i in 0 until list.length()) {
                val g = list.getJSONObject(i)
                val artworkObj = g.optJSONObject("artwork") ?: JSONObject()
                val artwork = artworkObj.keys().asSequence().associateWith { artworkObj.getString(it) }
                val channelObj = g.getJSONObject("channels")
                val channels = channelObj.keys().asSequence().associateWith { key ->
                    val c = channelObj.getJSONObject(key)
                    val manifestPath = c.optString("manifest_path")
                    val manifestUrl = if (manifestPath.isNotBlank()) rawUrl(owner, repo, branch, manifestPath) else c.getString("manifest_url")
                    ReleaseChannel(c.getString("version"), c.getString("tag"), manifestPath, manifestUrl, c.getLong("size"))
                }
                add(GameEntry(g.getString("id"), g.getString("title"), g.getString("platform"), g.optString("description"), artwork, channels))
            }
        }
        return Catalog(games)
    }
}
