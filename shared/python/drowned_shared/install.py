from __future__ import annotations

import hashlib
import json
import math
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

from .errors import DiskSpaceError, DownloadCancelled, HashMismatchError
from .util import atomic_json, safe_relative_path, sha256_file
from .validation import validate_manifest

BLOCK_SIZE = 4 * 1024 * 1024
DEFAULT_DOWNLOAD_WORKERS = 16
RANGE_MIN_SIZE = 8 * 1024 * 1024


class DownloadControl:
    """Thread-safe pause/resume/cancel controller used by the Launcher."""

    def __init__(self):
        self._resume_event = threading.Event()
        self._resume_event.set()
        self._cancel_event = threading.Event()

    def pause(self) -> None:
        if not self._cancel_event.is_set():
            self._resume_event.clear()

    def resume(self) -> None:
        self._resume_event.set()

    def cancel(self) -> None:
        self._cancel_event.set()
        self._resume_event.set()

    @property
    def paused(self) -> bool:
        return not self._resume_event.is_set() and not self._cancel_event.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def checkpoint(self) -> None:
        while not self._resume_event.wait(0.20):
            if self._cancel_event.is_set():
                raise DownloadCancelled("İndirme iptal edildi")
        if self._cancel_event.is_set():
            raise DownloadCancelled("İndirme iptal edildi")


def fetch_json(url: str) -> dict:
    r = requests.get(url, timeout=60, headers={"User-Agent": "Drowned-Launcher/0.8"})
    r.raise_for_status()
    return r.json()


def _state_path(root: Path) -> Path:
    return root / ".drowned" / "state.json"


def _load_state(root: Path, tag: str) -> dict:
    path = _state_path(root)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if state.get("tag") != tag:
        state = {"tag": tag, "completed_chunks": [], "verified": False}
    state.setdefault("completed_chunks", [])
    state.setdefault("verified", False)
    return state


def _save_state(root: Path, state: dict) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, state)


def _checkpoint(control: DownloadControl | None, cancelled) -> None:
    if cancelled():
        raise DownloadCancelled("İndirme iptal edildi")
    if control is not None:
        control.checkpoint()


def find_invalid_files(
    manifest: dict,
    root: Path,
    progress=lambda done, total: None,
    cancelled=lambda: False,
    control: DownloadControl | None = None,
) -> list[str]:
    """Return missing, wrong-sized or SHA-256-invalid manifest file paths."""
    validate_manifest(manifest)
    root = Path(root)
    files = manifest["files"]
    total = sum(int(f["size"]) for f in files)
    checked = 0
    invalid: list[str] = []

    for entry in files:
        _checkpoint(control, cancelled)
        rel = entry["path"]
        path = root / safe_relative_path(rel)
        expected_size = int(entry["size"])
        if not path.is_file() or path.stat().st_size != expected_size:
            invalid.append(rel)
            checked += expected_size
            progress(min(checked, total), total)
            continue

        digest = hashlib.sha256()
        with path.open("rb") as fp:
            while True:
                _checkpoint(control, cancelled)
                block = fp.read(BLOCK_SIZE)
                if not block:
                    break
                digest.update(block)
                checked += len(block)
                progress(min(checked, total), total)
        if digest.hexdigest().lower() != str(entry["sha256"]).lower():
            invalid.append(rel)

    return invalid


def chunks_for_files(manifest: dict, file_paths: list[str] | set[str]) -> set[str]:
    wanted = set(file_paths)
    result: set[str] = set()
    for chunk in manifest["chunks"]:
        if any(segment["file"] in wanted for segment in chunk["segments"]):
            result.add(chunk["name"])
    return result


def _prepare_manifest_files(manifest: dict, root: Path, only_files: set[str] | None = None) -> None:
    for entry in manifest["files"]:
        rel = entry["path"]
        if only_files is not None and rel not in only_files:
            continue
        path = root / safe_relative_path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        expected = int(entry["size"])
        if not path.exists():
            with path.open("wb") as out:
                out.truncate(expected)
        elif path.stat().st_size != expected:
            with path.open("r+b") as out:
                out.truncate(expected)


def _chunk_url(manifest: dict, chunk: dict) -> str:
    release = manifest["release"]
    return (
        f"https://github.com/{release['owner']}/{release['repo']}"
        f"/releases/download/{release['tag']}/{chunk['name']}"
    )


def _new_session(pool_size: int = 4) -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=0)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "Drowned-Launcher/0.8", "Accept-Encoding": "identity"})
    return session


