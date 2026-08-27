package com.drowned.control

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Bundle
import android.util.Base64
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import java.util.UUID

class RemoteControlActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            DrownedTheme {
                RemoteControlScreen(onBack = { finish() })
            }
        }
    }
}

private class RemoteController(private val scope: CoroutineScope) {
    var relayUrl by mutableStateOf("")
    var deviceId by mutableStateOf("")
    var token by mutableStateOf("")
    var connected by mutableStateOf(false)
    var agentOnline by mutableStateOf(false)
    var hostname by mutableStateOf("—")
    var cpu by mutableStateOf(0.0)
    var memoryPercent by mutableStateOf(0.0)

    var fdmRunning by mutableStateOf(false)
    var downloadFolder by mutableStateOf<String?>(null)
    var downloadWatchActive by mutableStateOf(false)
    var downloadState by mutableStateOf("idle")
    var downloadFile by mutableStateOf<String?>(null)
    var downloadedBytes by mutableStateOf(0L)
    var downloadSpeed by mutableStateOf(0.0)
    var stableSeconds by mutableStateOf(0.0)

    var selectedExe by mutableStateOf<String?>(null)
    var testActive by mutableStateOf(false)
    var pid by mutableStateOf<Int?>(null)
    var preview by mutableStateOf<Bitmap?>(null)
    var frameNumber by mutableStateOf(0)
    val logs = mutableStateListOf<String>()

    private var polling = false
    private var pollJob: Job? = null

    fun connect() {
        if (polling) return
        val base = relayUrl.trim().trimEnd('/')
        val device = deviceId.trim().lowercase()
        val accessToken = token.trim()
        if (base.isBlank() || device.isBlank() || accessToken.isBlank()) {
            addLog("Relay URL, cihaz ID ve token gerekli.")
            return
        }
        relayUrl = base
        deviceId = device
        polling = true
        connected = true
        addLog("Relay bağlantısı başlatıldı.")
        pollJob = scope.launch(Dispatchers.IO) {
            while (polling) {
                try {
                    val message = getJson("/api/mobile/$device/next")
                    process(message)
                } catch (error: Exception) {
                    withContext(Dispatchers.Main) {
                        agentOnline = false
                        addLog("Bağlantı hatası: ${error.message ?: error.javaClass.simpleName}")
                    }
                    delay(2_000)
                }
            }
        }
        command("request_status")
    }

    fun disconnect() {
        polling = false
        pollJob?.cancel()
        pollJob = null
        connected = false
        agentOnline = false
        preview = null
        addLog("Relay bağlantısı kapatıldı.")
    }

    fun command(name: String) {
        if (!connected) {
            addLog("Önce relay'e bağlan.")
            return
        }
        val requestId = UUID.randomUUID().toString()
        scope.launch(Dispatchers.IO) {
            try {
                val body = JSONObject()
                    .put("type", "command")
                    .put("command", name)
                    .put("request_id", requestId)
                postJson("/api/mobile/${deviceId.trim().lowercase()}/command", body)
            } catch (error: Exception) {
                withContext(Dispatchers.Main) {
                    addLog("Komut gönderilemedi: ${error.message ?: error.javaClass.simpleName}")
                }
            }
        }
    }

    private suspend fun process(message: JSONObject) {
        when (message.optString("type")) {
            "screen_frame" -> {
                val bytes = Base64.decode(message.optString("data"), Base64.DEFAULT)
                val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                withContext(Dispatchers.Main) {
                    preview = bitmap
                    frameNumber = message.optInt("frame", frameNumber + 1)
                }
            }
            else -> withContext(Dispatchers.Main) { applyMessage(message) }
        }
    }

