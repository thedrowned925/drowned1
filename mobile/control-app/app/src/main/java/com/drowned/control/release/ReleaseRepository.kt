package com.drowned.control.release

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

private const val OWNER = "thedrowned925"
private const val REPO = "drowned1"
private const val API_BASE = "https://api.github.com/repos/$OWNER/$REPO"
private const val RAW_BASE = "https://raw.githubusercontent.com/$OWNER/$REPO/main"

private val BUILD_STATUS_FILES = listOf(
    "mobile-control-v1" to ".build-status/mobile-control-v1.txt",
    "optional-packages-v1" to ".build-status/optional-packages-v1.txt",
)

private const val LIVE_UPLOAD_STATUS_PATH = ".release-status/live.json"

object ReleaseRepository {

    suspend fun load(context: Context): ReleaseDashboard = withContext(Dispatchers.IO) {
        val prefs = context.getSharedPreferences("drowned_release", Context.MODE_PRIVATE)
        try {
            val runs = fetchWorkflowRuns(prefs)
            val releases = fetchReleases(prefs)
            val statuses = fetchBuildStatuses()
            val liveUpload = fetchLiveUploadStatus()
            val runsWithJobs = runs.map { run ->
                if (run.isLive) {
                    try {
                        run.copy(jobs = fetchJobsForRun(prefs, run.id))
                    } catch (error: Exception) {
                        run
                    }
                } else run
            }
            val dashboard = ReleaseDashboard(runsWithJobs, releases, statuses, liveUpload, fromCache = false)
            prefs.edit().putString("release_dashboard", serialize(dashboard)).apply()
            dashboard
        } catch (error: Exception) {
            val cached = prefs.getString("release_dashboard", null)
            if (cached.isNullOrBlank()) throw error
            deserialize(cached)
        }
    }

    /**
     * Conditional GET keyed by ETag: an unchanged resource returns HTTP 304 with an empty body,
     * and 304 responses do not count against GitHub's unauthenticated API rate limit. This is what
     * lets the dashboard poll frequently for live progress without exhausting the 60 req/hour quota.
     */
    private fun fetchJsonCached(prefs: android.content.SharedPreferences, cacheKey: String, url: String): String {
        val etag = prefs.getString("etag_$cacheKey", null)
        val connection = openConnection(url)
        if (etag != null) connection.setRequestProperty("If-None-Match", etag)
        connection.connect()
        return when (connection.responseCode) {
            304 -> {
                connection.disconnect()
                prefs.getString("body_$cacheKey", null) ?: error("No cached body for $cacheKey")
            }
            in 200..299 -> {
                val text = readAll(connection)
                val newEtag = connection.getHeaderField("ETag")
                connection.disconnect()
                prefs.edit().apply {
                    putString("body_$cacheKey", text)
                    if (newEtag != null) putString("etag_$cacheKey", newEtag)
                }.apply()
                text
            }
            else -> {
                connection.disconnect()
                error("GitHub API HTTP ${connection.responseCode} for $cacheKey")
            }
        }
    }

    private fun fetchWorkflowRuns(prefs: android.content.SharedPreferences): List<WorkflowRun> {
        val text = fetchJsonCached(prefs, "runs", "$API_BASE/actions/runs?per_page=30")
        val root = JSONObject(text)
        val array = root.optJSONArray("workflow_runs") ?: return emptyList()
        return buildList {
            for (i in 0 until array.length()) {
                val item = array.optJSONObject(i) ?: continue
                add(
                    WorkflowRun(
                        id = item.optLong("id"),
                        name = item.optString("name"),
                        displayTitle = item.optString("display_title"),
                        status = item.optString("status"),
                        conclusion = item.optString("conclusion").takeIf { it.isNotBlank() && it != "null" },
                        branch = item.optString("head_branch"),
                        event = item.optString("event"),
                        runNumber = item.optInt("run_number"),
                        createdAt = item.optString("created_at"),
                        updatedAt = item.optString("updated_at"),
                        htmlUrl = item.optString("html_url"),
                        actor = item.optJSONObject("actor")?.optString("login") ?: "",
                    )
                )
            }
        }
    }

