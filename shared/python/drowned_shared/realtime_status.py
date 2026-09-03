from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests


SUPABASE_PROJECT_URL = "https://hfigrspqyxhscbkmporz.supabase.co"
LIVE_UPDATE_URL = f"{SUPABASE_PROJECT_URL}/functions/v1/release-live-update"
# Phase transitions / finish / errors use force=True and remain immediate. During
# steady transfer we only need a few updates per second on the phone, so keep
# ample headroom under the Supabase Free Edge Function invocation quota.
MIN_PUSH_INTERVAL_SECONDS = 3.0


@dataclass
class LiveContext:
    kind: str = "release"
    title: str = ""
    platform: str = ""
    channel: str = ""
    version: str = ""
    machine_id: str = "primary"


class LiveStatusPublisher:
    """Best-effort, non-blocking publisher for the mobile realtime dashboard.

    The desktop's existing GitHub token is used only to prove that the caller is
    the repository owner to the Supabase Edge Function. The token is never stored
    in Supabase and is not committed to the repository.
    """

    def __init__(
        self,
        github_token: str,
        kind: str = "release",
        title: str = "",
        platform: str = "",
        channel: str = "",
        version: str = "",
        machine_id: str = "primary",
    ):
        self.github_token = str(github_token or "").strip()
        self.context = LiveContext(kind, title, platform, channel, version, machine_id)
        self._queue: queue.Queue[dict | None] = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_enqueue = 0.0
        self._last_phase = ""
        self._started_at = time.monotonic()
        self._last_done = 0
        self._last_done_at = self._started_at
        self._average_speed = 0.0

        if self.github_token:
            self._thread = threading.Thread(
                target=self._worker,
                name="drowned-live-status",
                daemon=True,
            )
            self._thread.start()

    @property
    def enabled(self) -> bool:
        return bool(self.github_token and self._thread is not None)

    def set_context(
        self,
        *,
        kind: str | None = None,
        title: str | None = None,
        platform: str | None = None,
        channel: str | None = None,
        version: str | None = None,
    ) -> None:
        if kind is not None:
            self.context.kind = str(kind)
        if title is not None:
            self.context.title = str(title)
        if platform is not None:
            self.context.platform = str(platform)
        if channel is not None:
            self.context.channel = str(channel)
        if version is not None:
            self.context.version = str(version)

    def update(self, snapshot: dict[str, Any], *, force: bool = False, active: bool = True) -> None:
        if not self.enabled:
            return
        phase = str(snapshot.get("phase") or "working")
        now = time.monotonic()
        if not force and phase == self._last_phase and now - self._last_enqueue < MIN_PUSH_INTERVAL_SECONDS:
            return

        done = int(snapshot.get("done", snapshot.get("total_sent", 0)) or 0)
        total = int(snapshot.get("total", snapshot.get("total_size", 0)) or 0)
        explicit_speed = float(snapshot.get("speed") or 0.0)
        dt = max(0.001, now - self._last_done_at)
        derived_speed = max(0.0, (done - self._last_done) / dt) if done >= self._last_done else 0.0
        speed = explicit_speed if explicit_speed > 0 else derived_speed

        elapsed = max(0.001, now - self._started_at)
        average = float(snapshot.get("average_speed") or 0.0)
        if average <= 0 and done > 0:
            average = done / elapsed
        if average > 0:
            self._average_speed = average

        eta_value = snapshot.get("eta")
        if eta_value is None and total > done and speed > 0:
            eta_value = (total - done) / speed

        progress = snapshot.get("progress")
        if progress is None:
            percent = int(done * 100 / total) if total else 0
        else:
            percent = int(max(0.0, min(1.0, float(progress))) * 100)

        active_rows = snapshot.get("active") or []
        current_item = str(snapshot.get("current_item") or snapshot.get("detail") or "")
        if not current_item and active_rows:
            first = active_rows[0] if isinstance(active_rows[0], dict) else {}
            current_item = str(first.get("file") or first.get("chunk") or "")

        payload = {
            "machine_id": self.context.machine_id,
            "active": bool(active),
            "phase": phase,
            "kind": self.context.kind,
            "title": self.context.title,
            "platform": self.context.platform,
            "channel": self.context.channel,
            "version": self.context.version,
            "percent": max(0, min(100, percent)),
            "speed_bps": max(0, int(speed)),
            "avg_speed_bps": max(0, int(self._average_speed)),
            "eta_seconds": None if eta_value is None else max(0, int(float(eta_value))),
            "processed_bytes": max(0, done),
            "total_bytes": max(0, total),
            "connections": max(
                0,
                int(
                    snapshot.get("active_connections")
                    or snapshot.get("connections")
                    or snapshot.get("workers")
                    or 0
                ),
            ),
            "current_item": current_item,
            "message": str(snapshot.get("message") or snapshot.get("detail") or ""),
        }

        self._last_enqueue = now
        self._last_phase = phase
        self._last_done = done
        self._last_done_at = now
        self._offer(payload)

    def finish(self, phase: str = "complete", message: str = "") -> None:
        self.update(
            {
                "phase": phase,
                "done": self._last_done,
                "total": self._last_done,
                "progress": 1.0 if phase in {"complete", "done"} else 0.0,
                "speed": 0.0,
                "eta": 0,
                "message": message,
            },
            force=True,
            active=False,
        )

    def fail(self, message: str) -> None:
        self.update(
            {
                "phase": "error",
                "done": self._last_done,
                "total": max(self._last_done, 1),
                "speed": 0.0,
                "eta": None,
                "message": message,
            },
            force=True,
            active=False,
        )

    def _offer(self, payload: dict) -> None:
        try:
            self._queue.put_nowait(payload)
            return
        except queue.Full:
            pass
        try:
            self._queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            pass

    def _worker(self) -> None:
        session = requests.Session()
        session.headers.update(
            {
                "user-agent": "Drowned-Release-Manager-Realtime/1.0",
                "content-type": "application/json",
                "x-github-token": self.github_token,
            }
        )
        while not self._stop.is_set():
            try:
                payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if payload is None:
                break
            try:
                session.post(LIVE_UPDATE_URL, json=payload, timeout=(3, 5))
            except requests.RequestException:
                # Telemetry must never affect the actual download/upload job.
                pass

    def close(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
