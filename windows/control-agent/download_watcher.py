from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psutil

from archive_manager import ArchiveError, ArchiveManager


FDM_PROCESS_NAMES = {
    "fdm.exe",
    "freedownloadmanager.exe",
    "free download manager.exe",
}


class DownloadWatcher:
    """Observe a user-selected download folder without talking to the source site.

    When a newly observed ZIP becomes stable, the watcher validates it and extracts
    it into a new sibling directory. Existing files are never overwritten.
    """

    def __init__(self):
        self.folder = None
        self.started_at = None
        self.baseline = {}
        self.active_path = None
        self.last_size = 0
        self.last_sample_at = None
        self.last_change_at = None
        self.smoothed_speed = 0.0

        self._archive_lock = threading.Lock()
        self._archive_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="drowned-archive")
        self._archive_future = None
        self._archive_attempt_signature = None
        self.archive_state = "idle"
        self.archive_progress = 0.0
        self.archive_error = None
        self.archive_path = None
        self.extract_folder = None
        self.game_root = None
        self.archive_uncompressed_bytes = 0
        self.archive_file_count = 0

    @staticmethod
    def fdm_running():
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info.get("name") or "").lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if name in FDM_PROCESS_NAMES or "freedownloadmanager" in name.replace(" ", ""):
                return True
        return False

    @staticmethod
    def choose_folder_dialog():
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        value = filedialog.askdirectory(title="Drowned Agent - FDM indirme klasörünü seç")
        root.destroy()
        return value or None

    @staticmethod
    def _files(folder):
        result = {}
        root = Path(folder)
        if not root.exists():
            return result
        try:
            entries = list(root.iterdir())
        except OSError:
            return result

        for entry in entries:
            try:
                if entry.is_file():
                    stat = entry.stat()
                    result[str(entry)] = (stat.st_size, stat.st_mtime)
            except OSError:
                continue
        return result

    def _reset_archive_state(self):
        with self._archive_lock:
            self._archive_attempt_signature = None
            self.archive_state = "idle"
            self.archive_progress = 0.0
            self.archive_error = None
            self.archive_path = None
            self.extract_folder = None
            self.game_root = None
            self.archive_uncompressed_bytes = 0
            self.archive_file_count = 0

    def start(self, folder):
        folder = str(Path(folder).resolve())
        if not Path(folder).is_dir():
            raise RuntimeError("İndirme klasörü bulunamadı.")

        self.folder = folder
        self.started_at = time.time()
        self.baseline = self._files(folder)
        self.active_path = None
        self.last_size = 0
        self.last_sample_at = time.monotonic()
        self.last_change_at = time.monotonic()
        self.smoothed_speed = 0.0
        self._reset_archive_state()
        return self.status("waiting")

    def stop(self):
        snapshot = self.status("stopped")
        self.started_at = None
        self.active_path = None
        self.last_size = 0
        self.last_sample_at = None
        self.last_change_at = None
        self.smoothed_speed = 0.0
        return snapshot

    def _select_candidate(self, files):
        candidates = []
        for path, (size, mtime) in files.items():
            old_size, old_mtime = self.baseline.get(path, (-1, -1))
            if old_size < 0:
                growth = size
            else:
                growth = max(0, size - old_size)
            if old_size < 0 or size != old_size or mtime != old_mtime:
                candidates.append((growth, mtime, size, path))

        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][3]

    def _set_archive(self, **values):
        with self._archive_lock:
            for key, value in values.items():
                setattr(self, key, value)

    def _archive_progress_callback(self, extracted, total):
        percent = min(100.0, max(0.0, extracted * 100.0 / max(1, total)))
        self._set_archive(archive_state="extracting", archive_progress=percent)

    def _archive_workflow(self, path, signature):
        try:
            info = ArchiveManager.inspect(path)
            destination = ArchiveManager.default_destination(path)
            self._set_archive(
                archive_state="extracting",
                archive_progress=0.0,
                archive_error=None,
                archive_path=info["archive_path"],
                extract_folder=str(destination),
                archive_uncompressed_bytes=int(info["uncompressed_bytes"]),
                archive_file_count=int(info["file_count"]),
            )
            result = ArchiveManager.extract(
                path,
                destination=destination,
                progress=self._archive_progress_callback,
                verified_info=info,
            )
            self._set_archive(
                archive_state="extracted",
                archive_progress=100.0,
                extract_folder=result["destination"],
                game_root=result["game_root"],
                archive_error=None,
            )
        except ArchiveError as exc:
            self._set_archive(
                archive_state="archive_error",
                archive_progress=0.0,
                archive_error=str(exc),
            )
        except Exception as exc:
            self._set_archive(
                archive_state="archive_error",
                archive_progress=0.0,
                archive_error=f"Arşiv işlemi başarısız: {exc}",
            )

    def _maybe_start_archive(self, path, size, state):
        if state != "stable" or not path or not ArchiveManager.supported(path):
            return
        signature = (str(path), int(size or 0))
        with self._archive_lock:
            running = self._archive_future is not None and not self._archive_future.done()
            if running or self._archive_attempt_signature == signature:
                return
            self._archive_attempt_signature = signature
            self.archive_state = "archive_verifying"
            self.archive_progress = 0.0
            self.archive_error = None
            self.archive_path = str(path)
            self.extract_folder = None
            self.game_root = None
            self.archive_uncompressed_bytes = 0
            self.archive_file_count = 0
            self._archive_future = self._archive_executor.submit(self._archive_workflow, str(path), signature)

    def poll(self):
        if not self.folder or self.started_at is None:
            return self.status("idle")

        files = self._files(self.folder)
        if self.active_path not in files:
            candidate = self._select_candidate(files)
            if candidate:
                self.active_path = candidate
                self.last_size = files[candidate][0]
                self.last_sample_at = time.monotonic()
                self.last_change_at = self.last_sample_at

        if not self.active_path or self.active_path not in files:
            return self.status("waiting")

        now = time.monotonic()
        size = files[self.active_path][0]
        elapsed = max(0.001, now - (self.last_sample_at or now))
        delta = size - self.last_size
        instant_speed = max(0.0, delta / elapsed)

        if delta != 0:
            self.last_change_at = now
            if self.smoothed_speed <= 0:
                self.smoothed_speed = instant_speed
            else:
                self.smoothed_speed = self.smoothed_speed * 0.7 + instant_speed * 0.3

        self.last_size = size
        self.last_sample_at = now
        stable_for = max(0.0, now - (self.last_change_at or now))

        state = "downloading" if delta > 0 or stable_for < 8 else "stable"
        self._maybe_start_archive(self.active_path, size, state)
        return self.status(state, size=size, stable_for=stable_for)

    def status(self, state, size=None, stable_for=0.0):
        path = Path(self.active_path) if self.active_path else None
        if size is None and path and path.exists():
            try:
                size = path.stat().st_size
            except OSError:
                size = 0

        with self._archive_lock:
            archive_state = self.archive_state
            effective_state = archive_state if state == "stable" and archive_state != "idle" else state
            archive_payload = {
                "archive_state": archive_state,
                "archive_progress": float(self.archive_progress),
                "archive_error": self.archive_error,
                "archive_path": self.archive_path,
                "extract_folder": self.extract_folder,
                "game_root": self.game_root,
                "archive_uncompressed_bytes": int(self.archive_uncompressed_bytes),
                "archive_file_count": int(self.archive_file_count),
            }

        return {
            "state": effective_state,
            "folder": self.folder,
            "file_name": path.name if path else None,
            "file_path": str(path) if path else None,
            "downloaded_bytes": int(size or 0),
            "speed_bps": float(self.smoothed_speed),
            "stable_seconds": float(stable_for),
            "fdm_running": self.fdm_running(),
            "started_at": self.started_at,
            **archive_payload,
        }
