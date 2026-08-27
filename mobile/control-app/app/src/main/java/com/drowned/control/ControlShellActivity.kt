package com.drowned.control

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

class ControlShellActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            DrownedTheme {
                ControlShell(
                    onOpenPcControl = {
                        startActivity(Intent(this, RemoteControlActivity::class.java))
                    }
                )
            }
        }
    }
}

@Composable
private fun ControlShell(onOpenPcControl: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var updateInfo by remember { mutableStateOf<ControlUpdateInfo?>(null) }
    var updating by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        updateInfo = runCatching { UpdateManager.checkForUpdate() }.getOrNull()
    }

    Box(Modifier.fillMaxSize()) {
        DrownedControlApp()
        FloatingActionButton(
            onClick = onOpenPcControl,
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(18.dp),
        ) {
            Text("PC")
        }
    }

    val available = updateInfo
    if (available != null) {
        AlertDialog(
            onDismissRequest = { if (!updating) updateInfo = null },
            title = { Text("Drowned Control güncellemesi") },
            text = {
                Text(
                    if (updating) {
                        "Güncelleme GitHub'dan indiriliyor ve doğrulanıyor…"
                    } else {
                        "Yeni sürüm hazır: ${available.versionName}\n\n" +
                            "APK uygulama tarafından indirilecek. Android kurulum ekranında yalnızca Güncelle/Kur onayı vermen yeterli."
                    }
                )
            },
            confirmButton = {
                TextButton(
                    enabled = !updating,
                    onClick = {
                        scope.launch {
                            updating = true
                            try {
                                val apk = UpdateManager.download(context.applicationContext, available)
                                when (UpdateManager.requestInstall(context.applicationContext, apk)) {
                                    InstallRequestResult.INSTALLER_OPENED -> {
                                        updateInfo = null
                                    }
                                    InstallRequestResult.PERMISSION_REQUIRED -> {
                                        Toast.makeText(
                                            context,
                                            "Drowned Control için 'Bilinmeyen uygulama yükleme' iznini aç. Sonra uygulamaya dönüp Güncelle'ye tekrar bas.",
                                            Toast.LENGTH_LONG,
                                        ).show()
                                    }
                                }
                            } catch (error: Exception) {
                                Toast.makeText(
                                    context,
                                    "Güncelleme başarısız: ${error.message ?: error.javaClass.simpleName}",
                                    Toast.LENGTH_LONG,
                                ).show()
                            } finally {
                                updating = false
                            }
                        }
                    },
                ) {
                    Text(if (updating) "İndiriliyor…" else "Güncelle")
                }
            },
            dismissButton = {
                TextButton(
                    enabled = !updating,
                    onClick = { updateInfo = null },
                ) {
                    Text("Sonra")
                }
            },
        )
    }
}
