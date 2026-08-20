from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import SourceChangedError

READ_BLOCK_SIZE = 8 * 1024 * 1024


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    rel: str
    size: int
    mtime_ns: int


def _snapshot_file(root: Path, path: Path) -> SourceSnapshot:
    stat = path.stat()
    return SourceSnapshot(
        path=path,
        rel=path.relative_to(root).as_posix(),
        size=int(stat.st_size),
        mtime_ns=int(stat.st_mtime_ns),
    )


def plan_direct_stream(builder):
    """Build chunk segment metadata without creating temporary chunk files."""
    root = Path(builder.root).resolve()
    snapshots = [_snapshot_file(root, path) for path in builder.files]
    snapshot_map = {item.rel: item for item in snapshots}

    chunks: list[dict] = []
    index = 0
    chunk_size = int(builder.chunk_size)
    chunk_used = 0
    segments: list[dict] = []

    def finish_chunk():
        nonlocal index, chunk_used, segments
        if chunk_used <= 0:
            return
        index += 1
        chunks.append({
            "name": f"chunk-{index:06d}.bin",
            "size": int(chunk_used),
            "segments": segments,
        })
        chunk_used = 0
        segments = []

    for snap in snapshots:
        file_offset = 0
        while file_offset < snap.size:
            available = chunk_size - chunk_used
            take = min(available, snap.size - file_offset)
            segments.append({
                "file": snap.rel,
                "file_offset": int(file_offset),
                "chunk_offset": int(chunk_used),
                "length": int(take),
            })
            file_offset += take
            chunk_used += take
            if chunk_used == chunk_size:
                finish_chunk()

    finish_chunk()
    if len(chunks) != builder.chunk_count:
        raise RuntimeError(
            f"direct stream planner mismatch: planned {len(chunks)} chunks, "
            f"builder expected {builder.chunk_count}"
        )

    return {
        "total_size": int(builder.total_size),
        "snapshots": snapshots,
        "snapshot_map": snapshot_map,
        "chunks": chunks,
    }


def _validate_snapshot(snapshot: SourceSnapshot):
    stat = snapshot.path.stat()
    if int(stat.st_size) != snapshot.size or int(stat.st_mtime_ns) != snapshot.mtime_ns:
        raise SourceChangedError(f"source changed during publish: {snapshot.rel}")


def hash_source_files(
    snapshots: list[SourceSnapshot],
    cancelled: Callable[[], bool] = lambda: False,
) -> list[dict]:
    """Hash source files sequentially; intended to run in parallel with network upload."""
    result: list[dict] = []
    for snapshot in snapshots:
        if cancelled():
            raise RuntimeError("cancelled")
        _validate_snapshot(snapshot)
        digest = hashlib.sha256()
        with snapshot.path.open("rb") as handle:
            while True:
                if cancelled():
                    raise RuntimeError("cancelled")
                block = handle.read(READ_BLOCK_SIZE)
                if not block:
                    break
                digest.update(block)
        _validate_snapshot(snapshot)
        result.append({
            "path": snapshot.rel,
            "size": snapshot.size,
            "sha256": digest.hexdigest(),
        })
    return result


class DirectChunkReader:
    """File-like reader that materializes a logical chunk directly from source ranges."""

    def __init__(
        self,
        chunk: dict,
        snapshot_map: dict[str, SourceSnapshot],
        progress=None,
        cancelled: Callable[[], bool] = lambda: False,
    ):
        self.chunk = chunk
        self.snapshot_map = snapshot_map
        self.progress = progress
        self.cancelled = cancelled
        self.total = int(chunk.get("size") or 0)
        self.sent = 0
        self._digest = hashlib.sha256()
        self._segment_index = 0
        self._segment_position = 0
        self._handle = None
        self._active_snapshot: SourceSnapshot | None = None

    @property
    def sha256(self) -> str:
        return self._digest.hexdigest()

    def __len__(self):
        return self.total

    def readable(self):
        return True

    def tell(self):
        return self.sent

    def _close_handle(self, validate: bool = True):
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        if validate and self._active_snapshot is not None:
            _validate_snapshot(self._active_snapshot)
        self._active_snapshot = None

    def close(self):
        self._close_handle(validate=False)

    def _open_current_segment(self):
        segments = self.chunk.get("segments") or []
        if self._segment_index >= len(segments):
            return False
        segment = segments[self._segment_index]
        rel = str(segment.get("file") or "")
        snapshot = self.snapshot_map.get(rel)
        if snapshot is None:
            raise SourceChangedError(f"source file disappeared during publish: {rel}")
        _validate_snapshot(snapshot)
        self._active_snapshot = snapshot
        self._handle = snapshot.path.open("rb")
        self._handle.seek(int(segment.get("file_offset") or 0) + self._segment_position)
        return True

    def read(self, n: int = -1):
        if self.cancelled():
            raise RuntimeError("cancelled")
        if self.sent >= self.total:
            self._close_handle()
            return b""
        if n is None or n < 0:
            n = min(READ_BLOCK_SIZE, self.total - self.sent)
        else:
            n = min(max(1, int(n)), self.total - self.sent)

        output = bytearray()
        segments = self.chunk.get("segments") or []
        while len(output) < n and self._segment_index < len(segments):
            if self.cancelled():
                raise RuntimeError("cancelled")
            segment = segments[self._segment_index]
            segment_length = int(segment.get("length") or 0)
            remaining = segment_length - self._segment_position
            if remaining <= 0:
                self._close_handle()
                self._segment_index += 1
                self._segment_position = 0
                continue
            if self._handle is None:
                self._open_current_segment()
            take = min(n - len(output), remaining)
            block = self._handle.read(take)
            if not block:
                raise SourceChangedError(
                    f"source changed during publish: {segment.get('file') or ''}"
                )
            output.extend(block)
            got = len(block)
            self._segment_position += got
            if self._segment_position >= segment_length:
                self._close_handle()
                self._segment_index += 1
                self._segment_position = 0

        block = bytes(output)
        if block:
            self.sent += len(block)
            self._digest.update(block)
            if self.progress:
                self.progress(self.sent, self.total)
        return block
