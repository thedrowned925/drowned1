package com.drowned.control.release

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

private val FileCard = Color(0xFF101923)
private val FileCardAlt = Color(0xFF142130)
private val FileMuted = Color(0xFF8FA5B8)
private val FileAccent = Color(0xFF66C0F4)
private val FileGood = Color(0xFF34D399)
private val FileBad = Color(0xFFF87171)

@Composable
fun RemoteFileManagerPanel(pairingToken: String) {
    val scope = rememberCoroutineScope()
    var roots by remember { mutableStateOf<List<RemoteFolder>>(emptyList()) }
    var directory by remember { mutableStateOf<RemoteDirectory?>(null) }
    var open by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var info by remember { mutableStateOf<String?>(null) }

    var selectedName by remember { mutableStateOf("") }
    var selectedPath by remember { mutableStateOf("") }
    var selectedIsFolder by remember { mutableStateOf(false) }
    var renameName by remember { mutableStateOf("") }

    var clipboardMode by remember { mutableStateOf("") }
    var clipboardSource by remember { mutableStateOf("") }
    var clipboardName by remember { mutableStateOf("") }
    var newFolderName by remember { mutableStateOf("") }

    val live = RealtimeLiveStore.status.value?.takeIf { it.kind == "fileop" }
    val fileActive = live?.active == true

    LaunchedEffect(Unit) {
        RealtimeLiveStore.ensureStarted()
    }

    fun task(block: suspend () -> Unit) {
        if (busy) return
        scope.launch {
            busy = true
            error = null
            info = null
            try {
                block()
            } catch (throwable: Throwable) {
                error = throwable.message ?: "Dosya işlemi başarısız oldu."
            } finally {
                busy = false
            }
        }
    }

    fun select(name: String, path: String, isFolder: Boolean) {
        selectedName = name
        selectedPath = path
        selectedIsFolder = isFolder
        renameName = name
        info = "Seçildi: $name"
        error = null
    }

    Card(colors = CardDefaults.cardColors(containerColor = FileCard)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("PC Dosya Yöneticisi", fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
            Text(
                "Kopyala, kes/taşı, yeniden adlandır ve yeni klasör oluştur. Dosya verisi Supabase'e gönderilmez; işlem PC diskinde yapılır.",
                fontSize = 12.sp,
                color = FileMuted,
            )

            if (!open) {
                Button(
                    enabled = !busy && pairingToken.length >= 24,
                    onClick = {
                        task {
                            roots = RemoteReleaseApi.listRoots(pairingToken)
                            directory = null
                            open = true
                        }
                    },
                ) { Text("DOSYA YÖNETİCİSİNİ AÇ") }
            } else {
                val current = directory
                if (current == null) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("Diskler", fontWeight = FontWeight.Bold)
                        TextButton(onClick = {
                            task { roots = RemoteReleaseApi.listRoots(pairingToken) }
                        }) { Text("Yenile") }
                    }
                    roots.forEach { root ->
                        FileManagerRow("💽", root.name, "${root.path} · boş ${fileHumanBytes(root.diskFree)}") {
                            task { directory = RemoteReleaseApi.listDirectory(pairingToken, root.path) }
                        }
                    }
                } else {
                    Text(current.path, fontSize = 12.sp, fontWeight = FontWeight.Bold, color = FileAccent)
                    Text("Boş alan: ${fileHumanBytes(current.diskFree)}", fontSize = 11.sp, color = FileMuted)

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (current.parent.isNotBlank()) {
                            TextButton(onClick = {
                                task { directory = RemoteReleaseApi.listDirectory(pairingToken, current.parent) }
                            }) { Text("↑ Üst") }
                        }
                        TextButton(onClick = {
                            task { directory = RemoteReleaseApi.listDirectory(pairingToken, current.path) }
                        }) { Text("Yenile") }
                    }

                    if (clipboardSource.isNotBlank()) {
                        Card(colors = CardDefaults.cardColors(containerColor = FileCardAlt)) {
                            Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(
                                    if (clipboardMode == "move") "✂ Kesildi: $clipboardName" else "📋 Kopyalanacak: $clipboardName",
                                    fontSize = 12.sp,
                                    color = FileAccent,
                                )
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Button(
                                        enabled = !busy && !fileActive,
                                        onClick = {
                                            task {
                                                if (clipboardMode == "move") {
                                                    RemoteReleaseApi.movePath(pairingToken, clipboardSource, current.path)
                                                } else {
                                                    RemoteReleaseApi.copyPath(pairingToken, clipboardSource, current.path)
                                                }
                                                info = if (clipboardMode == "move") "✓ Taşıma PC'de başladı." else "✓ Kopyalama PC'de başladı."
                                                clipboardMode = ""
                                                clipboardSource = ""
                                                clipboardName = ""
                                            }
                                        },
                                    ) { Text("BURAYA YAPIŞTIR") }
                                    TextButton(onClick = {
                                        clipboardMode = ""
                                        clipboardSource = ""
                                        clipboardName = ""
                                    }) { Text("Vazgeç") }
                                }
                            }
                        }
                    }

                    OutlinedTextField(
                        value = newFolderName,
                        onValueChange = { newFolderName = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Yeni klasör adı") },
                        singleLine = true,
                    )
                    Button(
                        enabled = !busy && !fileActive && newFolderName.isNotBlank(),
                        onClick = {
                            task {
                                RemoteReleaseApi.createFolder(pairingToken, current.path, newFolderName)
                                info = "✓ Klasör oluşturuldu: $newFolderName"
                                newFolderName = ""
                                directory = RemoteReleaseApi.listDirectory(pairingToken, current.path)
                            }
                        },
                    ) { Text("YENİ KLASÖR") }

                    if (current.folders.isNotEmpty()) {
                        Text("Klasörler", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                        current.folders.take(100).forEach { folder ->
                            Card(colors = CardDefaults.cardColors(containerColor = FileCardAlt)) {
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(10.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                ) {
                                    Column(
                                        modifier = Modifier.weight(1f).clickable {
                                            task { directory = RemoteReleaseApi.listDirectory(pairingToken, folder.path) }
                                        }
                                    ) {
                                        Text("📁 ${folder.name}", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                                        Text(folder.path, fontSize = 10.sp, color = FileMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    }
                                    TextButton(onClick = { select(folder.name, folder.path, true) }) { Text("Seç") }
                                }
                            }
                        }
                    }

                    val allFiles = buildList {
                        current.archives.forEach { add(RemoteFile(it.name, it.path, it.size, it.kind)) }
                        addAll(current.files)
                    }
                    if (allFiles.isNotEmpty()) {
                        Text("Dosyalar", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                        allFiles.take(120).forEach { file ->
                            FileManagerRow("📄", file.name, "${file.kind.uppercase()} · ${fileHumanBytes(file.size)}") {
                                select(file.name, file.path, false)
                            }
                        }
                    }
                }
            }

            if (selectedPath.isNotBlank()) {
                Card(colors = CardDefaults.cardColors(containerColor = FileCardAlt)) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            "${if (selectedIsFolder) "📁" else "📄"} $selectedName",
                            fontWeight = FontWeight.Bold,
                            color = FileGood,
                        )
                        Text(selectedPath, fontSize = 10.sp, color = FileMuted, maxLines = 2)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                enabled = !fileActive,
                                onClick = {
                                    clipboardMode = "copy"
                                    clipboardSource = selectedPath
                                    clipboardName = selectedName
                                    info = "Kopyalama için seçildi. Hedef klasöre gidip Buraya Yapıştır'a bas."
                                },
                            ) { Text("KOPYALA") }
                            Button(
                                enabled = !fileActive,
                                onClick = {
                                    clipboardMode = "move"
                                    clipboardSource = selectedPath
                                    clipboardName = selectedName
                                    info = "Kesildi. Hedef klasöre gidip Buraya Yapıştır'a bas."
                                },
                            ) { Text("KES / TAŞI") }
                        }
                        OutlinedTextField(
                            value = renameName,
                            onValueChange = { renameName = it },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Yeni ad") },
                            singleLine = true,
                        )
                        Button(
                            enabled = !busy && !fileActive && renameName.isNotBlank() && renameName != selectedName,
                            onClick = {
                                task {
                                    val newPath = RemoteReleaseApi.renamePath(pairingToken, selectedPath, renameName)
                                    info = "✓ Yeniden adlandırıldı: $renameName"
                                    selectedPath = newPath
                                    selectedName = renameName
                                    directory?.let { directory = RemoteReleaseApi.listDirectory(pairingToken, it.path) }
                                }
                            },
                        ) { Text("YENİDEN ADLANDIR") }
                    }
                }
            }

            if (live != null) {
                Text(
                    "${live.percent}% · ${live.phase}",
                    fontWeight = FontWeight.Bold,
                    color = if (live.active) FileAccent else FileGood,
                )
                LinearProgressIndicator(
                    progress = { live.percent.coerceIn(0, 100) / 100f },
                    modifier = Modifier.fillMaxWidth(),
                )
                if (live.totalSize > 0) {
                    Text(
                        "${fileHumanBytes(live.totalSent)} / ${fileHumanBytes(live.totalSize)}",
                        fontSize = 11.sp,
                        color = FileMuted,
                    )
                }
                if (live.message.isNotBlank()) {
                    Text(live.message, fontSize = 11.sp, color = FileMuted)
                }
                if (live.active) {
                    Button(
                        enabled = !busy,
                        onClick = {
                            task {
                                RemoteReleaseApi.cancelFileOperation(pairingToken)
                                info = "İptal sinyali PC'ye gönderildi."
                            }
                        },
                    ) { Text("DOSYA İŞLEMİNİ İPTAL ET") }
                }
            }

            if (busy) Text("PC işlemi bekleniyor…", color = FileMuted, fontSize = 12.sp)
            info?.let { Text(it, color = FileGood, fontSize = 12.sp) }
            error?.let { Text(it, color = FileBad, fontSize = 12.sp, fontWeight = FontWeight.SemiBold) }
        }
    }
}

@Composable
private fun FileManagerRow(icon: String, name: String, detail: String, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = FileCardAlt),
    ) {
        Column(Modifier.padding(10.dp)) {
            Text("$icon $name", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
            Text(detail, fontSize = 10.sp, color = FileMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

private fun fileHumanBytes(bytes: Long): String {
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
