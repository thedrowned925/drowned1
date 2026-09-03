package com.drowned.control.release

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

private val RemoteCard = androidx.compose.ui.graphics.Color(0xFF101923)
private val RemoteCardAlt = androidx.compose.ui.graphics.Color(0xFF142130)
private val RemoteMuted = androidx.compose.ui.graphics.Color(0xFF8FA5B8)
private val RemoteAccent = androidx.compose.ui.graphics.Color(0xFF66C0F4)
private val RemoteGood = androidx.compose.ui.graphics.Color(0xFF34D399)
private val RemoteBad = androidx.compose.ui.graphics.Color(0xFFF87171)

@Composable
fun RemoteReleaseScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var pairingToken by rememberSaveable { mutableStateOf(RemotePairingStore.load(context)) }
    var state by remember { mutableStateOf<RemotePcState?>(null) }
    var busy by remember { mutableStateOf(false) }
    var busyText by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var info by remember { mutableStateOf<String?>(null) }

    var steamId by rememberSaveable { mutableStateOf("") }
    var title by rememberSaveable { mutableStateOf("") }
    var version by rememberSaveable { mutableStateOf("1.0.0") }
    var platform by rememberSaveable { mutableStateOf("PC") }
    var channel by rememberSaveable { mutableStateOf("stable") }
    var description by rememberSaveable { mutableStateOf("") }
    var source by rememberSaveable { mutableStateOf("") }

    var browserOpen by remember { mutableStateOf(false) }
    var roots by remember { mutableStateOf<List<RemoteFolder>>(emptyList()) }
    var directory by remember { mutableStateOf<RemoteDirectory?>(null) }
    var selectedArchive by rememberSaveable { mutableStateOf("") }
    var selectedArchiveName by rememberSaveable { mutableStateOf("") }
    var extractTarget by rememberSaveable { mutableStateOf("") }

    LaunchedEffect(Unit) { RealtimeLiveStore.ensureStarted() }
    val liveStatus = RealtimeLiveStore.status.value
    val extractionLive = liveStatus?.takeIf { it.kind == "extract" }
    val extractionActive = extractionLive?.active == true
    val fileOperationActive = liveStatus?.let { it.kind == "fileop" && it.active } == true

    fun applyState(value: RemotePcState) {
        state = value
        if (value.steamAppId.isNotBlank()) steamId = value.steamAppId
        if (value.title.isNotBlank()) title = value.title
        if (value.version.isNotBlank()) version = value.version
        if (value.platform.isNotBlank()) platform = value.platform
        if (value.channel.isNotBlank()) channel = value.channel
        description = value.description
        if (value.source.isNotBlank()) source = value.source
        if (value.extractArchive.isNotBlank()) {
            selectedArchive = value.extractArchive
            selectedArchiveName = value.extractArchive.substringAfterLast('\\').substringAfterLast('/')
        }
        if (value.extractTarget.isNotBlank()) extractTarget = value.extractTarget
    }

    fun runTask(label: String, block: suspend () -> Unit) {
        if (busy) return
        scope.launch {
            busy = true
            busyText = label
            error = null
            info = null
            try {
                block()
            } catch (throwable: Throwable) {
                error = throwable.message ?: "İşlem başarısız oldu."
            } finally {
                busy = false
                busyText = ""
            }
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column {
                    Text("PC'den Yayınla", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, color = RemoteAccent)
                    Text("Windows Release Manager uzaktan kumandası", fontSize = 12.sp, color = RemoteMuted)
                }
                TextButton(onClick = onBack) { Text("Canlı takibe dön") }
            }
        }

        item {
            RemoteSection("1. PC'yi eşleştir") {
                Text("Windows Release Manager'daki ANDROID UZAKTAN KONTROL kodunu bir kez gir.", fontSize = 12.sp, color = RemoteMuted)
                OutlinedTextField(
                    value = pairingToken,
                    onValueChange = { pairingToken = it.trim() },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Eşleştirme kodu") },
                    singleLine = true,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        enabled = !busy && pairingToken.length >= 24,
                        onClick = {
                            runTask("PC bağlantısı doğrulanıyor…") {
                                val pc = RemoteReleaseApi.ping(pairingToken)
                                RemotePairingStore.save(context, pairingToken)
                                applyState(pc)
                                info = "✓ PC eşleştirildi."
                            }
                        },
                    ) { Text(if (state == null) "Bağlan" else "Bağlantıyı test et") }
                    if (pairingToken.isNotBlank()) {
                        TextButton(onClick = {
                            RemotePairingStore.clear(context)
                            pairingToken = ""
                            state = null
                            source = ""
                        }) { Text("Eşleştirmeyi sil") }
                    }
                }
            }
        }

        if (state != null) {
            item {
                RemoteSection("2. Steam bilgilerini PC'de hazırla") {
                    OutlinedTextField(
                        value = steamId,
                        onValueChange = { steamId = it.filter(Char::isDigit) },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Steam App ID") },
                        placeholder = { Text("Örn. 960910") },
                        singleLine = true,
                    )
                    Button(
                        enabled = !busy && steamId.isNotBlank() && !extractionActive && !fileOperationActive,
                        onClick = {
                            runTask("Steam bilgileri PC'de çekiliyor…") {
                                val pc = RemoteReleaseApi.fetchSteam(pairingToken, steamId)
                                applyState(pc)
                                info = "✓ Steam metadata ve artwork PC'de hazırlandı."
                            }
                        },
                    ) { Text("Steam bilgilerini PC'de getir") }
                    state?.steamStatus?.takeIf(String::isNotBlank)?.let {
                        Text(it, fontSize = 12.sp, color = RemoteMuted)
                    }
                    state?.let { artwork ->
                        Text(
                            "Artwork: Hero ${mark(artwork.artworkHero)} · Cover ${mark(artwork.artworkCover)} · Logo ${mark(artwork.artworkLogo)} · ${artwork.screenshots} screenshot · ${artwork.trailers} fragman",
                            fontSize = 11.sp,
                            color = RemoteMuted,
                        )
                    }
                }
            }

            item {
                RemoteSection("3. Yayın bilgileri") {
                    OutlinedTextField(title, { title = it }, Modifier.fillMaxWidth(), label = { Text("Oyun adı") }, singleLine = true)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(version, { version = it }, Modifier.weight(1f), label = { Text("Sürüm") }, singleLine = true)
                        OutlinedTextField(platform, { platform = it }, Modifier.weight(1f), label = { Text("Platform") }, singleLine = true)
                    }
                    OutlinedTextField(channel, { channel = it }, Modifier.fillMaxWidth(), label = { Text("Kanal") }, singleLine = true)
                    OutlinedTextField(description, { description = it }, Modifier.fillMaxWidth(), label = { Text("Açıklama") }, minLines = 3)
                    Button(
                        enabled = !busy && title.isNotBlank(),
                        onClick = {
                            runTask("Yayın bilgileri PC'ye aktarılıyor…") {
                                val pc = RemoteReleaseApi.setPublishFields(pairingToken, title, version, platform, channel, description)
                                applyState(pc)
                                info = "✓ Yayın alanları PC'ye uygulandı."
                            }
                        },
                    ) { Text("Bilgileri PC'ye uygula") }
                }
            }

            item {
                RemoteSection("4. Arşiv / upload klasörü seç") {
                    Text("ZIP / RAR / 7z seçebilir veya upload klasörü belirleyebilirsin. Dosya içeriği Supabase'e gönderilmez.", fontSize = 12.sp, color = RemoteMuted)
                    Text(source.ifBlank { "Upload klasörü henüz seçilmedi." }, fontSize = 12.sp, color = if (source.isBlank()) RemoteMuted else RemoteGood)
                    Button(
                        enabled = !busy && !fileOperationActive,
                        onClick = {
                            runTask("PC diskleri okunuyor…") {
                                roots = RemoteReleaseApi.listRoots(pairingToken)
                                directory = null
                                browserOpen = true
                            }
                        },
                    ) { Text(if (browserOpen) "Diskleri yenile" else "PC dosyalarını aç") }

                    if (browserOpen) {
                        val current = directory
                        if (current == null) {
                            roots.forEach { root ->
                                FolderRow(root.name, "${root.path} · boş ${humanBytes(root.diskFree)}") {
                                    runTask("${root.path} açılıyor…") { directory = RemoteReleaseApi.listDirectory(pairingToken, root.path) }
                                }
                            }
                        } else {
                            Text(current.path, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = RemoteAccent)
                            Text("Boş alan: ${humanBytes(current.diskFree)}", fontSize = 11.sp, color = RemoteMuted)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                if (current.parent.isNotBlank()) {
                                    TextButton(onClick = {
                                        runTask("Üst klasör açılıyor…") { directory = RemoteReleaseApi.listDirectory(pairingToken, current.parent) }
                                    }) { Text("↑ Üst") }
                                }
                                Button(onClick = {
                                    runTask("Upload klasörü seçiliyor…") {
                                        val pc = RemoteReleaseApi.selectSource(pairingToken, current.path)
                                        applyState(pc)
                                        source = current.path
                                        info = "✓ Upload klasörü seçildi."
                                    }
                                }) { Text("Upload klasörü yap") }
                            }
                            TextButton(onClick = {
                                extractTarget = current.path
                                info = "✓ Çıkarma hedefi: ${current.path}"
                            }) { Text("Bu klasörü çıkarma hedefi yap") }

                            if (current.archives.isNotEmpty()) {
                                Text("Arşivler", fontWeight = FontWeight.SemiBold, fontSize = 13.sp, color = RemoteAccent)
                                current.archives.take(80).forEach { archive ->
                                    ArchiveRow(archive, selectedArchive == archive.path) {
                                        if (!archive.firstPart) {
                                            error = "Çok parçalı RAR için ilk parçayı seç."
                                        } else {
                                            selectedArchive = archive.path
                                            selectedArchiveName = archive.name
                                            if (extractTarget.isBlank()) extractTarget = current.path
                                            info = "✓ Arşiv seçildi: ${archive.name}"
                                            error = null
                                        }
                                    }
                                }
                            }
                            if (current.folders.isNotEmpty()) {
                                Text("Klasörler", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                                current.folders.take(120).forEach { folder ->
                                    FolderRow(folder.name, folder.path) {
                                        runTask("${folder.name} açılıyor…") { directory = RemoteReleaseApi.listDirectory(pairingToken, folder.path) }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            item {
                Card(colors = CardDefaults.cardColors(containerColor = RemoteCardAlt), shape = RoundedCornerShape(16.dp)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                        Text("5. Arşivi PC'de çıkart", fontWeight = FontWeight.ExtraBold, fontSize = 17.sp)
                        Text(selectedArchiveName.ifBlank { "Tarayıcıdan ZIP / RAR / 7z seç." }, fontSize = 12.sp, color = if (selectedArchive.isBlank()) RemoteMuted else RemoteGood)
                        if (selectedArchive.isNotBlank()) {
                            Text(selectedArchive, fontSize = 10.sp, color = RemoteMuted, maxLines = 2)
                            Text("Hedef: ${extractTarget.ifBlank { "Arşivin bulunduğu klasör" }}", fontSize = 11.sp, color = RemoteMuted)
                        }
                        extractionLive?.let { live ->
                            Text("${live.percent}% · ${live.phase}", fontWeight = FontWeight.Bold, color = if (live.active) RemoteAccent else RemoteGood)
                            LinearProgressIndicator(progress = { live.percent.coerceIn(0, 100) / 100f }, modifier = Modifier.fillMaxWidth())
                            if (live.totalSize > 0) Text("${humanBytes(live.totalSent)} / ${humanBytes(live.totalSize)}", fontSize = 11.sp, color = RemoteMuted)
                            if (live.message.isNotBlank()) Text(live.message, fontSize = 11.sp, color = RemoteMuted)
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                enabled = !busy && selectedArchive.isNotBlank() && !extractionActive && !fileOperationActive && state?.uploadRunning != true,
                                onClick = {
                                    runTask("Arşiv çıkarma PC'de başlatılıyor…") {
                                        val pc = RemoteReleaseApi.startExtract(pairingToken, selectedArchive, extractTarget, title)
                                        applyState(pc)
                                        info = "✓ Arşiv çıkarma PC'de başladı."
                                    }
                                },
                            ) { Text(if (extractionActive) "Çıkartılıyor" else "ÇIKARTMAYI BAŞLAT") }
                            if (extractionActive) {
                                Button(enabled = !busy, onClick = {
                                    runTask("İptal sinyali gönderiliyor…") {
                                        applyState(RemoteReleaseApi.cancelExtract(pairingToken))
                                        info = "İptal sinyali PC'ye gönderildi."
                                    }
                                }) { Text("İPTAL") }
                            }
                        }
                        TextButton(enabled = !busy, onClick = {
                            runTask("PC durumu yenileniyor…") {
                                val pc = RemoteReleaseApi.getState(pairingToken)
                                applyState(pc)
                                info = if (pc.extractOutput.isNotBlank()) "✓ Çıkarma tamamlandı: ${pc.extractOutput}" else "PC durumu yenilendi."
                            }
                        }) { Text("Çıkarma durumunu PC'den yenile") }
                        state?.extractOutput?.takeIf(String::isNotBlank)?.let { output ->
                            Text("Çıktı: $output", fontSize = 11.sp, color = RemoteGood)
                            Button(enabled = !busy && !extractionActive && !fileOperationActive, onClick = {
                                runTask("Çıkarılan klasör upload kaynağı yapılıyor…") {
                                    val pc = RemoteReleaseApi.selectSource(pairingToken, output)
                                    applyState(pc)
                                    source = output
                                    info = "✓ Çıkarılan klasör upload kaynağı oldu."
                                }
                            }) { Text("Çıkarılan klasörü upload kaynağı yap") }
                        }
                        state?.extractError?.takeIf(String::isNotBlank)?.let { Text("Son çıkarma hatası: $it", fontSize = 11.sp, color = RemoteBad) }
                    }
                }
            }

            item { RemoteFileManagerPanel(pairingToken) }

            item {
                Card(colors = CardDefaults.cardColors(containerColor = RemoteCardAlt), shape = RoundedCornerShape(16.dp)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                        Text("6. Upload'u PC'de başlat", fontWeight = FontWeight.ExtraBold, fontSize = 17.sp)
                        Text("Telefon dosya taşımayacak; seçilen klasör PC → GitHub yüklenecek.", fontSize = 12.sp, color = RemoteMuted)
                        Button(
                            enabled = !busy && source.isNotBlank() && title.isNotBlank() && state?.uploadRunning != true && !extractionActive && !fileOperationActive,
                            onClick = {
                                runTask("Upload PC'de başlatılıyor…") {
                                    val request = (state ?: RemotePcState()).copy(title = title, version = version, platform = platform, channel = channel, description = description)
                                    applyState(RemoteReleaseApi.startUpload(pairingToken, request, source))
                                    info = "✓ Upload PC'de başladı."
                                }
                            },
                        ) { Text(if (state?.uploadRunning == true) "Upload çalışıyor" else "YÜKLEMEYİ BAŞLAT") }
                    }
                }
            }
        }

        if (busy) {
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    CircularProgressIndicator()
                    Text(busyText.ifBlank { "PC bekleniyor…" }, color = RemoteMuted)
                }
            }
        }
        info?.let { message -> item { Text(message, color = RemoteGood, fontWeight = FontWeight.SemiBold) } }
        error?.let { message ->
            item {
                Card(colors = CardDefaults.cardColors(containerColor = androidx.compose.ui.graphics.Color(0xFF3B1212))) {
                    Text(message, modifier = Modifier.padding(14.dp), color = RemoteBad)
                }
            }
        }
        item { Spacer(Modifier.height(28.dp)) }
    }
}

