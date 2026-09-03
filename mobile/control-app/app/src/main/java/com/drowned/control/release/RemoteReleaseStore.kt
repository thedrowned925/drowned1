package com.drowned.control.release

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URLEncoder
import java.net.URL

private const val REMOTE_SUPABASE_URL = "https://hfigrspqyxhscbkmporz.supabase.co"
private const val REMOTE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhmaWdyc3BxeXhoc2Nia21wb3J6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgzOTY0NjIsImV4cCI6MjEwMzk3MjQ2Mn0.7esPHfTAIS19KKniUi6Klo1Fgoze2-y6jOOlhHlZaGg"
private const val REMOTE_COMMAND_URL = "$REMOTE_SUPABASE_URL/functions/v1/release-remote-command"
private const val REMOTE_COMMANDS_TABLE = "$REMOTE_SUPABASE_URL/rest/v1/remote_commands"
private const val REMOTE_PREFS = "drowned_remote_release"
private const val REMOTE_TOKEN_KEY = "pairing_token"
private const val MACHINE_ID = "primary"


data class RemoteFolder(
    val name: String,
    val path: String,
    val diskFree: Long = 0,
)

data class RemotePcState(
    val title: String = "",
    val steamAppId: String = "",
    val steamStatus: String = "",
    val description: String = "",
    val platform: String = "",
    val channel: String = "",
    val version: String = "1.0.0",
    val source: String = "",
    val uploadRunning: Boolean = false,
    val steamBusy: Boolean = false,
    val artworkHero: Boolean = false,
    val artworkCover: Boolean = false,
    val artworkLogo: Boolean = false,
    val screenshots: Int = 0,
    val trailers: Int = 0,
)

data class RemoteDirectory(
    val path: String,
    val parent: String,
    val folders: List<RemoteFolder>,
    val diskFree: Long,
)

object RemotePairingStore {
    fun load(context: Context): String =
        context.getSharedPreferences(REMOTE_PREFS, Context.MODE_PRIVATE)
            .getString(REMOTE_TOKEN_KEY, "")
            .orEmpty()

    fun save(context: Context, token: String) {
        context.getSharedPreferences(REMOTE_PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(REMOTE_TOKEN_KEY, token.trim())
            .apply()
    }

    fun clear(context: Context) {
        context.getSharedPreferences(REMOTE_PREFS, Context.MODE_PRIVATE)
            .edit()
            .remove(REMOTE_TOKEN_KEY)
            .apply()
    }
}

object RemoteReleaseApi {
    suspend fun ping(token: String): RemotePcState = commandState(token, "ping", JSONObject(), 20_000L)

    suspend fun getState(token: String): RemotePcState = commandState(token, "get_state", JSONObject(), 20_000L)

    suspend fun fetchSteam(token: String, appId: String): RemotePcState =
        commandState(
            token,
            "fetch_steam",
            JSONObject().put("app_id", appId.trim()),
            120_000L,
        )

    suspend fun listRoots(token: String): List<RemoteFolder> {
        val result = command(token, "list_roots", JSONObject(), 25_000L)
        val array = result.optJSONArray("roots") ?: JSONArray()
        return buildList {
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                add(
                    RemoteFolder(
                        name = item.optString("name"),
                        path = item.optString("path"),
                        diskFree = item.optLong("disk_free", 0L),
                    )
                )
            }
        }
    }

