package com.drowned.control

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Icon
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Public
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale

private const val CATALOG_URL = "https://raw.githubusercontent.com/thedrowned925/drowned1/main/catalog.json"

data class ChannelInfo(
    val name: String,
    val version: String,
    val tag: String,
    val size: Long,
    val publishedAt: String,
)

data class Artwork(
    val hero: String?,
    val cover: String?,
    val logo: String?,
    val screenshots: List<String>,
)

data class GameInfo(
    val id: String,
    val title: String,
    val platform: String,
    val description: String,
    val artwork: Artwork,
    val channels: List<ChannelInfo>,
) {
    val totalSize: Long get() = channels.sumOf { it.size }
}

data class Catalog(
    val updatedAt: String,
    val games: List<GameInfo>,
    val fromCache: Boolean = false,
) {
    val totalSize: Long get() = games.sumOf { it.totalSize }
    val channelCount: Int get() = games.sumOf { it.channels.size }
}

object CatalogRepository {
    suspend fun load(context: Context): Catalog = withContext(Dispatchers.IO) {
        val prefs = context.getSharedPreferences("drowned_control", Context.MODE_PRIVATE)
        try {
            val connection = (URL(CATALOG_URL).openConnection() as HttpURLConnection).apply {
                connectTimeout = 12_000
                readTimeout = 20_000
                requestMethod = "GET"
                setRequestProperty("User-Agent", "Drowned-Control-Android/1.0")
                setRequestProperty("Cache-Control", "no-cache")
            }
            val text = connection.inputStream.bufferedReader().use { it.readText() }
            if (connection.responseCode !in 200..299) {
                error("GitHub catalog HTTP ${connection.responseCode}")
            }
            prefs.edit().putString("catalog_json", text).apply()
            parse(text, fromCache = false)
        } catch (error: Exception) {
            val cached = prefs.getString("catalog_json", null)
            if (cached.isNullOrBlank()) throw error
            parse(cached, fromCache = true)
        }
    }

    private fun parse(text: String, fromCache: Boolean): Catalog {
        val root = JSONObject(text)
        val gamesJson = root.optJSONArray("games")
        val games = buildList {
            if (gamesJson != null) {
                for (index in 0 until gamesJson.length()) {
                    val item = gamesJson.optJSONObject(index) ?: continue
                    val artworkJson = item.optJSONObject("artwork") ?: JSONObject()
                    val screenshots = buildList {
                        val array = artworkJson.optJSONArray("screenshots")
                        if (array != null) {
                            for (i in 0 until array.length()) {
                                array.optString(i).takeIf { it.isNotBlank() }?.let(::add)
                            }
                        }
                    }
                    val channelsJson = item.optJSONObject("channels") ?: JSONObject()
                    val channels = buildList {
                        val keys = channelsJson.keys()
                        while (keys.hasNext()) {
                            val key = keys.next()
                            val channel = channelsJson.optJSONObject(key) ?: continue
                            add(
                                ChannelInfo(
                                    name = key,
                                    version = channel.optString("version"),
                                    tag = channel.optString("tag"),
                                    size = channel.optLong("size", 0L),
                                    publishedAt = channel.optString("published_at"),
                                )
                            )
                        }
                    }.sortedBy { it.name }
                    add(
                        GameInfo(
                            id = item.optString("id"),
                            title = item.optString("title"),
                            platform = item.optString("platform", "other"),
                            description = item.optString("description"),
                            artwork = Artwork(
                                hero = artworkJson.optString("hero").takeIf { it.isNotBlank() },
                                cover = artworkJson.optString("cover").takeIf { it.isNotBlank() },
                                logo = artworkJson.optString("logo").takeIf { it.isNotBlank() },
                                screenshots = screenshots,
                            ),
                            channels = channels,
                        )
                    )
                }
            }
        }.sortedBy { it.title.lowercase(Locale.getDefault()) }
        return Catalog(
            updatedAt = root.optString("updated_at"),
            games = games,
            fromCache = fromCache,
        )
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            DrownedTheme {
                DrownedControlApp()
            }
        }
    }
}

private val DrownedColors = darkColorScheme(
    primary = Color(0xFF66C0F4),
    secondary = Color(0xFF1A9FFF),
    background = Color(0xFF0B1118),
    surface = Color(0xFF101923),
    surfaceVariant = Color(0xFF172536),
    onPrimary = Color(0xFF001E2D),
    onBackground = Color(0xFFEAF2F8),
    onSurface = Color(0xFFEAF2F8),
)