def _split_ranges(size: int, parts: int) -> list[tuple[int, int]]:
    size = int(size)
    if size <= 0:
        return []
    parts = max(1, min(int(parts), size))
    step = math.ceil(size / parts)
    ranges = []
    start = 0
    while start < size:
        end = min(size - 1, start + step - 1)
        ranges.append((start, end))
        start = end + 1
    return ranges


def _write_chunk_slice(
    chunk: dict,
    root: Path,
    chunk_offset: int,
    data: bytes | memoryview,
    file_locks: dict[str, threading.Lock],
) -> None:
    """Write a byte slice from a chunk into the manifest-mapped final files."""
    if not data:
        return
    view = memoryview(data)
    slice_start = int(chunk_offset)
    slice_end = slice_start + len(view)

    for segment in chunk["segments"]:
        seg_start = int(segment["chunk_offset"])
        seg_end = seg_start + int(segment["length"])
        overlap_start = max(slice_start, seg_start)
        overlap_end = min(slice_end, seg_end)
        if overlap_start >= overlap_end:
            continue

        src_start = overlap_start - slice_start
        src_end = overlap_end - slice_start
        file_offset = int(segment["file_offset"]) + (overlap_start - seg_start)
        rel = str(segment["file"])
        target = root / safe_relative_path(rel)
        lock = file_locks.setdefault(rel, threading.Lock())
        with lock:
            with target.open("r+b") as fp:
                fp.seek(file_offset)
                fp.write(view[src_start:src_end])


def _hash_reconstructed_chunk(chunk: dict, root: Path, control, cancelled) -> str:
    digest = hashlib.sha256()
    for segment in sorted(chunk["segments"], key=lambda s: int(s["chunk_offset"])):
        _checkpoint(control, cancelled)
        target = root / safe_relative_path(segment["file"])
        remaining = int(segment["length"])
        with target.open("rb") as fp:
            fp.seek(int(segment["file_offset"]))
            while remaining:
                _checkpoint(control, cancelled)
                block = fp.read(min(BLOCK_SIZE, remaining))
                if not block:
                    raise HashMismatchError(chunk["name"])
                digest.update(block)
                remaining -= len(block)
    return digest.hexdigest()


def _probe_range_support(url: str, control, cancelled) -> bool:
    _checkpoint(control, cancelled)
    try:
        with _new_session(2) as session:
            response = session.get(
                url,
                headers={"Range": "bytes=0-0", "Cache-Control": "no-cache"},
                stream=True,
                allow_redirects=True,
                timeout=(15, 30),
            )
            supported = response.status_code == 206 and bool(response.headers.get("Content-Range"))
            response.close()
            return supported
    except Exception:
        return False


def _download_range(
    url: str,
    chunk: dict,
    root: Path,
    start: int,
    end: int,
    unit_key: str,
    report_absolute,
    file_locks,
    control,
    cancelled,
) -> None:
    expected = end - start + 1
    for attempt in range(1, 4):
        _checkpoint(control, cancelled)
        received = 0
        report_absolute(unit_key, 0)
        try:
            with _new_session(2) as session:
                with session.get(
                    url,
                    headers={"Range": f"bytes={start}-{end}"},
                    stream=True,
                    allow_redirects=True,
                    timeout=(20, 180),
                ) as response:
                    if response.status_code != 206:
                        raise RuntimeError(f"HTTP Range desteklenmedi ({response.status_code})")
                    for block in response.iter_content(BLOCK_SIZE):
                        _checkpoint(control, cancelled)
                        if not block:
                            continue
                        if received + len(block) > expected:
                            block = block[: expected - received]
                        _write_chunk_slice(chunk, root, start + received, block, file_locks)
                        received += len(block)
                        report_absolute(unit_key, received)
                        if received >= expected:
                            break
            if received != expected:
                raise RuntimeError(f"Eksik range: {received}/{expected}")
            return
        except DownloadCancelled:
            raise
        except Exception:
            if attempt == 3:
                raise
            time.sleep(0.4 * attempt)


def _download_chunk_single(
    url: str,
    chunk: dict,
    root: Path,
    unit_key: str,
    report_absolute,
    file_locks,
    control,
    cancelled,
) -> None:
    expected = int(chunk["size"])
    for attempt in range(1, 4):
        _checkpoint(control, cancelled)
        digest = hashlib.sha256()
        received = 0
        report_absolute(unit_key, 0)
        try:
            with _new_session(2) as session:
                with session.get(url, stream=True, allow_redirects=True, timeout=(20, 240)) as response:
                    response.raise_for_status()
                    for block in response.iter_content(BLOCK_SIZE):
                        _checkpoint(control, cancelled)
                        if not block:
                            continue
                        digest.update(block)
                        _write_chunk_slice(chunk, root, received, block, file_locks)
                        received += len(block)
                        report_absolute(unit_key, min(received, expected))
            if received != expected:
                raise RuntimeError(f"Eksik chunk: {received}/{expected}")
            if digest.hexdigest().lower() != str(chunk["sha256"]).lower():
                raise HashMismatchError(chunk["name"])
            return
        except DownloadCancelled:
            raise
        except Exception:
            if attempt == 3:
                raise
            time.sleep(0.5 * attempt)


