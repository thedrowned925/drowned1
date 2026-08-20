from __future__ import annotations

import math
import threading
import time
from pathlib import Path

import requests

from .constants import CHUNK_SIZE_BYTES, GITHUB_API_VERSION, GITHUB_UPLOADS, MAX_DATA_ASSETS
from .errors import AuthenticationError, NetworkError

MIB = 1024 * 1024
GIB = 1024 * MIB

# Keep the established chunk plan exactly as before. Upload concurrency may go
# higher, but chunk sizing still targets the old 16-stream layout so existing
# 1.5 GiB large-game chunks and manifest behaviour do not change.
CHUNK_PLANNING_WORKERS = 16
DEFAULT_TURBO_WORKERS = 32
MAX_TURBO_WORKERS = 32

# 32 x 1.5 GiB is the absolute scratch ceiling for the aggressive profile.
# publish.py also checks actual free space and keeps an 8 GiB safety reserve,
# automatically reducing the worker count when the temp drive is smaller.
TEMP_BUDGET_BYTES = 48 * GIB
TEMP_RESERVE_BYTES = 8 * GIB


def _align_up(value: int, alignment: int = MIB) -> int:
    return max(alignment, ((int(value) + alignment - 1) // alignment) * alignment)


def choose_upload_chunk_size(total_size: int, requested_workers: int = DEFAULT_TURBO_WORKERS) -> int:
    """Choose the established adaptive chunk size without changing chunk layout.

    Upload concurrency can now reach 32, but chunk planning intentionally caps
    itself at 16 workers. That preserves the existing chunk sizes/counts while
    allowing more already-planned chunks to upload at once on large projects.
    """
    total_size = max(0, int(total_size))
    workers = max(1, min(int(requested_workers or 1), CHUNK_PLANNING_WORKERS))
    if total_size <= 0:
        return CHUNK_SIZE_BYTES

    target_for_parallelism = max(4 * MIB, math.ceil(total_size / workers))
    required_for_asset_budget = math.ceil(total_size / min(900, MAX_DATA_ASSETS))

    chosen = max(target_for_parallelism, required_for_asset_budget)
    chosen = min(CHUNK_SIZE_BYTES, chosen)
    return min(CHUNK_SIZE_BYTES, _align_up(chosen, MIB))


def effective_worker_count(
    chunk_size: int,
    requested_workers: int,
    free_temp_bytes: int | None = None,
) -> int:
    """Return a safe upload concurrency for the current scratch-space budget."""
    requested = max(1, min(int(requested_workers or 1), MAX_TURBO_WORKERS))
    budget = TEMP_BUDGET_BYTES
    if free_temp_bytes is not None:
        usable = max(0, int(free_temp_bytes) - TEMP_RESERVE_BYTES)
        budget = min(budget, usable)
    by_temp_space = budget // max(int(chunk_size), 1)
    return max(1, min(requested, int(by_temp_space)))


class TurboAssetUploader:
    """Thread-safe Release asset uploader with per-thread sessions and shared backoff."""

    def __init__(self, client, release_id: int, min_start_interval: float = 0.15):
        self.client = client
        self.release_id = int(release_id)
        self.min_start_interval = max(0.0, float(min_start_interval))
        self._thread_local = threading.local()
        self._start_lock = threading.Lock()
        self._last_start = 0.0
        self._backoff_lock = threading.Lock()
        self._backoff_until = 0.0

    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update({
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "User-Agent": "Drowned-Distribution-Suite/0.8-gigabit32",
                "Authorization": f"Bearer {self.client.token}",
            })
            self._thread_local.session = session
        return session

    def _wait_global_backoff(self):
        while True:
            with self._backoff_lock:
                remaining = self._backoff_until - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 1.0))

    def _set_global_backoff(self, seconds: float):
        seconds = max(1.0, float(seconds))
        with self._backoff_lock:
            self._backoff_until = max(self._backoff_until, time.monotonic() + seconds)

    def _wait_for_start_slot(self):
        self._wait_global_backoff()
        with self._start_lock:
            now = time.monotonic()
            delay = self.min_start_interval - (now - self._last_start)
            if delay > 0:
                time.sleep(delay)
            self._last_start = time.monotonic()

    @staticmethod
    def _secondary_limited(response: requests.Response) -> bool:
        if response.status_code not in (403, 429):
            return False
        text = response.text.lower()
        return (
            "secondary rate limit" in text
            or "abuse detection" in text
            or response.headers.get("Retry-After") is not None
        )

    def upload(self, name: str, path: Path, progress=None, content_type: str = "application/octet-stream"):
        path = Path(path)
        total = path.stat().st_size

        class Reader:
            def __init__(self, fp):
                self.fp = fp
                self.sent = 0

            def read(self, n=-1):
                block = self.fp.read(n)
                if block:
                    self.sent += len(block)
                    if progress:
                        progress(self.sent, total)
                return block

            def __getattr__(self, attr):
                return getattr(self.fp, attr)

        url = f"{GITHUB_UPLOADS}/repos/{self.client.owner}/{self.client.repo}/releases/{self.release_id}/assets"
        last_error = None
        for attempt in range(5):
            self._wait_for_start_slot()
            try:
                with path.open("rb") as handle:
                    response = self._session().post(
                        url,
                        params={"name": name},
                        headers={"Content-Type": content_type, "Content-Length": str(total)},
                        data=Reader(handle),
                        timeout=(30, 12 * 60 * 60),
                    )
            except requests.RequestException as exc:
                last_error = exc
                if attempt == 4:
                    raise NetworkError(f"asset upload network error: {exc}") from exc
                wait = min(30, 2 ** attempt)
                self._set_global_backoff(wait)
                continue

            if response.ok:
                return response.json()

            if self._secondary_limited(response):
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else min(60, 5 * (2 ** attempt))
                last_error = NetworkError(f"GitHub secondary rate limit: HTTP {response.status_code}")
                # One worker hitting secondary limits pauses new starts for all
                # workers instead of allowing the rest to keep hammering GitHub.
                self._set_global_backoff(wait)
                continue

            if response.status_code in (500, 502, 503, 504) and attempt < 4:
                wait = min(30, 2 ** attempt)
                last_error = NetworkError(f"GitHub upload HTTP {response.status_code}")
                self._set_global_backoff(wait)
                continue

            message = self.client._permission_help(response.status_code, response.text)
            if response.status_code in (401, 403):
                raise AuthenticationError(message)
            raise NetworkError(f"asset upload: {message}")

        if last_error:
            raise last_error
        raise NetworkError("asset upload failed")
