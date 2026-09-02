package com.drowned.control.release

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val ColorSuccess = Color(0xFF34D399)
private val ColorFailure = Color(0xFFF87171)
private val ColorRunning = Color(0xFFFBBF24)
private val ColorNeutral = Color(0xFF8FA5B8)
private val ColorSurface = Color(0xFF101923)
private val ColorSurfaceAlt = Color(0xFF142130)
private val ColorAccent = Color(0xFF66C0F4)

@Composable
fun ReleaseManagerScreen(
    dashboard: ReleaseDashboard?,
    isLoading: Boolean,
    error: String?,
    onRefresh: () -> Unit,
) {
    var filter by remember { mutableStateOf("Tümü") }
    val filters = listOf("Tümü", "Pipeline", "Yayınlar", "Bileşenler")

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text("Release Manager", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, color = ColorAccent)
                    Text("Dağıtım durumu takibi", fontSize = 12.sp, color = ColorNeutral)
                }
                TextButton(onClick = onRefresh) { Text("Yenile") }
            }
        }

        if (dashboard != null) {
            if (dashboard.fromCache) {
                item {
                    Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF493C18))) {
                        Text(
                            "Çevrimdışı önbellek gösteriliyor.",
                            modifier = Modifier.padding(12.dp),
                            fontSize = 12.sp,
                        )
                    }
                }
            }
            item { OverviewSummary(dashboard) }
            item {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(filters) { item ->
                        FilterChip(
                            selected = filter == item,
                            onClick = { filter = item },
                            label = { Text(item) },
                        )
                    }
                }
            }
            when (filter) {
                "Tümü" -> {
                    item { SectionHeader("Çalışan build'ler") }
                    val running = dashboard.runningRuns
                    if (running.isEmpty()) {
                        item { EmptyHint("Şu anda çalışan build yok.") }
                    } else {
                        items(running.take(5)) { run -> WorkflowRunCard(run) }
                    }
                    item { SectionHeader("Son pipeline run'ları") }
                    items(dashboard.workflowRuns.take(10)) { run -> WorkflowRunCard(run) }
                    item { SectionHeader("Son yayınlar") }
                    items(dashboard.recentReleases.take(8)) { rel -> ReleaseCard(rel) }
                    item { SectionHeader("Bileşen build durumları") }
                    items(dashboard.buildStatuses) { bs -> BuildStatusCard(bs) }
                }
                "Pipeline" -> {
                    item { SectionHeader("Workflow run'ları (${dashboard.workflowRuns.size})") }
                    items(dashboard.workflowRuns) { run -> WorkflowRunCard(run) }
                }
                "Yayınlar" -> {
                    item { SectionHeader("GitHub Releases (${dashboard.releases.size})") }
                    items(dashboard.releases) { rel -> ReleaseCard(rel) }
                }
                "Bileşenler" -> {
                    item { SectionHeader("Bileşen build durumları") }
                    items(dashboard.buildStatuses) { bs -> BuildStatusCard(bs) }
                }
            }
        } else if (isLoading) {
            item {
                Box(Modifier.fillMaxWidth().padding(48.dp), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator(color = ColorAccent)
                        Spacer(Modifier.height(12.dp))
                        Text("GitHub Actions durumu yükleniyor…", color = ColorNeutral)
                    }
                }
            }
        } else if (error != null) {
            item {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF3B1212))) {
                    Column(Modifier.padding(16.dp)) {
                        Text("Durum alınamadı", fontWeight = FontWeight.Bold, color = ColorFailure)
                        Spacer(Modifier.height(6.dp))
                        Text(error, color = Color(0xFFE5B8B8), fontSize = 13.sp)
                        Spacer(Modifier.height(12.dp))
                        Button(onClick = onRefresh) { Text("Tekrar dene") }
                    }
                }
            }
        }
        item { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun OverviewSummary(dashboard: ReleaseDashboard) {
    val running = dashboard.runningRuns.size
    val failed = dashboard.failedRuns.size
    val releases = dashboard.releases.size
    val totalDownloads = dashboard.releases.sumOf { it.totalDownloads }
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SummaryStat("ÇALIŞAN", running.toString(), ColorRunning, Modifier.weight(1f))
        SummaryStat("BAŞARISIZ", failed.toString(), ColorFailure, Modifier.weight(1f))
        SummaryStat("YAYIN", releases.toString(), ColorAccent, Modifier.weight(1f))
    }
    Spacer(Modifier.height(8.dp))
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SummaryStat("İNDİRME", formatCount(totalDownloads), ColorSuccess, Modifier.weight(1f))
        val lastRun = dashboard.latestRun
        SummaryStat(
            "SON RUN",
            lastRun?.conclusion ?: lastRun?.status ?: "—",
            conclusionColor(lastRun?.conclusion),
            Modifier.weight(1f),
        )
    }
}

