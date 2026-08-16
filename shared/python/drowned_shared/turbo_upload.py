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
DEFAULT_TURBO_WORKERS = 8
MAX_TURBO_WORKERS = 12
TEMP_BUDGET_BYTES = 4 * GIB


def _align_up(value: int, alignment: int = MIB) -> int:
    return max(alignment, ((int(value) + alignment - 1) // alignment) * alignment)


def choose_upload_chunk_size(total_size: int, requested_workers: int = DEFAULT_TURBO_WORKERS) -> int:
    """Pick a chunk size that can use several connections without exhausting release assets.

    Small projects are split across the selected worker count so a single slow GitHub
    connection does not become the whole transfer. Larger projects target 256 MiB
    assets, growing automatically when needed to stay comfortably below GitHub's
    per-release asset count.
    """
    total_size = max(0, int(total_size))
    workers = max(1, min(int(requested_workers or 1), MAX_TURBO_WORKERS))
    if total_size <= 0:
        return CHUNK_SIZE_BYTES

    # Up to 1 GiB: deliberately create enough pieces to keep all selected workers busy.
    if total_size <= GIB:
        per_worker = math.ceil(total_size / workers)
        return min(CHUNK_SIZE_BYTES, _align_up(max(8 * MIB, per_worker), MIB))

    # Normal large-game target. 900 leaves room under GitHub's 999 data-asset ceiling.
    desired = 256 * MIB
    required_for_asset_budget = math.ceil(total_size / min(900, MAX_DATA_ASSETS))
    chosen = max(desired, required_for_asset_budget)
    return min(CHUNK_SIZE_BYTES, _align_up(chosen, 8 * MIB))


def effective_worker_count(chunk_size: int, requested_workers: int) -> int:
    requested = max(1, min(int(requested_workers or 1), MAX_TURBO_WORKERS))
    by_temp_space = max(1, TEMP_BUDGET_BYTES // max(int(chunk_size), 1))
    return max(1, min(requested, int(by_temp_space)))


class TurboAssetUploader:
    """Thread-safe release asset uploader with per-thread HTTP sessions and backoff."""

    def __init__(self, client, release_id: int, min_start_interval: float = 0.20):
        self.client = client
        self.release_id = int(release_id)
        self.min_start_interval = max(0.0, float(min_start_interval))
        self._thread_local = threading.local()
        self._start_lock = threading.Lock()
        self._last_start = 0.0

    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update({
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "User-Agent": "Drowned-Distribution-Suite/0.5-gigabit",
                "Authorization": f"Bearer {self.client.token}",
            })
            self._thread_local.session = session
        return session

    def _wait_for_start_slot(self):
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
                time.sleep(min(30, 2 ** attempt))
                continue

            if response.ok:
                return response.json()

            if self._secondary_limited(response):
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else min(60, 5 * (2 ** attempt))
                last_error = NetworkError(f"GitHub secondary rate limit: HTTP {response.status_code}")
                time.sleep(wait)
                continue

            if response.status_code in (500, 502, 503, 504) and attempt < 4:
                last_error = NetworkError(f"GitHub upload HTTP {response.status_code}")
                time.sleep(min(30, 2 ** attempt))
                continue

            message = self.client._permission_help(response.status_code, response.text)
            if response.status_code in (401, 403):
                raise AuthenticationError(message)
            raise NetworkError(f"asset upload: {message}")

        if last_error:
            raise last_error
        raise NetworkError("asset upload failed")
