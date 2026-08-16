package com.thedrowned.drowned

data class ReleaseChannel(
    val version: String,
    val tag: String,
    val manifestPath: String,
    val manifestUrl: String,
    val size: Long
)
data class GameEntry(
    val id: String,
    val title: String,
    val platform: String,
    val description: String,
    val artwork: Map<String, String>,
    val channels: Map<String, ReleaseChannel>
)
data class Catalog(val games: List<GameEntry>)