@Composable
private fun SummaryStat(label: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = ColorSurfaceAlt),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            Text(label, fontSize = 10.sp, color = ColorNeutral, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(5.dp))
            Text(
                value,
                fontSize = 16.sp,
                fontWeight = FontWeight.ExtraBold,
                color = color,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun WorkflowRunCard(run: WorkflowRun) {
    val context = LocalContext.current
    Card(
        modifier = Modifier.fillMaxWidth().clickable { openUrl(context, run.htmlUrl) },
        colors = CardDefaults.cardColors(containerColor = ColorSurface),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                StatusDot(run.conclusion, run.status)
                Spacer(Modifier.width(8.dp))
                Text(
                    run.name,
                    fontWeight = FontWeight.Bold,
                    color = ColorAccent,
                    fontSize = 13.sp,
                    modifier = Modifier.weight(1f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text("#${run.runNumber}", color = ColorNeutral, fontSize = 12.sp)
            }
            Spacer(Modifier.height(6.dp))
            Text(
                run.displayTitle,
                fontSize = 14.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                color = Color(0xFFEAF2F8),
            )
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MetaTag("event", run.event, ColorNeutral)
                MetaTag("branch", run.branch, ColorNeutral)
                if (run.actor.isNotBlank()) MetaTag("by", run.actor, ColorNeutral)
            }
            if (run.isLive) {
                Spacer(Modifier.height(10.dp))
                UploadProgress(run)
            }
            Spacer(Modifier.height(6.dp))
            Text(
                formatLabel(run.conclusion ?: run.status) + " · " + formatDate(run.updatedAt),
                fontSize = 11.sp,
                color = ColorNeutral,
            )
        }
    }
}

@Composable
private fun UploadProgress(run: WorkflowRun) {
    val percent = run.progressPercent
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                "Canlı: " + (run.currentStageName?.takeIf { it.isNotBlank() } ?: "Başlatılıyor…"),
                fontSize = 12.sp,
                color = ColorRunning,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (percent != null) {
                Text("%$percent", fontSize = 12.sp, color = ColorRunning, fontWeight = FontWeight.Bold)
            }
        }
        Spacer(Modifier.height(4.dp))
        if (percent != null) {
            LinearProgressIndicator(
                progress = { percent / 100f },
                modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
                color = ColorRunning,
                trackColor = ColorSurfaceAlt,
            )
        } else {
            LinearProgressIndicator(
                modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
                color = ColorRunning,
                trackColor = ColorSurfaceAlt,
            )
        }
    }
}

@Composable
private fun ReleaseCard(rel: ReleaseInfo) {
    val context = LocalContext.current
    Card(
        modifier = Modifier.fillMaxWidth().clickable { openUrl(context, rel.htmlUrl) },
        colors = CardDefaults.cardColors(containerColor = ColorSurface),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    rel.tagName,
                    fontWeight = FontWeight.Bold,
                    color = ColorAccent,
                    fontSize = 14.sp,
                    modifier = Modifier.weight(1f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                if (rel.isDraft) StatusBadge("DRAFT", ColorNeutral)
                else if (rel.isPrerelease) StatusBadge("PRE", ColorRunning)
            }
            if (rel.name.isNotBlank() && rel.name != rel.tagName) {
                Spacer(Modifier.height(4.dp))
                Text(rel.name, fontSize = 13.sp, color = Color(0xFFEAF2F8), maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MetaTag("assets", rel.assets.size.toString(), ColorNeutral)
                MetaTag("boyut", formatBytes(rel.totalSize), ColorNeutral)
                MetaTag("indirme", formatCount(rel.totalDownloads), ColorNeutral)
            }
            Spacer(Modifier.height(6.dp))
            Text(
                "Yayın: " + formatDate(rel.publishedAt),
                fontSize = 11.sp,
                color = ColorNeutral,
            )
            if (rel.assets.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                rel.assets.take(4).forEach { asset ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text(
                            asset.name,
                            fontSize = 12.sp,
                            color = Color(0xFFC3D0DB),
                            modifier = Modifier.weight(1f),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(formatBytes(asset.size), fontSize = 11.sp, color = ColorNeutral)
                    }
                }
                if (rel.assets.size > 4) {
                    Text("... +${rel.assets.size - 4} dosya", fontSize = 11.sp, color = ColorNeutral)
                }
            }
        }
    }
}