    suspend fun listDirectory(token: String, path: String): RemoteDirectory {
        val result = command(token, "list_dir", JSONObject().put("path", path), 25_000L)
        val array = result.optJSONArray("folders") ?: JSONArray()
        val folders = buildList {
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                add(RemoteFolder(item.optString("name"), item.optString("path")))
            }
        }
        return RemoteDirectory(
            path = result.optString("path"),
            parent = result.optString("parent"),
            folders = folders,
            diskFree = result.optLong("disk_free", 0L),
        )
    }

    suspend fun selectSource(token: String, path: String): RemotePcState =
        commandState(token, "select_source", JSONObject().put("path", path), 30_000L)

    suspend fun setPublishFields(
        token: String,
        title: String,
        version: String,
        platform: String,
        channel: String,
        description: String,
    ): RemotePcState = commandState(
        token,
        "set_publish_fields",
        JSONObject()
            .put("title", title)
            .put("version", version)
            .put("platform", platform)
            .put("channel", channel)
            .put("description", description),
        25_000L,
    )

    suspend fun startUpload(
        token: String,
        state: RemotePcState,
        source: String,
    ): RemotePcState = commandState(
        token,
        "start_upload",
        JSONObject()
            .put("title", state.title)
            .put("version", state.version)
            .put("platform", state.platform)
            .put("channel", state.channel)
            .put("description", state.description)
            .put("source", source),
        40_000L,
    )

    private suspend fun commandState(
        token: String,
        commandType: String,
        payload: JSONObject,
        timeoutMs: Long,
    ): RemotePcState = parseState(command(token, commandType, payload, timeoutMs))

    private suspend fun command(
        token: String,
        commandType: String,
        payload: JSONObject,
        timeoutMs: Long,
    ): JSONObject = withContext(Dispatchers.IO) {
        require(token.trim().length >= 24) { "Eşleştirme kodu geçersiz." }
        val commandId = submit(token.trim(), commandType, payload)
        waitForResult(token.trim(), commandId, timeoutMs)
    }

    private fun submit(token: String, commandType: String, payload: JSONObject): String {
        val connection = (URL(REMOTE_COMMAND_URL).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 7_000
            readTimeout = 12_000
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "Drowned-Control-Android/1.3")
        }
        return try {
            val body = JSONObject()
                .put("machine_id", MACHINE_ID)
                .put("remote_token", token)
                .put("command_type", commandType)
                .put("payload", payload)
                .toString()
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            val json = JSONObject(text.ifBlank { "{}" })
            if (code !in 200..299) {
                val error = json.optString("error", "HTTP $code")
                if (error == "pairing_rejected") throw IllegalStateException("Eşleştirme kodu PC ile uyuşmuyor.")
                throw IllegalStateException("Uzaktan komut gönderilemedi: $error")
            }
            json.optString("id").takeIf { it.isNotBlank() }
                ?: throw IllegalStateException("Komut ID alınamadı.")
        } finally {
            connection.disconnect()
        }
    }

    private suspend fun waitForResult(token: String, commandId: String, timeoutMs: Long): JSONObject {
        val started = System.currentTimeMillis()
        while (System.currentTimeMillis() - started < timeoutMs) {
            val row = fetchCommand(token, commandId)
            when (row?.optString("status")) {
                "done" -> return row.optJSONObject("result") ?: JSONObject()
                "error" -> throw IllegalStateException(row.optString("error", "PC komutu başarısız oldu."))
                "cancelled" -> throw IllegalStateException("PC komutu iptal edildi.")
            }
            delay(700L)
        }
        throw IllegalStateException("PC yanıt vermedi. Release Manager'ın açık ve uzaktan kontrol durumunun hazır olduğundan emin ol.")
    }

    private fun fetchCommand(token: String, commandId: String): JSONObject? {
        val encoded = URLEncoder.encode(commandId, "UTF-8")
        val url = "$REMOTE_COMMANDS_TABLE?id=eq.$encoded&machine_id=eq.$MACHINE_ID&select=status,result,error&limit=1"
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 5_000
            readTimeout = 6_000
            setRequestProperty("apikey", REMOTE_ANON_KEY)
            setRequestProperty("Authorization", "Bearer $REMOTE_ANON_KEY")
            setRequestProperty("x-machine-token", token)
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "Drowned-Control-Android/1.3")
        }
        return try {
            val code = connection.responseCode
            if (code !in 200..299) return null
            val text = BufferedReader(InputStreamReader(connection.inputStream)).use { it.readText() }
            val array = JSONArray(text)
            if (array.length() == 0) null else array.optJSONObject(0)
        } finally {
            connection.disconnect()
        }
    }

    private fun parseState(item: JSONObject): RemotePcState {
        val artwork = item.optJSONObject("artwork") ?: JSONObject()
        val steamValue = if (item.isNull("steam_app_id")) "" else item.opt("steam_app_id")?.toString().orEmpty()
        return RemotePcState(
            title = item.optString("title"),
            steamAppId = steamValue,
            steamStatus = item.optString("steam_status"),
            description = item.optString("description"),
            platform = item.optString("platform"),
            channel = item.optString("channel"),
            version = item.optString("version", "1.0.0").ifBlank { "1.0.0" },
            source = item.optString("source"),
            uploadRunning = item.optBoolean("upload_running", false),
            steamBusy = item.optBoolean("steam_busy", false),
            artworkHero = artwork.optBoolean("hero", false),
            artworkCover = artwork.optBoolean("cover", false),
            artworkLogo = artwork.optBoolean("logo", false),
            screenshots = artwork.optInt("screenshots", 0),
            trailers = artwork.optInt("trailers", 0),
        )
    }
}