def _download_one_chunk(
    manifest: dict,
    chunk: dict,
    root: Path,
    ranges_per_chunk: int,
    report_absolute,
    file_locks,
    control,
    cancelled,
) -> None:
    url = _chunk_url(manifest, chunk)
    size = int(chunk["size"])
    ranges_per_chunk = max(1, int(ranges_per_chunk))

    # A 0-0 request both warms GitHub's redirect/CDN path and tells us whether
    # this asset supports byte ranges. Old one-chunk releases can therefore use
    # multiple network streams just like newer multi-chunk releases.
    use_ranges = (
        ranges_per_chunk > 1
        and size >= RANGE_MIN_SIZE
        and _probe_range_support(url, control, cancelled)
    )

    if not use_ranges:
        _download_chunk_single(
            url, chunk, root, f"{chunk['name']}:full", report_absolute,
            file_locks, control, cancelled,
        )
        return

    ranges = _split_ranges(size, ranges_per_chunk)
    with ThreadPoolExecutor(max_workers=len(ranges), thread_name_prefix="drowned-range") as executor:
        futures = []
        for index, (start, end) in enumerate(ranges):
            key = f"{chunk['name']}:r{index}"
            futures.append(
                executor.submit(
                    _download_range,
                    url,
                    chunk,
                    root,
                    start,
                    end,
                    key,
                    report_absolute,
                    file_locks,
                    control,
                    cancelled,
                )
            )
        for future in as_completed(futures):
            future.result()

    got = _hash_reconstructed_chunk(chunk, root, control, cancelled)
    if got.lower() != str(chunk["sha256"]).lower():
        raise HashMismatchError(chunk["name"])