    private fun applyMessage(message: JSONObject) {
        when (message.optString("type")) {
            "relay_state" -> agentOnline = message.optBoolean("agent_online", false)
            "agent_hello" -> {
                hostname = message.optString("hostname", hostname)
                agentOnline = true
                addLog("Agent bağlandı: $hostname")
            }
            "agent_status" -> {
                hostname = message.optString("hostname", hostname)
                cpu = message.optDouble("cpu", 0.0)
                memoryPercent = message.optDouble("memory_percent", 0.0)
                selectedExe = message.optString("selected_exe").takeIf { it.isNotBlank() && it != "null" }
                testActive = message.optBoolean("test_active", false)
                pid = if (message.isNull("pid")) null else message.optInt("pid")
                fdmRunning = message.optBoolean("fdm_running", false)
                downloadFolder = message.optString("download_folder").takeIf { it.isNotBlank() && it != "null" }
                downloadWatchActive = message.optBoolean("download_watch_active", false)
                agentOnline = true
            }
            "download_folder_selected" -> {
                downloadFolder = message.optString("folder").takeIf { it.isNotBlank() }
                fdmRunning = message.optBoolean("fdm_running", fdmRunning)
                addLog("İndirme klasörü seçildi: ${downloadFolder ?: "—"}")
            }
            "download_folder_selection_cancelled" -> addLog("PC'deki indirme klasörü seçimi iptal edildi.")
            "download_watch_started" -> {
                downloadWatchActive = true
                applyDownloadProgress(message)
                addLog("İndirme izlemesi başladı.")
            }
            "download_progress" -> applyDownloadProgress(message)
            "download_watch_stopped" -> {
                downloadWatchActive = false
                applyDownloadProgress(message)
                addLog("İndirme izlemesi durduruldu.")
            }
            "exe_selected" -> {
                selectedExe = message.optString("path")
                addLog("EXE seçildi: ${selectedExe ?: "—"}")
            }
            "exe_selection_cancelled" -> addLog("PC'deki EXE seçimi iptal edildi.")
            "test_started" -> {
                testActive = true
                pid = message.optInt("pid")
                addLog("Test başladı. PID: ${pid ?: "—"}")
            }
            "test_process_exited" -> {
                testActive = false
                addLog("Test process'i kendiliğinden kapandı.")
            }
            "test_approved" -> {
                testActive = false
                pid = null
                preview = null
                addLog("Test onaylandı. Process kapatıldı; sonraki aşamaya hazır.")
            }
            "test_failed" -> {
                testActive = false
                pid = null
                preview = null
                addLog("Test başarısız olarak sonlandırıldı.")
            }
            "event" -> addLog(message.optString("message", "Agent olayı"))
            "error" -> addLog("Hata: ${message.optString("message", "Bilinmeyen hata")}")
        }
    }

    private fun applyDownloadProgress(message: JSONObject) {
        downloadState = message.optString("state", downloadState)
        downloadFolder = message.optString("folder").takeIf { it.isNotBlank() && it != "null" } ?: downloadFolder
        downloadFile = message.optString("file_name").takeIf { it.isNotBlank() && it != "null" }
        downloadedBytes = message.optLong("downloaded_bytes", downloadedBytes)
        downloadSpeed = message.optDouble("speed_bps", downloadSpeed)
        stableSeconds = message.optDouble("stable_seconds", stableSeconds)
        fdmRunning = message.optBoolean("fdm_running", fdmRunning)
    }

    private fun addLog(text: String) {
        logs.add(0, text)
        while (logs.size > 60) logs.removeLast()
    }

    private fun open(path: String): HttpURLConnection {
        val connection = URL(relayUrl + path).openConnection() as HttpURLConnection
        connection.connectTimeout = 12_000
        connection.readTimeout = 30_000
        connection.setRequestProperty("Authorization", "Bearer ${token.trim()}")
        connection.setRequestProperty("Accept", "application/json")
        return connection
    }

    private fun getJson(path: String): JSONObject {
        val connection = open(path)
        connection.requestMethod = "GET"
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()
        if (code !in 200..299) error("HTTP $code ${text.take(120)}")
        return JSONObject(text)
    }

