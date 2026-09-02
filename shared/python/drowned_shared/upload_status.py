from __future__ import annotations

import json
import time
from datetime import datetime, timezone

STATUS_PATH = ".release-status/live.json"

# Progress ticks are throttled to this interval; phase changes always go
# through immediately regardless of the timer. Chosen to keep the mobile
# dashboard feeling live without spamming the Contents API with a commit
# every 0.25s (the underlying publish.py callback rate).
MIN_TICK_INTERVAL_SECONDS = 5.0


class UploadStatusBroadcaster:
    """Publishes coarse upload progress to a small repo-tracked JSON file.

    This is the only bridge between a live Release Manager upload (running on
    someone's desktop) and the mobile Release Manager tab: there is no shared
    server, so progress travels the same way the catalog/manifests already do
    - as a small file committed straight to the distribution repo via the
    Contents API, read back over raw.githubusercontent.com.
    """

    def __init__(self, client, kind: str, title: str, platform: str = "", channel: str = "", version: str = ""):
        self.client = client
        self.kind = kind
        self.title = title
        self.platform = platform
        self.channel = channel
        self.version = version
        self._last_sent = 0.0
        self._last_phase: str | None = None

    def update(self, snapshot: dict) -> None:
        """Feed a drowned_shared.publish detailed_progress snapshot."""
        phase = str(snapshot.get("phase") or "upload")
        if not self._should_send(phase):
            return
        self._push(
            phase=phase,
            total_sent=int(snapshot.get("total_sent") or 0),
            total_size=int(snapshot.get("total_size") or 0),
            active=True,
        )

    def update_simple(self, sent: int, total: int) -> None:
        """Feed a plain (sent, total) progress callback."""
        if not self._should_send("upload"):
            return
        self._push(phase="upload", total_sent=int(sent), total_size=int(total), active=True)

    def finish(self) -> None:
        self._push(phase="done", total_sent=0, total_size=0, active=False)

    def fail(self, message: str = "") -> None:
        self._push(phase="error", total_sent=0, total_size=0, active=False, message=message)

    def _should_send(self, phase: str) -> bool:
        now = time.monotonic()
        if phase != self._last_phase or now - self._last_sent >= MIN_TICK_INTERVAL_SECONDS:
            self._last_sent = now
            self._last_phase = phase
            return True
        return False

    def _push(self, phase: str, total_sent: int, total_size: int, active: bool, message: str = "") -> None:
        percent = int(total_sent * 100 / total_size) if total_size else (100 if phase == "done" else 0)
        body = {
            "active": active,
            "phase": phase,
            "kind": self.kind,
            "title": self.title,
            "platform": self.platform,
            "channel": self.channel,
            "version": self.version,
            "percent": max(0, min(100, percent)),
            "total_sent": total_sent,
            "total_size": total_size,
            "message": message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.client.upsert_text(
                STATUS_PATH,
                json.dumps(body, ensure_ascii=False, indent=2),
                f"Update live upload status ({phase})",
            )
        except Exception:
            # Best-effort telemetry only - never let a status ping break the
            # actual upload it is reporting on.
            pass
