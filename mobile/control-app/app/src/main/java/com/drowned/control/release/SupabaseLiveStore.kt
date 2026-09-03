package com.drowned.control.release

import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import io.github.jan.supabase.annotations.SupabaseExperimental
import io.github.jan.supabase.createSupabaseClient
import io.github.jan.supabase.postgrest.Postgrest
import io.github.jan.supabase.postgrest.from
import io.github.jan.supabase.realtime.Realtime
import io.github.jan.supabase.realtime.selectSingleValueAsFlow
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import org.json.JSONArray
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import kotlin.math.roundToLong

private const val SUPABASE_URL = "https://hfigrspqyxhscbkmporz.supabase.co"

// supabase-kt 3.0.1 predates the modern sb_publishable_* key format. The legacy
// anon JWT is intentionally a public client key and keeps the old Realtime
// channel authentication compatible. RLS still controls what the app can read.
private const val SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhmaWdyc3BxeXhoc2Nia21wb3J6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgzOTY0NjIsImV4cCI6MjEwMzk3MjQ2Mn0.7esPHfTAIS19KKniUi6Klo1Fgoze2-y6jOOlhHlZaGg"
private const val ACTIVE_SNAPSHOT_MS = 750L
private const val IDLE_SNAPSHOT_MS = 2_500L
private const val REALTIME_RETRY_MS = 2_000L
private const val LIVE_ROW_URL =
    "$SUPABASE_URL/rest/v1/release_live_status?machine_id=eq.primary&limit=1"

@Serializable
private data class SupabaseLiveRow(
    @SerialName("machine_id") val machineId: String,
    val active: Boolean = false,
    val phase: String = "idle",
    val kind: String = "release",
    val title: String = "",
    val platform: String = "",
    val channel: String = "",
    val version: String = "",
    val percent: Int = 0,
    @SerialName("speed_bps") val speedBps: Long = 0,
    @SerialName("avg_speed_bps") val averageSpeedBps: Long = 0,
    @SerialName("eta_seconds") val etaSeconds: Int? = null,
    @SerialName("processed_bytes") val processedBytes: Long = 0,
    @SerialName("total_bytes") val totalBytes: Long = 0,
    val connections: Int = 0,
    @SerialName("current_item") val currentItem: String = "",
    val message: String = "",
    @SerialName("updated_at") val updatedAt: String = "",
)

object RealtimeLiveStore {
    private val ioScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mainScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val _status = mutableStateOf<LiveUploadStatus?>(null)
    val status: State<LiveUploadStatus?> = _status

    @Volatile private var started = false
    @Volatile private var latestPublishedMillis = 0L

    private val client by lazy {
        createSupabaseClient(SUPABASE_URL, SUPABASE_ANON_KEY) {
            install(Postgrest)
            install(Realtime)
        }
    }

    @Synchronized
    fun ensureStarted() {
        if (started) return
        started = true

        // Primary path: Supabase Realtime. It should normally deliver the row
        // immediately after the PC updates it.
        ioScope.launch {
            while (isActive) {
                try {
                    collectRealtime()
                } catch (_: Throwable) {
                    delay(REALTIME_RETRY_MS)
                }
            }
        }

        // Reliability path: do not wait several seconds to decide whether the
        // WebSocket is stale. While a PC task is active we also read the single
        // status row every 750 ms. This row is tiny and guarantees that a flaky
        // mobile WebSocket cannot leave the UI several percent behind.
        ioScope.launch {
            while (isActive) {
                try {
                    fetchRestSnapshot()?.let(::publish)
                } catch (_: Throwable) {
                    // Live telemetry must never crash the dashboard.
                }
                delay(if (_status.value?.active == true) ACTIVE_SNAPSHOT_MS else IDLE_SNAPSHOT_MS)
            }
        }
    }

    @OptIn(SupabaseExperimental::class)
    private suspend fun collectRealtime() {
        client
            .from("release_live_status")
            .selectSingleValueAsFlow(SupabaseLiveRow::machineId) {
                eq("machine_id", "primary")
            }
            .collect(::publish)
    }

    @Synchronized
    private fun publish(row: SupabaseLiveRow) {
        val rowMillis = parseIsoInstantMillis(row.updatedAt) ?: 0L
        if (rowMillis > 0L && rowMillis < latestPublishedMillis) return
        if (rowMillis > 0L) latestPublishedMillis = rowMillis
        val uiValue = row.toUiStatus()
        mainScope.launch {
            _status.value = uiValue
        }
    }