    private fun postJson(path: String, body: JSONObject) {
        val connection = open(path)
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body.toString()) }
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()
        if (code !in 200..299) error("HTTP $code ${text.take(120)}")
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RemoteControlScreen(onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val controller = remember { RemoteController(scope) }

    DisposableEffect(Unit) {
        onDispose { controller.disconnect() }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("PC Control", fontWeight = FontWeight.Bold)
                        Text("Drowned Agent", fontSize = 11.sp)
                    }
                },
                navigationIcon = { TextButton(onClick = onBack) { Text("← Geri") } },
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item { Spacer(Modifier.height(4.dp)) }
            item {
                OutlinedTextField(
                    value = controller.relayUrl,
                    onValueChange = { controller.relayUrl = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Relay URL") },
                    placeholder = { Text("https://relay.example.com") },
                    singleLine = true,
                )
            }
            item {
                OutlinedTextField(
                    value = controller.deviceId,
                    onValueChange = { controller.deviceId = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("PC cihaz ID") },
                    placeholder = { Text("hasan-pc") },
                    singleLine = true,
                )
            }
            item {
                OutlinedTextField(
                    value = controller.token,
                    onValueChange = { controller.token = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Erişim anahtarı") },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                )
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { if (controller.connected) controller.disconnect() else controller.connect() }) {
                        Text(if (controller.connected) "Bağlantıyı Kes" else "Bağlan")
                    }
                    TextButton(onClick = { controller.command("request_status") }) { Text("Yenile") }
                }
            }
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(),
                    shape = RoundedCornerShape(14.dp),
                ) {
                    Column(Modifier.padding(14.dp)) {
                        Text(if (controller.agentOnline) "● PC Çevrimiçi" else "○ PC Çevrimdışı", fontWeight = FontWeight.Bold)
                        Spacer(Modifier.height(6.dp))
                        Text(controller.hostname)
                        Text("CPU: ${"%.1f".format(controller.cpu)}%   RAM: ${"%.1f".format(controller.memoryPercent)}%", fontSize = 13.sp)
                        Text("PID: ${controller.pid ?: "—"}", fontSize = 13.sp)
                    }
                }
            }

            item { Text("İndirme Takibi", fontSize = 20.sp, fontWeight = FontWeight.Bold) }
            item {
                Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp)) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text(if (controller.fdmRunning) "● FDM açık" else "○ FDM kapalı", fontWeight = FontWeight.Bold)
                        Text("Durum: ${downloadStateLabel(controller.downloadState)}", fontSize = 13.sp)
                        Text("Klasör: ${controller.downloadFolder ?: "Henüz seçilmedi"}", fontSize = 12.sp)
                        Text("Dosya: ${controller.downloadFile ?: "Bekleniyor"}", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                        Text("İndirilen: ${formatRemoteBytes(controller.downloadedBytes)}", fontSize = 13.sp)
                        Text("Hız: ${formatRemoteSpeed(controller.downloadSpeed)}", fontSize = 13.sp)
                        if (controller.stableSeconds > 0) {
                            Text("Son değişim: ${"%.0f".format(controller.stableSeconds)} sn önce", fontSize = 12.sp)
                        }
                    }
                }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = { controller.command("choose_download_folder") },
                        enabled = controller.agentOnline && !controller.downloadWatchActive,
                    ) { Text("PC'de Klasör Seç") }
                    Button(
                        onClick = {
                            controller.command(if (controller.downloadWatchActive) "stop_download_watch" else "start_download_watch")
                        },
                        enabled = controller.agentOnline && (controller.downloadFolder != null || controller.downloadWatchActive),
                    ) {
                        Text(if (controller.downloadWatchActive) "İzlemeyi Durdur" else "İzlemeyi Başlat")
                    }
                }
            }

            item { Text("Oyun Testi", fontSize = 20.sp, fontWeight = FontWeight.Bold) }
            item { Text("Seçilen EXE: ${controller.selectedExe ?: "Henüz seçilmedi"}", fontSize = 13.sp) }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { controller.command("choose_executable") }, enabled = controller.agentOnline && !controller.testActive) {
                        Text("PC'de EXE Seç")
                    }
                    Button(onClick = { controller.command("start_test") }, enabled = controller.agentOnline && !controller.testActive && controller.selectedExe != null) {
                        Text("Testi Başlat")
                    }
                }
            }
            if (controller.preview != null) {
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Image(
                            bitmap = controller.preview!!.asImageBitmap(),
                            contentDescription = "PC canlı önizleme",
                            modifier = Modifier.fillMaxWidth(),
                            contentScale = ContentScale.FillWidth,
                        )
                    }
                }
                item { Text("Canlı kare #${controller.frameNumber}", fontSize = 12.sp) }
            }
            if (controller.testActive) {
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { controller.command("approve_test") }, modifier = Modifier.weight(1f)) {
                            Text("✓ Çalışıyor")
                        }
                        Button(onClick = { controller.command("reject_test") }, modifier = Modifier.weight(1f)) {
                            Text("✕ Başarısız")
                        }
                    }
                }
            }
            item { Text("Teknik Günlük", fontSize = 20.sp, fontWeight = FontWeight.Bold) }
            items(controller.logs) { log -> Text(log, fontSize = 12.sp) }
            item { Spacer(Modifier.height(28.dp)) }
        }
    }
}

private fun downloadStateLabel(state: String): String = when (state) {
    "waiting" -> "Yeni/aktif dosya bekleniyor"
    "downloading" -> "İndiriliyor"
    "stable" -> "Dosya değişmiyor"
    "stopped" -> "İzleme durduruldu"
    "idle" -> "Boşta"
    else -> state.ifBlank { "—" }
}

private fun formatRemoteBytes(value: Long): String {
    var size = value.toDouble()
    val units = arrayOf("B", "KiB", "MiB", "GiB", "TiB")
    var index = 0
    while (size >= 1024.0 && index < units.lastIndex) {
        size /= 1024.0
        index++
    }
    return if (index == 0) "${size.toLong()} ${units[index]}" else String.format(Locale.US, "%.2f %s", size, units[index])
}

private fun formatRemoteSpeed(value: Double): String {
    if (value <= 0.0) return "—"
    return "${formatRemoteBytes(value.toLong())}/s"
}
