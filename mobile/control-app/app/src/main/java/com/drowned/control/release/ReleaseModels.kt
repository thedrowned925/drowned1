package com.drowned.control.release

/** minSdk 26 ships java.time natively, no desugaring needed. */
internal fun parseIsoInstantMillis(raw: String): Long? =
    try {
        java.time.Instant.parse(raw).toEpochMilli()
    } catch (_: Exception) {
        null
    }

data class JobStep(
    val name: String,
    val status: String,
    val conclusion: String?,
    val number: Int,
)

data class WorkflowJob(
    val name: String,
    val status: String,
    val conclusion: String?,
    val steps: List<JobStep>,
)

data class WorkflowRun(
    val id: Long,
    val name: String,
    val displayTitle: String,
    val status: String,
    val conclusion: String?,
    val branch: String,
    val event: String,
    val runNumber: Int,
    val createdAt: String,
    val updatedAt: String,
    val htmlUrl: String,
    val actor: String,
    val jobs: List<WorkflowJob> = emptyList(),
) {
    val isLive: Boolean get() = status != "completed"

    private val allSteps: List<JobStep> get() = jobs.flatMap { it.steps }

    /** Step-completion ratio as a live proxy for upload/build progress (0-100). Null when no step data yet. */
    val progressPercent: Int?
        get() {
            val steps = allSteps
            if (steps.isEmpty()) return null
            val completed = steps.count { it.status == "completed" }
            return (completed * 100) / steps.size
        }

    /** Name of the step currently executing, falling back to the last finished step. */
    val currentStageName: String?
        get() = allSteps.firstOrNull { it.status == "in_progress" }?.name
            ?: allSteps.lastOrNull { it.status == "completed" }?.name
            ?: jobs.firstOrNull { it.status != "completed" }?.name
}

data class ReleaseAsset(
    val name: String,
    val size: Long,
    val downloadCount: Long,
    val downloadUrl: String,
    val contentType: String,
)

data class ReleaseInfo(
    val id: Long,
    val name: String,
    val tagName: String,
    val isDraft: Boolean,
    val isPrerelease: Boolean,
    val publishedAt: String,
    val createdAt: String,
    val htmlUrl: String,
    val body: String,
    val assets: List<ReleaseAsset>,
) {
    val totalSize: Long get() = assets.sumOf { it.size }
    val totalDownloads: Long get() = assets.sumOf { it.downloadCount }
}

data class BuildStatus(
    val componentName: String,
    val status: String,
    val runId: String,
    val sha: String,
    val time: String,
)

/**
 * UI shape used by both the old GitHub live.json fallback and the new Supabase
 * Realtime transport. Supabase supplies this value continuously; GitHub remains
 * a compatibility fallback for older/temporarily disconnected clients.
 */
data class LiveUploadStatus(
    val active: Boolean,
    val phase: String,
    val kind: String,
    val title: String,
    val platform: String,
    val channel: String,
    val version: String,
    val percent: Int,
    val totalSent: Long,
    val totalSize: Long,
    val message: String,
    val updatedAt: String,
) {
    /** Guards against a crashed desktop run leaving a stuck "active" status behind. */
    val isFresh: Boolean
        get() {
            val updatedMillis = parseIsoInstantMillis(updatedAt) ?: return false
            return System.currentTimeMillis() - updatedMillis < STALE_AFTER_MS
        }

    companion object {
        private const val STALE_AFTER_MS = 60_000L
    }
}

class ReleaseDashboard(
    val workflowRuns: List<WorkflowRun>,
    val releases: List<ReleaseInfo>,
    val buildStatuses: List<BuildStatus>,
    liveUpload: LiveUploadStatus?,
    val fromCache: Boolean,
) {
    private val fallbackLiveUpload = liveUpload

    init {
        RealtimeLiveStore.ensureStarted()
    }

    /**
     * Compose observes RealtimeLiveStore.status because this getter is read from
     * ReleaseManagerScreen. Supabase therefore refreshes the live card instantly
     * without waiting for the 8/45 second GitHub polling loop.
     */
    val liveUpload: LiveUploadStatus?
        get() = RealtimeLiveStore.status.value ?: fallbackLiveUpload

    val latestRun: WorkflowRun? get() = workflowRuns.firstOrNull()
    val recentReleases: List<ReleaseInfo> get() = releases.take(20)
    val failedRuns: List<WorkflowRun> get() = workflowRuns.filter { it.conclusion == "failure" }
    val runningRuns: List<WorkflowRun> get() = workflowRuns.filter { it.status != "completed" }
}
