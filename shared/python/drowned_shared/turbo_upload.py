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

# Balanced Direct Stream profile.
# - 40 streams is the normal high-throughput target.
# - The planner may rise only as far as 64 when one complete wave needs it.
# - Small projects use fewer streams so we do not create dozens of tiny assets.
MIN_BALANCED_STREAMS = 40
DEFAULT_TURBO_WORKERS = 64
MAX_TURBO_WORKERS = 64
MIN_TARGET_CHUNK_BYTES = 64 * MIB
MAX_BALANCED_CHUNK_BYTES = CHUNK_SIZE_BYTES  # 1900 MiB; safely below GitHub's 2 GiB limit.


def _ceil_div(value: int, divisor: int) -> int:
    value = int(value)
    divisor = max(1, int(divisor))
    return (value + divisor - 1) // divisor


def choose_upload_plan(total_size: int, requested_workers: int = DEFAULT_TURBO_WORKERS) -> dict:
    """Choose a tail-resistant upload plan with complete, equal-sized waves.

    The planner prefers 40 concurrent uploads once a project is large enough to
    benefit from them. It raises concurrency only when the 1900 MiB per-asset
    ceiling requires more streams, up to 64. For larger projects it creates an
    integer number of complete waves (for example 40+40 or 54+54) so a tiny
    final wave such as 40+2 is not created by the planner.

    Small projects stay below 40 streams until they reach roughly 2.5 GiB; this
    avoids turning a few hundred MiB into dozens of tiny GitHub assets.
    """
    total_size = max(0, int(total_size))
    worker_cap = max(1, min(int(requested_workers or 1), MAX_TURBO_WORKERS))

    if total_size <= 0:
        return {
            "chunk_size": MAX_BALANCED_CHUNK_BYTES,
            "chunk_count": 0,
            "workers": 1,
            "waves": 0,
        }

    # Explicit callers that request fewer than 40 workers still get balanced
    # full waves at their requested concurrency.
    baseline = min(MIN_BALANCED_STREAMS, worker_cap)

    # Tiny/small projects: target about 64 MiB per asset and use only as many
    # streams as are useful. At ~2.5 GiB this naturally reaches 40 streams.
    small_threshold = MIN_BALANCED_STREAMS * MIN_TARGET_CHUNK_BYTES
    if worker_cap >= MIN_BALANCED_STREAMS and total_size < small_threshold:
        chunk_count = max(1, min(worker_cap, _ceil_div(total_size, MIN_TARGET_CHUNK_BYTES)))
        chunk_size = _ceil_div(total_size, chunk_count)
        return {
            "chunk_size": chunk_size,
            "chunk_count": chunk_count,
            "workers": chunk_count,
            "waves": 1,
        }

    max_waves = max(1, MAX_DATA_ASSETS // max(1, baseline))
    for waves in range(1, max_waves + 1):
        required_streams = _ceil_div(
            total_size,
            waves * MAX_BALANCED_CHUNK_BYTES,
        )
        streams = max(baseline, required_streams)
        if streams > worker_cap:
            continue

        chunk_count = streams * waves
        if chunk_count > MAX_DATA_ASSETS:
            break

        # No MiB rounding here: exact byte sizing keeps the requested chunk
        # count intact and guarantees that every chunk remains <= 1900 MiB.
        chunk_size = _ceil_div(total_size, chunk_count)
        actual_count = _ceil_div(total_size, chunk_size)
        if actual_count != chunk_count:
            # This is only realistically possible for extremely tiny integer
            # inputs; production game sizes are many orders of magnitude larger.
            continue
        if chunk_size > MAX_BALANCED_CHUNK_BYTES:
            continue

        return {
            "chunk_size": chunk_size,
            "chunk_count": chunk_count,
            "workers": streams,
            "waves": waves,
        }

    required = _ceil_div(total_size, MAX_BALANCED_CHUNK_BYTES)
    raise ValueError(
        "Project is too large for one GitHub Release with the balanced upload "
        f"profile: needs at least {required} data assets; max is {MAX_DATA_ASSETS}."
    )


def choose_upload_chunk_size(total_size: int, requested_workers: int = DEFAULT_TURBO_WORKERS) -> int:
    """Compatibility wrapper returning the balanced plan's chunk size."""
    return int(choose_upload_plan(total_size, requested_workers)["chunk_size"])


def effective_worker_count(
    chunk_size: int,
    requested_workers: int,
    free_temp_bytes: int | None = None,
) -> int:
    """Direct-stream uploads need no chunk scratch space; only cap concurrency."""
    del chunk_size, free_temp_bytes
    return max(1, min(int(requested_workers or 1), MAX_TURBO_WORKERS))


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
                "User-Agent": "Drowned-Distribution-Suite/0.9-balanced64",
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

    def _handle_failed_response(self, response, attempt: int):
        if self._secondary_limited(response):
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else min(60, 5 * (2 ** attempt))
            self._set_global_backoff(wait)
            return NetworkError(f"GitHub secondary rate limit: HTTP {response.status_code}"), attempt < 4

        if response.status_code in (500, 502, 503, 504) and attempt < 4:
            wait = min(30, 2 ** attempt)
            self._set_global_backoff(wait)
            return NetworkError(f"GitHub upload HTTP {response.status_code}"), True

        message = self.client._permission_help(response.status_code, response.text)
        if response.status_code in (401, 403):
            raise AuthenticationError(message)
        raise NetworkError(f"asset upload: {message}")

    def _upload_url(self):
        return (
            f"{GITHUB_UPLOADS}/repos/{self.client.owner}/{self.client.repo}"
            f"/releases/{self.release_id}/assets"
        )

    def upload_stream(
        self,
        name: str,
        total: int,
        reader_factory,
        progress=None,
        content_type: str = "application/octet-stream",
    ):
        """Upload from a fresh logical reader on every retry, returning asset + SHA."""
        total = max(0, int(total))
        last_error = None
        for attempt in range(5):
            self._wait_for_start_slot()
            reader = reader_factory()
            if progress:
                progress(0, total)
            try:
                response = self._session().post(
                    self._upload_url(),
                    params={"name": name},
                    headers={"Content-Type": content_type, "Content-Length": str(total)},
                    data=reader,
                    timeout=(30, 12 * 60 * 60),
                )
            except requests.RequestException as exc:
                last_error = exc
                reader.close()
                if attempt == 4:
                    raise NetworkError(f"asset upload network error: {exc}") from exc
                wait = min(30, 2 ** attempt)
                self._set_global_backoff(wait)
                continue

            try:
                if response.ok:
                    if int(getattr(reader, "sent", 0)) != total:
                        raise NetworkError(
                            f"asset upload ended early: sent {getattr(reader, 'sent', 0)} of {total} bytes"
                        )
                    return response.json(), str(reader.sha256)

                last_error, retry = self._handle_failed_response(response, attempt)
                if retry:
                    continue
            finally:
                reader.close()

        if last_error:
            raise last_error
        raise NetworkError("asset upload failed")

    def upload(self, name: str, path: Path, progress=None, content_type: str = "application/octet-stream"):
        """Compatibility uploader for callers that still have a real file."""
        path = Path(path)
        total = path.stat().st_size

        class Reader:
            def __init__(self, fp):
                self.fp = fp
                self.sent = 0

            @property
            def sha256(self):
                return ""

            def read(self, n=-1):
                block = self.fp.read(n)
                if block:
                    self.sent += len(block)
                    if progress:
                        progress(self.sent, total)
                return block

            def close(self):
                self.fp.close()

            def __getattr__(self, attr):
                return getattr(self.fp, attr)

        payload, _ = self.upload_stream(
            name,
            total,
            reader_factory=lambda: Reader(path.open("rb")),
            progress=None,
            content_type=content_type,
        )
        return payload