@Composable
private fun BuildStatusCard(bs: BuildStatus) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = ColorSurface),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(bs.componentName, fontWeight = FontWeight.Bold, color = ColorAccent, fontSize = 14.sp)
                StatusBadge(bs.status.uppercase(), statusColor(bs.status))
            }
            Spacer(Modifier.height(8.dp))
            if (bs.runId.isNotBlank()) {
                Text("Run: ${bs.runId}", fontSize = 11.sp, color = ColorNeutral)
            }
            if (bs.sha.isNotBlank()) {
                Text("SHA: ${bs.sha.take(7)}", fontSize = 11.sp, color = ColorNeutral)
            }
            if (bs.time.isNotBlank()) {
                Text("Zaman: " + formatDate(bs.time), fontSize = 11.sp, color = ColorNeutral)
            }
        }
    }
}

@Composable
private fun StatusDot(conclusion: String?, status: String) {
    val color = conclusionColor(conclusion)
    Box(
        modifier = Modifier
            .size(10.dp)
            .clip(CircleShape)
            .background(color),
    )
}

@Composable
private fun StatusBadge(text: String, color: Color) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(6.dp))
            .background(color.copy(alpha = 0.18f))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    ) {
        Text(text, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = color)
    }
}

@Composable
private fun MetaTag(label: String, value: String, color: Color) {
    Text(
        "$label: $value",
        fontSize = 11.sp,
        color = color,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
}

@Composable
private fun SectionHeader(text: String) {
    Text(text, fontSize = 17.sp, fontWeight = FontWeight.Bold, color = Color(0xFFEAF2F8))
}

@Composable
private fun EmptyHint(text: String) {
    Text(text, fontSize = 13.sp, color = ColorNeutral, modifier = Modifier.padding(vertical = 8.dp))
}

private fun conclusionColor(conclusion: String?): Color = when (conclusion) {
    "success" -> ColorSuccess
    "failure", "cancelled" -> ColorFailure
    "in_progress", "queued", "waiting", "pending", null -> ColorRunning
    else -> ColorNeutral
}

private fun statusColor(status: String): Color = when (status.lowercase()) {
    "success" -> ColorSuccess
    "failure", "cancelled", "error" -> ColorFailure
    "in_progress", "queued", "waiting", "pending" -> ColorRunning
    else -> ColorNeutral
}

private fun formatLabel(status: String): String = when (status.lowercase()) {
    "success" -> "Başarılı"
    "failure" -> "Başarısız"
    "cancelled" -> "İptal edildi"
    "in_progress" -> "Çalışıyor"
    "queued" -> "Sırada"
    "waiting" -> "Bekliyor"
    "pending" -> "Bekliyor"
    else -> status
}

private fun formatDate(raw: String): String {
    if (raw.isBlank()) return "—"
    return raw.replace("T", " ").substringBefore("+").substringBefore("Z").take(19)
}

private fun formatBytes(value: Long): String {
    var size = value.toDouble()
    val units = arrayOf("B", "KiB", "MiB", "GiB", "TiB")
    var index = 0
    while (size >= 1024.0 && index < units.lastIndex) {
        size /= 1024.0
        index++
    }
    return if (index == 0) "${size.toLong()} ${units[index]}"
    else String.format(java.util.Locale.US, "%.2f %s", size, units[index])
}

private fun formatCount(value: Long): String {
    if (value < 1000) return value.toString()
    if (value < 1_000_000) return String.format(java.util.Locale.US, "%.1fk", value / 1000.0)
    return String.format(java.util.Locale.US, "%.1fM", value / 1_000_000.0)
}

private fun openUrl(context: android.content.Context, url: String) {
    if (url.isBlank()) return
    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    context.startActivity(intent)
}
