package com.drowned.control

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

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
}