@Composable
fun DrownedTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = DrownedColors, content = content)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DrownedControlApp() {
    var tab by rememberSaveable { mutableStateOf(0) }
    Scaffold(
        bottomBar = {
            NavigationBar(containerColor = Color(0xFF101923)) {
                NavigationBarItem(
                    selected = tab == 0,
                    onClick = { tab = 0 },
                    icon = { Icon(Icons.Filled.Public, contentDescription = null) },
                    label = { Text("Katalog") },
                )
                NavigationBarItem(
                    selected = tab == 1,
                    onClick = { tab = 1 },
                    icon = { Icon(Icons.Filled.Build, contentDescription = null) },
                    label = { Text("Yayınlar") },
                )
            }
        }
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            when (tab) {
                0 -> CatalogTab()
                else -> ReleaseTab()
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CatalogTab() {
    val context = LocalContext.current
    var catalog by remember { mutableStateOf<Catalog?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshKey by remember { mutableStateOf(0) }
    var selectedGameId by rememberSaveable { mutableStateOf<String?>(null) }

    LaunchedEffect(refreshKey) {
        error = null
        try {
            catalog = CatalogRepository.load(context)
        } catch (throwable: Throwable) {
            error = throwable.message ?: "Katalog alınamadı."
        }
    }

    val selected = catalog?.games?.firstOrNull { it.id == selectedGameId }
    if (selected != null) {
        GameDetailScreen(game = selected, onBack = { selectedGameId = null })
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Drowned Control", fontWeight = FontWeight.Bold)
                        Text("Salt okunur dağıtım paneli", fontSize = 11.sp, color = Color(0xFF8FA5B8))
                    }
                },
                actions = {
                    TextButton(onClick = { refreshKey++ }) { Text("Yenile") }
                },
            )
        }
    ) { padding ->
        when {
            catalog != null -> Dashboard(
                catalog = catalog!!,
                modifier = Modifier.padding(padding),
                onGameClick = { selectedGameId = it.id },
            )
            error != null -> ErrorState(
                error = error!!,
                modifier = Modifier.padding(padding),
                onRetry = { refreshKey++ },
            )
            else -> LoadingState(Modifier.padding(padding))
        }
    }
}

// Live-tracks GitHub Actions runs: polls fast while a build/upload is in progress, slow when idle.
// Conditional GET (ETag) in ReleaseRepository makes the fast interval safe against GitHub's rate limit.
private const val RELEASE_POLL_ACTIVE_MS = 8_000L
private const val RELEASE_POLL_IDLE_MS = 45_000L

@Composable
private fun ReleaseTab() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var dashboard by remember { mutableStateOf<com.drowned.control.release.ReleaseDashboard?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    suspend fun refreshOnce() {
        try {
            dashboard = com.drowned.control.release.ReleaseRepository.load(context)
            error = null
        } catch (throwable: Throwable) {
            if (dashboard == null) error = throwable.message ?: "Dağıtım durumu alınamadı."
        }
    }

    LaunchedEffect(Unit) {
        while (true) {
            refreshOnce()
            val hasLiveRuns = dashboard?.runningRuns?.isNotEmpty() == true
            delay(if (hasLiveRuns) RELEASE_POLL_ACTIVE_MS else RELEASE_POLL_IDLE_MS)
        }
    }

    com.drowned.control.release.ReleaseManagerScreen(
        dashboard = dashboard,
        isLoading = dashboard == null && error == null,
        error = error,
        onRefresh = { scope.launch { refreshOnce() } },
    )
}

@Composable
private fun LoadingState(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text("GitHub kataloğu yükleniyor…")
    }
}

@Composable
private fun ErrorState(error: String, modifier: Modifier = Modifier, onRetry: () -> Unit) {
    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Katalog alınamadı", fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text(error, color = Color(0xFFB7C6D3))
        Spacer(Modifier.height(18.dp))
        Button(onClick = onRetry) { Text("Tekrar dene") }
    }
}

@Composable
private fun Dashboard(catalog: Catalog, modifier: Modifier = Modifier, onGameClick: (GameInfo) -> Unit) {
    var query by rememberSaveable { mutableStateOf("") }
    var platform by rememberSaveable { mutableStateOf("Tümü") }
    val platforms = remember(catalog.games) {
        listOf("Tümü") + catalog.games.map { it.platform.uppercase(Locale.getDefault()) }.distinct().sorted()
    }
    val filtered = remember(catalog.games, query, platform) {
        catalog.games.filter { game ->
            val platformMatches = platform == "Tümü" || game.platform.equals(platform, ignoreCase = true)
            val queryMatches = query.isBlank() || game.title.contains(query, ignoreCase = true)
            platformMatches && queryMatches
        }
    }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            if (catalog.fromCache) {
                Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF493C18))) {
                    Text(
                        "Çevrimdışı önbellek gösteriliyor. Yenile ile tekrar deneyebilirsin.",
                        modifier = Modifier.padding(12.dp),
                    )
                }
            }
        }
        item {
            SummaryCards(catalog)
        }
        item {
            Text(
                "Son katalog güncellemesi: ${formatDate(catalog.updatedAt)}",
                color = Color(0xFF8FA5B8),
                fontSize = 12.sp,
            )
        }
        item {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                label = { Text("Oyun ara") },
                placeholder = { Text("Örn. Portal 2") },
            )
        }
        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(platforms) { item ->
                    FilterChip(
                        selected = platform == item,
                        onClick = { platform = item },
                        label = { Text(item) },
                    )
                }
            }
        }
        item {
            Text(
                "Oyunlar (${filtered.size})",
                fontSize = 19.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
        items(filtered, key = { it.id }) { game ->
            GameCard(game, onClick = { onGameClick(game) })
        }
        item { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun SummaryCards(catalog: Catalog) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        StatCard("OYUN", catalog.games.size.toString(), Modifier.weight(1f))
        StatCard("SÜRÜM", catalog.channelCount.toString(), Modifier.weight(1f))
        StatCard("DEPOLAMA", formatBytes(catalog.totalSize), Modifier.weight(1f))
    }
}

@Composable
private fun StatCard(label: String, value: String, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = Color(0xFF142130)),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            Text(label, fontSize = 10.sp, color = Color(0xFF8FA5B8), fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(5.dp))
            Text(value, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold, maxLines = 1)
        }
    }
}