    private fun fetchReleases(prefs: android.content.SharedPreferences): List<ReleaseInfo> {
        val text = fetchJsonCached(prefs, "releases", "$API_BASE/releases?per_page=30")
        val array = JSONArray(text)
        return buildList {
            for (i in 0 until array.length()) {
                val item = array.optJSONObject(i) ?: continue
                val assetsArray = item.optJSONArray("assets") ?: JSONArray()
                val assets = buildList {
                    for (j in 0 until assetsArray.length()) {
                        val a = assetsArray.optJSONObject(j) ?: continue
                        add(
                            ReleaseAsset(
                                name = a.optString("name"),
                                size = a.optLong("size"),
                                downloadCount = a.optLong("download_count"),
                                downloadUrl = a.optString("browser_download_url"),
                                contentType = a.optString("content_type"),
                            )
                        )
                    }
                }
                add(
                    ReleaseInfo(
                        id = item.optLong("id"),
                        name = item.optString("name").ifBlank { item.optString("tag_name") },
                        tagName = item.optString("tag_name"),
                        isDraft = item.optBoolean("draft"),
                        isPrerelease = item.optBoolean("prerelease"),
                        publishedAt = item.optString("published_at"),
                        createdAt = item.optString("created_at"),
                        htmlUrl = item.optString("html_url"),
                        body = item.optString("body"),
                        assets = assets,
                    )
                )
            }
        }
    }

    private fun fetchJobsForRun(prefs: android.content.SharedPreferences, runId: Long): List<WorkflowJob> {
        val text = fetchJsonCached(prefs, "jobs_$runId", "$API_BASE/actions/runs/$runId/jobs")
        val array = JSONObject(text).optJSONArray("jobs") ?: JSONArray()
        return buildList {
            for (i in 0 until array.length()) {
                val job = array.optJSONObject(i) ?: continue
                val stepsArray = job.optJSONArray("steps") ?: JSONArray()
                val steps = buildList {
                    for (j in 0 until stepsArray.length()) {
                        val step = stepsArray.optJSONObject(j) ?: continue
                        add(
                            JobStep(
                                name = step.optString("name"),
                                status = step.optString("status"),
                                conclusion = step.optString("conclusion").takeIf { it.isNotBlank() && it != "null" },
                                number = step.optInt("number"),
                            )
                        )
                    }
                }
                add(
                    WorkflowJob(
                        name = job.optString("name"),
                        status = job.optString("status"),
                        conclusion = job.optString("conclusion").takeIf { it.isNotBlank() && it != "null" },
                        steps = steps,
                    )
                )
            }
        }
    }

    private fun fetchBuildStatuses(): List<BuildStatus> {
        return BUILD_STATUS_FILES.map { (name, path) ->
            val connection = openConnection("$RAW_BASE/$path")
            connection.connect()
            if (connection.responseCode !in 200..299) {
                connection.disconnect()
                return@map BuildStatus(name, "unknown", "", "", "")
            }
            val text = readAll(connection)
            connection.disconnect()
            parseBuildStatus(name, text)
        }
    }

    private fun fetchLiveUploadStatus(): LiveUploadStatus? {
        val connection = openConnection("$RAW_BASE/$LIVE_UPLOAD_STATUS_PATH")
        connection.connect()
        if (connection.responseCode !in 200..299) {
            connection.disconnect()
            return null
        }
        val text = readAll(connection)
        connection.disconnect()
        return try {
            parseLiveUploadStatus(JSONObject(text))
        } catch (error: Exception) {
            null
        }
    }

    private fun parseLiveUploadStatus(item: JSONObject): LiveUploadStatus = LiveUploadStatus(
        active = item.optBoolean("active"),
        phase = item.optString("phase"),
        kind = item.optString("kind"),
        title = item.optString("title"),
        platform = item.optString("platform"),
        channel = item.optString("channel"),
        version = item.optString("version"),
        percent = item.optInt("percent"),
        totalSent = item.optLong("total_sent"),
        totalSize = item.optLong("total_size"),
        message = item.optString("message"),
        updatedAt = item.optString("updated_at"),
    )

    private fun parseBuildStatus(name: String, text: String): BuildStatus {
        var status = "unknown"
        var run = ""
        var sha = ""
        var time = ""
        for (line in text.lineSequence()) {
            val trimmed = line.trim()
            if (trimmed.isEmpty()) continue
            val idx = trimmed.indexOf('=')
            if (idx <= 0) continue
            val key = trimmed.substring(0, idx).trim()
            val value = trimmed.substring(idx + 1).trim()
            when (key) {
                "status" -> status = value
                "run" -> run = value
                "sha" -> sha = value
                "time" -> time = value
            }
        }
        return BuildStatus(name, status, run, sha, time)
    }