    private fun fetchRestSnapshot(): SupabaseLiveRow? {
        val connection = (URL(LIVE_ROW_URL).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            useCaches = false
            connectTimeout = 4_000
            readTimeout = 4_000
            setRequestProperty("apikey", SUPABASE_ANON_KEY)
            setRequestProperty("Authorization", "Bearer $SUPABASE_ANON_KEY")
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Cache-Control", "no-cache, no-store, max-age=0")
            setRequestProperty("Pragma", "no-cache")
            setRequestProperty("User-Agent", "Drowned-Control-Android/1.4.1")
        }
        return try {
            connection.connect()
            if (connection.responseCode !in 200..299) return null
            val text = BufferedReader(InputStreamReader(connection.inputStream)).use { it.readText() }
            val array = JSONArray(text)
            if (array.length() == 0) return null
            val item = array.optJSONObject(0) ?: return null
            SupabaseLiveRow(
                machineId = item.optString("machine_id", "primary"),
                active = item.optBoolean("active", false),
                phase = item.optString("phase", "idle"),
                kind = item.optString("kind", "release"),
                title = item.optString("title", ""),
                platform = item.optString("platform", ""),
                channel = item.optString("channel", ""),
                version = item.optString("version", ""),
                percent = item.optInt("percent", 0),
                speedBps = item.optLong("speed_bps", 0L),
                averageSpeedBps = item.optLong("avg_speed_bps", 0L),
                etaSeconds = if (item.isNull("eta_seconds")) null else item.optInt("eta_seconds"),
                processedBytes = item.optLong("processed_bytes", 0L),
                totalBytes = item.optLong("total_bytes", 0L),
                connections = item.optInt("connections", 0),
                currentItem = item.optString("current_item", ""),
                message = item.optString("message", ""),
                updatedAt = item.optString("updated_at", ""),
            )
        } finally {
            connection.disconnect()
        }
    }
}

private fun SupabaseLiveRow.toUiStatus(): LiveUploadStatus {
    val extras = buildList {
        if (speedBps > 0) add("${formatRate(speedBps)}/sn")
        if (averageSpeedBps > 0) add("ort ${formatRate(averageSpeedBps)}/sn")
        etaSeconds?.takeIf { it >= 0 }?.let { add("ETA ${formatDuration(it)}") }
        if (connections > 0) add("$connections bağlantı")
    }
    val phaseText = buildString {
        append(phaseLabel(phase))
        if (extras.isNotEmpty()) append(" · ").append(extras.joinToString(" · "))
        if (currentItem.isNotBlank()) append(" · ").append(currentItem.takeLast(80))
    }
    return LiveUploadStatus(
        active = active,
        phase = phaseText,
        kind = kind,
        title = title.ifBlank { "Drowned Release Manager" },
        platform = platform,
        channel = channel,
        version = version,
        percent = percent.coerceIn(0, 100),
        totalSent = processedBytes,
        totalSize = totalBytes,
        message = message,
        updatedAt = updatedAt,
    )
}

private fun phaseLabel(value: String): String = when (value) {
    "download" -> "İndiriliyor"
    "verify" -> "İndirme kontrol ediliyor"
    "extract" -> "Arşiv çıkartılıyor"
    "ready_test", "test" -> "Oyun test ediliyor"
    "ready" -> "Yayına hazır"
    "cleanup" -> "Yerel temizlik"
    "plan" -> "Yayın hazırlanıyor"
    "upload" -> "GitHub'a yükleniyor"
    "metadata" -> "Meta veri yazılıyor"
    "remote_verify" -> "GitHub yayını doğrulanıyor"
    "complete", "done" -> "Tamamlandı"
    "error" -> "Hata"
    "idle" -> "Bekliyor"
    else -> value.ifBlank { "Çalışıyor" }
}

private fun formatRate(bytes: Long): String {
    if (bytes <= 0) return "0 B"
    val units = arrayOf("B", "KiB", "MiB", "GiB")
    var value = bytes.toDouble()
    var index = 0
    while (value >= 1024.0 && index < units.lastIndex) {
        value /= 1024.0
        index++
    }
    val rounded = if (value >= 100) value.roundToLong().toString() else String.format(java.util.Locale.US, "%.1f", value)
    return "$rounded ${units[index]}"
}

private fun formatDuration(seconds: Int): String {
    val safe = seconds.coerceAtLeast(0)
    val hours = safe / 3600
    val minutes = (safe % 3600) / 60
    val secs = safe % 60
    return if (hours > 0) "%02d:%02d:%02d".format(hours, minutes, secs) else "%02d:%02d".format(minutes, secs)
}
