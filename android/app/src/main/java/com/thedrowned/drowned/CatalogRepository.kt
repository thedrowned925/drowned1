package com.thedrowned.drowned

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class CatalogRepository {
    suspend fun load(owner: String, repo: String, branch: String): Catalog = withContext(Dispatchers.IO) {
        val url = URL("https://raw.githubusercontent.com/$owner/$repo/$branch/catalog.json")
        val connection = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = 15_000; readTimeout = 30_000; setRequestProperty("User-Agent", "Drowned-Mobile/0.1")
        }
        try {
            if (connection.responseCode !in 200..299) error("Catalog HTTP ${connection.responseCode}")
            parse(connection.inputStream.bufferedReader().use { it.readText() })
        } finally { connection.disconnect() }
    }

    private fun parse(raw: String): Catalog {
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
                    ReleaseChannel(c.getString("version"), c.getString("tag"), c.getString("manifest_url"), c.getLong("size"))
                }
                add(GameEntry(g.getString("id"), g.getString("title"), g.getString("platform"), g.optString("description"), artwork, channels))
            }
        }
        return Catalog(games)
    }
}
