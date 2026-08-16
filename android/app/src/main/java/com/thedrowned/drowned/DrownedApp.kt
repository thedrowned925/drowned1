package com.thedrowned.drowned

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import java.text.DecimalFormat

private val Bg = Color(0xFF070A10)
private val Surface = Color(0xFF101622)
private val Elevated = Color(0xFF172033)
private val Primary = Color(0xFF6673FF)
private val Muted = Color(0xFF929DAF)

enum class Screen { Home, Library, Downloads, Manager, Settings }

@Composable
fun DrownedApp() {
    MaterialTheme(colorScheme = darkColorScheme(background = Bg, surface = Surface, primary = Primary)) {
        var screen by remember { mutableStateOf(Screen.Home) }
        val context = LocalContext.current
        val prefs = remember { context.getSharedPreferences("drowned", Context.MODE_PRIVATE) }
        var owner by remember { mutableStateOf(prefs.getString("owner", "thedrowned925") ?: "thedrowned925") }
        var repo by remember { mutableStateOf(prefs.getString("repo", "drowned1") ?: "drowned1") }
        var branch by remember { mutableStateOf(prefs.getString("branch", "main") ?: "main") }
        val repository = remember { CatalogRepository() }
        val scope = rememberCoroutineScope()
        var catalog by remember { mutableStateOf(Catalog(emptyList())) }
        var loading by remember { mutableStateOf(false) }
        var error by remember { mutableStateOf<String?>(null) }

        fun refresh() {
            loading = true; error = null
            scope.launch {
                runCatching { repository.load(owner, repo, branch) }
                    .onSuccess { catalog = it }
                    .onFailure { error = it.message }
                loading = false
            }
        }
        LaunchedEffect(Unit) { refresh() }

        Scaffold(
            containerColor = Bg,
            bottomBar = {
                NavigationBar(containerColor = Surface) {
                    Screen.entries.forEach { item ->
                        NavigationBarItem(selected = screen == item, onClick = { screen = item }, icon = { Text(icon(item), fontSize = 18.sp) }, label = { Text(item.name) })
                    }
                }
            }
        ) { padding ->
            Box(Modifier.padding(padding).fillMaxSize()) {
                when (screen) {
                    Screen.Home -> HomeScreen(catalog, loading, error, ::refresh)
                    Screen.Library -> LibraryScreen(catalog)
                    Screen.Downloads -> EmptyScreen("Downloads", "Aktif indirmeler ve devam eden kurulumlar burada görünecek.")
                    Screen.Manager -> ManagerScreen(owner, repo, branch)
                    Screen.Settings -> SettingsScreen(owner, repo, branch, { owner = it }, { repo = it }, { branch = it }) {
                        prefs.edit().putString("owner", owner).putString("repo", repo).putString("branch", branch).apply(); refresh()
                    }
                }
            }
        }
    }
}

private fun icon(s: Screen) = when(s){ Screen.Home->"⌂"; Screen.Library->"▦"; Screen.Downloads->"⇩"; Screen.Manager->"＋"; Screen.Settings->"⚙" }

@Composable
private fun HomeScreen(catalog: Catalog, loading: Boolean, error: String?, refresh: () -> Unit) {
    LazyColumn(contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        item { Text("DROWNED", fontSize = 28.sp, fontWeight = FontWeight.Black, letterSpacing = 3.sp); Text("Your distribution library", color = Muted) }
        item {
            Box(Modifier.fillMaxWidth().height(220.dp).background(Brush.linearGradient(listOf(Color(0xFF1B2450),Color(0xFF11172A),Bg)), RoundedCornerShape(24.dp)).padding(24.dp)) {
                Column(Modifier.align(Alignment.BottomStart)) {
                    Text(catalog.games.firstOrNull()?.title ?: "Drowned Distribution", fontSize = 30.sp, fontWeight = FontWeight.ExtraBold)
                    Text(if (catalog.games.isEmpty()) "Publish your first project from Release Manager" else "${catalog.games.size} projects available", color = Muted)
                    Spacer(Modifier.height(12.dp)); Button(onClick = refresh) { Text(if (loading) "Loading…" else "Refresh catalog") }
                }
            }
        }
        error?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }
        item { SectionTitle("Recently added") }
        item { LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) { items(catalog.games.take(12)) { GameCard(it) } } }
        val groups = catalog.games.groupBy { it.platform.uppercase() }
        groups.forEach { (platform, games) -> item { SectionTitle(platform) }; item { LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) { items(games) { GameCard(it) } } } }
    }
}