@Composable
private fun GameCard(game: GameInfo, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        colors = CardDefaults.cardColors(containerColor = Color(0xFF101923)),
        shape = RoundedCornerShape(16.dp),
    ) {
        Row(Modifier.fillMaxWidth().padding(12.dp)) {
            AsyncImage(
                model = game.artwork.cover ?: game.artwork.hero,
                contentDescription = game.title,
                modifier = Modifier.size(width = 88.dp, height = 124.dp).clip(RoundedCornerShape(10.dp)),
                contentScale = ContentScale.Crop,
            )
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(game.title, fontSize = 18.sp, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(6.dp))
                Text(game.platform.uppercase(Locale.getDefault()), color = Color(0xFF66C0F4), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text(formatBytes(game.totalSize), fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(5.dp))
                Text(
                    game.channels.joinToString(" • ") { "${it.name} v${it.version}" },
                    color = Color(0xFF9EB1C2),
                    fontSize = 12.sp,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun GameDetailScreen(game: GameInfo, onBack: () -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(game.title, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = { TextButton(onClick = onBack) { Text("← Geri") } },
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                AsyncImage(
                    model = game.artwork.hero ?: game.artwork.cover,
                    contentDescription = game.title,
                    modifier = Modifier.fillMaxWidth().height(220.dp),
                    contentScale = ContentScale.Crop,
                )
            }
            item {
                Column(Modifier.padding(horizontal = 16.dp)) {
                    Text(game.title, fontSize = 26.sp, fontWeight = FontWeight.ExtraBold)
                    Spacer(Modifier.height(6.dp))
                    Text(game.platform.uppercase(Locale.getDefault()), color = Color(0xFF66C0F4), fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MiniStat("Toplam", formatBytes(game.totalSize), Modifier.weight(1f))
                        MiniStat("Kanal", game.channels.size.toString(), Modifier.weight(1f))
                    }
                    if (game.description.isNotBlank()) {
                        Spacer(Modifier.height(16.dp))
                        Text(game.description, color = Color(0xFFC3D0DB), lineHeight = 21.sp)
                    }
                }
            }
            item {
                Text("Yayınlar", fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 16.dp))
            }
            items(game.channels) { channel ->
                Card(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF142130)),
                ) {
                    Column(Modifier.padding(14.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(channel.name.uppercase(Locale.getDefault()), fontWeight = FontWeight.Bold, color = Color(0xFF66C0F4))
                            Text(formatBytes(channel.size), fontWeight = FontWeight.Bold)
                        }
                        Spacer(Modifier.height(5.dp))
                        Text("Sürüm ${channel.version}")
                        if (channel.publishedAt.isNotBlank()) {
                            Text(formatDate(channel.publishedAt), color = Color(0xFF8FA5B8), fontSize = 12.sp)
                        }
                    }
                }
            }
            if (game.artwork.screenshots.isNotEmpty()) {
                item {
                    Text("Ekran görüntüleri", fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 16.dp))
                }
                item {
                    LazyRow(
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        items(game.artwork.screenshots) { url ->
                            AsyncImage(
                                model = url,
                                contentDescription = null,
                                modifier = Modifier.size(width = 240.dp, height = 135.dp).clip(RoundedCornerShape(12.dp)),
                                contentScale = ContentScale.Crop,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MiniStat(label: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier, colors = CardDefaults.cardColors(containerColor = Color(0xFF142130))) {
        Column(Modifier.padding(12.dp)) {
            Text(label, color = Color(0xFF8FA5B8), fontSize = 11.sp)
            Text(value, fontWeight = FontWeight.Bold, fontSize = 17.sp)
        }
    }
}

private fun formatBytes(value: Long): String {
    var size = value.toDouble()
    val units = arrayOf("B", "KiB", "MiB", "GiB", "TiB")
    var index = 0
    while (size >= 1024.0 && index < units.lastIndex) {
        size /= 1024.0
        index++
    }
    return if (index == 0) "${size.toLong()} ${units[index]}" else String.format(Locale.US, "%.2f %s", size, units[index])
}

private fun formatDate(raw: String): String {
    if (raw.isBlank()) return "—"
    return raw.replace("T", " ").substringBefore("+").substringBefore("Z").take(19)
}