    private fun openConnection(url: String): HttpURLConnection {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 12_000
            readTimeout = 20_000
            requestMethod = "GET"
            setRequestProperty("User-Agent", "Drowned-Control-Android/1.0")
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("Cache-Control", "no-cache")
        }
        return conn
    }

    private fun readAll(connection: HttpURLConnection): String {
        val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
        return BufferedReader(InputStreamReader(stream)).use { it.readText() }
    }

    private fun serialize(dashboard: ReleaseDashboard): String {
        val root = JSONObject()
        root.put("fromCache", false)
        val runsArray = JSONArray()
        dashboard.workflowRuns.forEach { run ->
            val obj = JSONObject()
            obj.put("id", run.id)
            obj.put("name", run.name)
            obj.put("displayTitle", run.displayTitle)
            obj.put("status", run.status)
            obj.put("conclusion", run.conclusion ?: "")
            obj.put("branch", run.branch)
            obj.put("event", run.event)
            obj.put("runNumber", run.runNumber)
            obj.put("createdAt", run.createdAt)
            obj.put("updatedAt", run.updatedAt)
            obj.put("htmlUrl", run.htmlUrl)
            obj.put("actor", run.actor)
            runsArray.put(obj)
        }
        root.put("workflowRuns", runsArray)
        val releasesArray = JSONArray()
        dashboard.releases.forEach { rel ->
            val obj = JSONObject()
            obj.put("id", rel.id)
            obj.put("name", rel.name)
            obj.put("tagName", rel.tagName)
            obj.put("isDraft", rel.isDraft)
            obj.put("isPrerelease", rel.isPrerelease)
            obj.put("publishedAt", rel.publishedAt)
            obj.put("createdAt", rel.createdAt)
            obj.put("htmlUrl", rel.htmlUrl)
            obj.put("body", rel.body)
            val assetsArray = JSONArray()
            rel.assets.forEach { asset ->
                val a = JSONObject()
                a.put("name", asset.name)
                a.put("size", asset.size)
                a.put("downloadCount", asset.downloadCount)
                a.put("downloadUrl", asset.downloadUrl)
                a.put("contentType", asset.contentType)
                assetsArray.put(a)
            }
            obj.put("assets", assetsArray)
            releasesArray.put(obj)
        }
        root.put("releases", releasesArray)
        val statusesArray = JSONArray()
        dashboard.buildStatuses.forEach { bs ->
            val obj = JSONObject()
            obj.put("componentName", bs.componentName)
            obj.put("status", bs.status)
            obj.put("runId", bs.runId)
            obj.put("sha", bs.sha)
            obj.put("time", bs.time)
            statusesArray.put(obj)
        }
        root.put("buildStatuses", statusesArray)
        return root.toString()
    }

    private fun deserialize(text: String): ReleaseDashboard {
        val root = JSONObject(text)
        val runsArray = root.optJSONArray("workflowRuns") ?: JSONArray()
        val runs = buildList {
            for (i in 0 until runsArray.length()) {
                val item = runsArray.optJSONObject(i) ?: continue
                add(
                    WorkflowRun(
                        id = item.optLong("id"),
                        name = item.optString("name"),
                        displayTitle = item.optString("displayTitle"),
                        status = item.optString("status"),
                        conclusion = item.optString("conclusion").takeIf { it.isNotBlank() },
                        branch = item.optString("branch"),
                        event = item.optString("event"),
                        runNumber = item.optInt("runNumber"),
                        createdAt = item.optString("createdAt"),
                        updatedAt = item.optString("updatedAt"),
                        htmlUrl = item.optString("htmlUrl"),
                        actor = item.optString("actor"),
                    )
                )
            }
        }
        val releasesArray = root.optJSONArray("releases") ?: JSONArray()
        val releases = buildList {
            for (i in 0 until releasesArray.length()) {
                val item = releasesArray.optJSONObject(i) ?: continue
                val assetsArray = item.optJSONArray("assets") ?: JSONArray()
                val assets = buildList {
                    for (j in 0 until assetsArray.length()) {
                        val a = assetsArray.optJSONObject(j) ?: continue
                        add(
                            ReleaseAsset(
                                name = a.optString("name"),
                                size = a.optLong("size"),
                                downloadCount = a.optLong("downloadCount"),
                                downloadUrl = a.optString("downloadUrl"),
                                contentType = a.optString("contentType"),
                            )
                        )
                    }
                }
                add(
                    ReleaseInfo(
                        id = item.optLong("id"),
                        name = item.optString("name"),
                        tagName = item.optString("tagName"),
                        isDraft = item.optBoolean("isDraft"),
                        isPrerelease = item.optBoolean("isPrerelease"),
                        publishedAt = item.optString("publishedAt"),
                        createdAt = item.optString("createdAt"),
                        htmlUrl = item.optString("htmlUrl"),
                        body = item.optString("body"),
                        assets = assets,
                    )
                )
            }
        }
        val statusesArray = root.optJSONArray("buildStatuses") ?: JSONArray()
        val statuses = buildList {
            for (i in 0 until statusesArray.length()) {
                val item = statusesArray.optJSONObject(i) ?: continue
                add(
                    BuildStatus(
                        componentName = item.optString("componentName"),
                        status = item.optString("status"),
                        runId = item.optString("runId"),
                        sha = item.optString("sha"),
                        time = item.optString("time"),
                    )
                )
            }
        }
        // Live upload status is deliberately not cached - it is only meaningful in the moment.
        return ReleaseDashboard(runs, releases, statuses, liveUpload = null, fromCache = true)
    }
}