@Composable private fun LibraryScreen(catalog: Catalog) {
    var platform by remember { mutableStateOf("ALL") }
    val platforms = listOf("ALL") + catalog.games.map { it.platform.uppercase() }.distinct().sorted()
    LazyColumn(contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { Text("Library", fontSize = 30.sp, fontWeight = FontWeight.ExtraBold) }
        item { LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { items(platforms) { p -> FilterChip(selected=platform==p,onClick={platform=p},label={Text(p)}) } } }
        items(catalog.games.filter { platform=="ALL" || it.platform.equals(platform,true) }) { game -> WideGameCard(game) }
    }
}

@Composable private fun GameCard(game: GameEntry) {
    val stable=game.channels["stable"] ?: game.channels.values.firstOrNull()
    Card(colors=CardDefaults.cardColors(containerColor=Surface), shape=RoundedCornerShape(18.dp), modifier=Modifier.width(190.dp)) {
        Box(Modifier.fillMaxWidth().height(100.dp).background(Brush.linearGradient(listOf(Color(0xFF28366F),Elevated))))
        Column(Modifier.padding(14.dp)) { Text(game.title, fontWeight=FontWeight.Bold, maxLines=1); Text("${game.platform.uppercase()} • ${stable?.version ?: "—"}", color=Muted, fontSize=12.sp) }
    }
}

@Composable private fun WideGameCard(game: GameEntry) {
    val stable=game.channels["stable"] ?: game.channels.values.firstOrNull()
    Card(colors=CardDefaults.cardColors(containerColor=Surface), shape=RoundedCornerShape(18.dp), modifier=Modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), verticalAlignment=Alignment.CenterVertically) {
            Box(Modifier.size(72.dp).background(Brush.linearGradient(listOf(Color(0xFF28366F),Elevated)),RoundedCornerShape(14.dp)))
            Spacer(Modifier.width(14.dp)); Column(Modifier.weight(1f)){ Text(game.title,fontSize=18.sp,fontWeight=FontWeight.Bold); Text(game.platform.uppercase(),color=Muted); Text(stable?.let{"v${it.version} • ${formatBytes(it.size)}"}?:"No release",color=Muted,fontSize=12.sp) }
            FilledTonalButton(onClick={}) { Text("View") }
        }
    }
}

@Composable private fun ManagerScreen(owner:String, repo:String, branch:String) {
    LazyColumn(contentPadding=PaddingValues(18.dp), verticalArrangement=Arrangement.spacedBy(14.dp)) {
        item { Text("Manager",fontSize=30.sp,fontWeight=FontWeight.ExtraBold); Text("Mobile publishing console",color=Muted) }
        item { Card(colors=CardDefaults.cardColors(containerColor=Surface)){ Column(Modifier.padding(18.dp)){ Text("Connected repository",fontWeight=FontWeight.Bold); Text("$owner/$repo • $branch",color=Muted); Spacer(Modifier.height(12.dp)); Text("Large release publishing remains safest from the desktop Release Manager. Mobile uses the same catalog/manifest protocol.",color=Muted) } } }
        item { OutlinedTextField(value="",onValueChange={},label={Text("Project name")},modifier=Modifier.fillMaxWidth()) }
        item { Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){ AssistChip(onClick={},label={Text("PC")}); AssistChip(onClick={},label={Text("PS2")}); AssistChip(onClick={},label={Text("PS3")}); AssistChip(onClick={},label={Text("Other")}) } }
        item { Button(onClick={},modifier=Modifier.fillMaxWidth()){ Text("Prepare mobile release") } }
    }
}

@Composable private fun SettingsScreen(owner:String,repo:String,branch:String,onOwner:(String)->Unit,onRepo:(String)->Unit,onBranch:(String)->Unit,save:()->Unit) {
    LazyColumn(contentPadding=PaddingValues(18.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
        item { Text("Settings",fontSize=30.sp,fontWeight=FontWeight.ExtraBold) }
        item { OutlinedTextField(owner,onOwner,label={Text("GitHub owner")},modifier=Modifier.fillMaxWidth()) }
        item { OutlinedTextField(repo,onRepo,label={Text("Repository")},modifier=Modifier.fillMaxWidth()) }
        item { OutlinedTextField(branch,onBranch,label={Text("Branch")},modifier=Modifier.fillMaxWidth()) }
        item { Button(onClick=save,modifier=Modifier.fillMaxWidth()){ Text("Save & refresh") } }
    }
}

@Composable private fun EmptyScreen(title:String,body:String)=Box(Modifier.fillMaxSize().padding(24.dp)){ Column(Modifier.align(Alignment.Center)){Text(title,fontSize=30.sp,fontWeight=FontWeight.ExtraBold);Text(body,color=Muted)} }
@Composable private fun SectionTitle(value:String)=Text(value,fontSize=20.sp,fontWeight=FontWeight.Bold)
private fun formatBytes(value:Long):String { val gb=value/1024.0/1024.0/1024.0; return DecimalFormat("0.##").format(gb)+" GiB" }
