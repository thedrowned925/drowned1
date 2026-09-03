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
import kotlin.math.roundToLong

private const val SUPABASE_URL = "https://hfigrspqyxhscbkmporz.supabase.co"
private const val SUPABASE_PUBLISHABLE_KEY = "sb_publishable_6eylCS77qrEkMJNa6sW95g_u89HDoj4"

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
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val _status = mutableStateOf<LiveUploadStatus?>(null)
    val status: State<LiveUploadStatus?> = _status

    private var started = false

    private val client by lazy {
        createSupabaseClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY) {
            install(Postgrest)
            install(Realtime)
        }
    }

    @Synchronized
    fun ensureStarted() {
        if (started) return
        started = true
        scope.launch {
            while (isActive) {
                try {
                    collectRealtime()
                } catch (_: Throwable) {
                    delay(3_000)
                }
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
            .collect { row ->
                _status.value = row.toUiStatus()
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