@Composable
private fun RemoteSection(title: String, content: @Composable () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = RemoteCard), shape = RoundedCornerShape(16.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            content()
        }
    }
}

@Composable
private fun FolderRow(name: String, detail: String, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = RemoteCardAlt),
        shape = RoundedCornerShape(10.dp),
    ) {
        Column(Modifier.padding(11.dp)) {
            Text("📁 $name", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
            Text(detail, fontSize = 10.sp, color = RemoteMuted, maxLines = 1)
        }
    }
}

@Composable
private fun ArchiveRow(archive: RemoteArchive, selected: Boolean, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = if (selected) RemoteCard else RemoteCardAlt),
        shape = RoundedCornerShape(10.dp),
    ) {
        Column(Modifier.padding(11.dp)) {
            Text("📦 ${archive.name}", fontWeight = FontWeight.SemiBold, fontSize = 13.sp, color = if (selected) RemoteAccent else androidx.compose.ui.graphics.Color.Unspecified)
            Text("${archive.kind.uppercase()} · ${humanBytes(archive.size)}" + if (archive.firstPart) "" else " · ilk parça değil", fontSize = 10.sp, color = if (archive.firstPart) RemoteMuted else RemoteBad)
        }
    }
}

private fun mark(value: Boolean): String = if (value) "✓" else "—"

private fun humanBytes(bytes: Long): String {
    if (bytes <= 0) return "—"
    val units = arrayOf("B", "KiB", "MiB", "GiB", "TiB")
    var value = bytes.toDouble()
    var index = 0
    while (value >= 1024.0 && index < units.lastIndex) {
        value /= 1024.0
        index++
    }
    return String.format(java.util.Locale.US, "%.1f %s", value, units[index])
}
