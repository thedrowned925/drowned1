from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from .realtime_status import LiveStatusPublisher

STATUS_PATH = ".release-status/live.json"
LEGACY_GITHUB_INTERVAL_SECONDS = 15.0


class UploadStatusBroadcaster:
    """Publishes live progress to Supabase and keeps GitHub JSON as fallback.

    Supabase is the fast path used by Android Realtime. The legacy repo-tracked
    JSON remains as a low-frequency fallback so older Android builds continue to
    work and a temporary Supabase outage never affects the real publish job.
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
        self.realtime = LiveStatusPublisher(
            client.token,
            kind=kind,
            title=title,
            platform=platform,
            channel=channel,
            version=version,
        )

    def update(self, snapshot: dict) -> None:
        """Feed a drowned_shared.publish detailed_progress snapshot."""
        phase = str(snapshot.get("phase") or "upload")
        self.realtime.update(snapshot, active=True)
        if not self._should_send_legacy(phase):
            return
        self._push_legacy(
            phase=phase,
            total_sent=int(snapshot.get("total_sent") or 0),
            total_size=int(snapshot.get("total_size") or 0),
            active=True,
        )

    def update_simple(self, sent: int, total: int) -> None:
        """Feed a plain (sent, total) progress callback."""
        snapshot = {
            "phase": "upload",
            "total_sent": int(sent),
            "total_size": int(total),
        }
        self.realtime.update(snapshot, active=True)
        if self._should_send_legacy("upload"):
            self._push_legacy("upload", int(sent), int(total), True)

    def finish(self) -> None:
        self.realtime.finish("done")
        self._push_legacy(phase="done", total_sent=0, total_size=0, active=False)

    def fail(self, message: str = "") -> None:
        self.realtime.fail(message)
        self._push_legacy(phase="error", total_sent=0, total_size=0, active=False, message=message)

    def _should_send_legacy(self, phase: str) -> bool:
        now = time.monotonic()
        if phase != self._last_phase or now - self._last_sent >= LEGACY_GITHUB_INTERVAL_SECONDS:
            self._last_sent = now
            self._last_phase = phase
            return True
        return False

    def _push_legacy(self, phase: str, total_sent: int, total_size: int, active: bool, message: str = "") -> None:
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
            pass