def _download_chunks(
    manifest: dict,
    root: Path,
    chunk_names: set[str],
    progress=lambda done, total: None,
    log=print,
    cancelled=lambda: False,
    *,
    workers: int = DEFAULT_DOWNLOAD_WORKERS,
    control: DownloadControl | None = None,
    on_chunk_complete=None,
) -> int:
    """Download selected chunks with up to *workers* concurrent HTTP streams."""
    if not chunk_names:
        return 0

    selected = [c for c in manifest["chunks"] if c["name"] in chunk_names]
    total = sum(int(c["size"]) for c in selected)
    workers = max(1, min(int(workers), DEFAULT_DOWNLOAD_WORKERS))
    outer_workers = min(workers, max(1, len(selected)))
    ranges_per_chunk = max(1, workers // outer_workers)

    file_locks: dict[str, threading.Lock] = {}
    progress_lock = threading.Lock()
    state_lock = threading.Lock()
    unit_progress: dict[str, int] = {}
    completed_count = 0
    last_emit = [0.0]

    def report_absolute(key: str, value: int):
        with progress_lock:
            unit_progress[key] = max(0, int(value))
            now = time.monotonic()
            if now - last_emit[0] >= 0.10:
                last_emit[0] = now
                progress(min(sum(unit_progress.values()), total), total)

    def worker(chunk: dict):
        _checkpoint(control, cancelled)
        _download_one_chunk(
            manifest, chunk, root, ranges_per_chunk,
            report_absolute, file_locks, control, cancelled,
        )
        if on_chunk_complete is not None:
            with state_lock:
                on_chunk_complete(chunk["name"])
        log(f"Doğrulandı: {chunk['name']}")
        return chunk["name"]

    log(
        f"Turbo indirme: {workers} HTTP stream • {len(selected)} chunk • "
        f"chunk başına en fazla {ranges_per_chunk} range"
    )

    executor = ThreadPoolExecutor(max_workers=outer_workers, thread_name_prefix="drowned-chunk")
    futures = [executor.submit(worker, chunk) for chunk in selected]
    try:
        for future in as_completed(futures):
            future.result()
            completed_count += 1
    except Exception:
        if control is not None:
            control.cancel()
        for future in futures:
            future.cancel()
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    progress(total, total)
    return completed_count


def repair_manifest(
    manifest: dict,
    root: Path,
    progress=lambda done, total: None,
    log=print,
    cancelled=lambda: False,
    *,
    workers: int = DEFAULT_DOWNLOAD_WORKERS,
    control: DownloadControl | None = None,
) -> dict:
    """Verify an installation and redownload only chunks touching invalid files."""
    validate_manifest(manifest)
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Kurulum klasörü bulunamadı: {root}")

    log("Dosyalar SHA-256 ile doğrulanıyor…")
    invalid = find_invalid_files(manifest, root, progress, cancelled, control)
    if not invalid:
        tag = manifest["release"]["tag"]
        state = _load_state(root, tag)
        state["verified"] = True
        state["completed_chunks"] = [c["name"] for c in manifest["chunks"]]
        _save_state(root, state)
        log("Tüm dosyalar sağlam.")
        return {"invalid_files": [], "repaired_files": [], "downloaded_chunks": 0}

    log(f"{len(invalid)} eksik/bozuk dosya bulundu.")
    for rel in invalid[:50]:
        log(f"  • {rel}")
    if len(invalid) > 50:
        log(f"  … ve {len(invalid) - 50} dosya daha")

    required_chunks = chunks_for_files(manifest, invalid)
    if not required_chunks:
        raise HashMismatchError("Bozuk dosyaları onaracak chunk bulunamadı")

    invalid_set = set(invalid)
    _prepare_manifest_files(manifest, root, invalid_set)

    tag = manifest["release"]["tag"]
    state = _load_state(root, tag)
    completed = set(state.get("completed_chunks", []))
    completed.difference_update(required_chunks)
    state["completed_chunks"] = sorted(completed)
    state["verified"] = False
    _save_state(root, state)
    state_lock = threading.Lock()

    def mark_complete(name: str):
        with state_lock:
            completed.add(name)
            state["completed_chunks"] = sorted(completed)
            state["verified"] = False
            _save_state(root, state)

    log(f"Yalnız gerekli {len(required_chunks)} chunk yeniden indirilecek.")
    downloaded = _download_chunks(
        manifest, root, required_chunks, progress, log, cancelled,
        workers=workers, control=control, on_chunk_complete=mark_complete,
    )

    log("Onarılan dosyalar tekrar doğrulanıyor…")
    still_invalid = []
    by_path = {f["path"]: f for f in manifest["files"]}
    for rel in invalid:
        _checkpoint(control, cancelled)
        entry = by_path[rel]
        path = root / safe_relative_path(rel)
        if (
            not path.is_file()
            or path.stat().st_size != int(entry["size"])
            or sha256_file(path).lower() != str(entry["sha256"]).lower()
        ):
            still_invalid.append(rel)
    if still_invalid:
        raise HashMismatchError(", ".join(still_invalid[:5]))

    state["completed_chunks"] = sorted(completed)
    state["verified"] = True
    _save_state(root, state)
    log(f"Onarım tamamlandı: {len(invalid)} dosya, {downloaded} chunk.")
    return {
        "invalid_files": invalid,
        "repaired_files": invalid,
        "downloaded_chunks": downloaded,
    }


def install_manifest(
    manifest: dict,
    root: Path,
    progress=lambda done, total: None,
    log=print,
    cancelled=lambda: False,
    *,
    workers: int = DEFAULT_DOWNLOAD_WORKERS,
    control: DownloadControl | None = None,
):
    validate_manifest(manifest)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    required_growth = 0
    for entry in manifest["files"]:
        path = root / safe_relative_path(entry["path"])
        existing = path.stat().st_size if path.exists() and path.is_file() else 0
        required_growth += max(0, int(entry["size"]) - existing)
    free = shutil.disk_usage(root).free
    if free < required_growth:
        raise DiskSpaceError(f"requires {required_growth} bytes; {free} free")

    tag = manifest["release"]["tag"]
    state = _load_state(root, tag)
    completed = set(state.get("completed_chunks", []))
    _prepare_manifest_files(manifest, root)
    state_lock = threading.Lock()

    def mark_complete(name: str):
        with state_lock:
            completed.add(name)
            state["completed_chunks"] = sorted(completed)
            state["verified"] = False
            _save_state(root, state)

    pending = {c["name"] for c in manifest["chunks"] if c["name"] not in completed}
    if pending:
        downloaded = _download_chunks(
            manifest, root, pending, progress, log, cancelled,
            workers=workers, control=control, on_chunk_complete=mark_complete,
        )
        log(f"{downloaded} chunk indirildi.")

    # Completed state can become stale if files were deleted/modified. Verify
    # after every install/resume and repair only the affected chunks.
    result = repair_manifest(
        manifest, root, progress, log, cancelled,
        workers=workers, control=control,
    )
    state = _load_state(root, tag)
    state["completed_chunks"] = [c["name"] for c in manifest["chunks"]]
    state["verified"] = True
    _save_state(root, state)
    return result
