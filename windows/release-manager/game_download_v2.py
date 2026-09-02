from __future__ import annotations

import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

import game_prepare as base


MIB = 1024 * 1024
GIB = 1024 * MIB
NETWORK_BLOCK = 4 * MIB
SEGMENT_BYTES = 64 * MIB
ASSEMBLE_BLOCK = 8 * MIB
MAX_RETRIES = 5
USER_AGENT = "Drowned-Release-Manager/0.13"


class DownloadRateMeter:
    """Measures only bytes transferred during the current run.

    Resume bytes are deliberately excluded from the average-speed numerator so
    a resumed job cannot show an impossible multi-gigabyte/second average.
    """

    def __init__(self, start_value: int = 0, window: float = 10.0):
        self.start_value = max(0, int(start_value))
        self.window = float(window)
        self.started = time.monotonic()
        self.samples: list[tuple[float, int]] = []

    def update(self, total_done: int) -> tuple[float, float, float]:
        now = time.monotonic()
        total_done = max(0, int(total_done))
        self.samples.append((now, total_done))
        cutoff = now - self.window
        while len(self.samples) > 2 and self.samples[0][0] < cutoff:
            self.samples.pop(0)

        if len(self.samples) > 1:
            dt = max(0.001, self.samples[-1][0] - self.samples[0][0])
            instant = max(0.0, (self.samples[-1][1] - self.samples[0][1]) / dt)
        else:
            instant = 0.0

        elapsed = max(0.001, now - self.started)
        average = max(0.0, (total_done - self.start_value) / elapsed)
        return instant, average, elapsed


def recommended_connections(size: int, requested: int = 0) -> int:
    requested = max(0, int(requested))
    if requested:
        return min(requested, 32)
    size = max(0, int(size))
    if size >= 4 * GIB:
        return 16
    if size >= 1 * GIB:
        return 12
    if size >= 256 * MIB:
        return 8
    return 4


def _segment_dir(state_dir: Path, probe: base.URLProbe) -> Path:
    return state_dir / f"{base._slug(probe.filename)}.segments"


def _segment_path(segment_dir: Path, index: int) -> Path:
    return segment_dir / f"{index:06d}.part"


class ProgressiveParallelDownloader(base.ParallelDownloader):
    """Range downloader tuned for fast residential gigabit connections.

    Unlike the previous implementation, the visible ``.part`` file is never
    pre-sized to the final archive size. Each Range request writes to a small
    real segment file first. Completed segments are appended to the visible
    ``.part`` in order and immediately deleted, so the visible file grows only
    with data that has actually arrived. The only temporary duplication is one
    small segment while it is being appended.
    """

    def _emit_download(
        self,
        done: int,
        total: int,
        meter: DownloadRateMeter,
        detail: str,
        connections: int,
        active_connections: int,
        file_done: int,
        file_total: int,
    ):
        now = time.monotonic()
        if now - self._last_emit < 0.20 and done < total:
            return
        self._last_emit = now
        speed, avg, elapsed = meter.update(done)
        remaining = max(0, total - done) if total else 0
        eta = remaining / speed if speed > 0 and total else None
        self.telemetry(
            {
                "phase": "download",
                "done": int(done),
                "total": int(total),
                "progress": (done / total) if total else 0.0,
                "speed": speed,
                "average_speed": avg,
                "elapsed": elapsed,
                "eta": eta,
                "detail": detail,
                "disk_free": base._disk_free(self.target_dir),
                "connections": int(connections),
                "active_connections": int(active_connections),
                "file_done": int(file_done),
                "file_total": int(file_total),
            }
        )

    def _progressive_state_path(self, probe: base.URLProbe) -> Path:
        return self._state_path(probe)

    @staticmethod
    def _identity_matches(state: dict, probe: base.URLProbe) -> bool:
        if state.get("mode") != "progressive-v2":
            return False
        if state.get("url") != probe.final_url:
            return False
        if int(state.get("size") or 0) != probe.size:
            return False
        if probe.etag and state.get("etag") != probe.etag:
            return False
        if not probe.etag and probe.last_modified and state.get("last_modified") != probe.last_modified:
            return False
        return int(state.get("segment_bytes") or 0) == SEGMENT_BYTES

    def _write_progressive_state(self, probe: base.URLProbe, assembled_bytes: int, force: bool = False):
        now = time.monotonic()
        if not force and now - self._last_state_save < 1.5:
            return
        self._last_state_save = now
        payload = {
            "mode": "progressive-v2",
            "url": probe.final_url,
            "size": probe.size,
            "etag": probe.etag,
            "last_modified": probe.last_modified,
            "segment_bytes": SEGMENT_BYTES,
            "assembled_bytes": int(assembled_bytes),
            "updated_at": time.time(),
        }
        path = self._progressive_state_path(probe)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _prepare_resume(
        self,
        probe: base.URLProbe,
        part: Path,
        segment_dir: Path,
    ) -> int:
        state_path = self._progressive_state_path(probe)
        state = None
        if state_path.exists():
            try:
                candidate = json.loads(state_path.read_text(encoding="utf-8"))
                if self._identity_matches(candidate, probe):
                    state = candidate
            except Exception:
                state = None

        if state is None:
            # Old v11/v12 Range state used an already pre-sized sparse/random
            # access file. It cannot be safely resumed as a contiguous file.
            if part.exists() or segment_dir.exists() or state_path.exists():
                self.log("Eski indirme state'i progressive mod ile uyumsuz; indirme temiz olarak yeniden başlatılıyor.")
            part.unlink(missing_ok=True)
            shutil.rmtree(segment_dir, ignore_errors=True)
            state_path.unlink(missing_ok=True)
            segment_dir.mkdir(parents=True, exist_ok=True)
            self._write_progressive_state(probe, 0, force=True)
            return 0

        assembled = max(0, min(int(state.get("assembled_bytes") or 0), probe.size))
        if assembled % SEGMENT_BYTES and assembled != probe.size:
            # Only the final segment may end on a non-standard boundary.
            assembled -= assembled % SEGMENT_BYTES

        if part.exists():
            current = part.stat().st_size
            if current < assembled:
                # The state says bytes were committed but the file is shorter.
                # Reset rather than trusting corrupt resume metadata.
                part.unlink(missing_ok=True)
                shutil.rmtree(segment_dir, ignore_errors=True)
                segment_dir.mkdir(parents=True, exist_ok=True)
                self._write_progressive_state(probe, 0, force=True)
                return 0
            if current != assembled:
                with open(part, "r+b") as handle:
                    handle.truncate(assembled)
        elif assembled:
            # State without the assembled file is not resumable.
            shutil.rmtree(segment_dir, ignore_errors=True)
            segment_dir.mkdir(parents=True, exist_ok=True)
            self._write_progressive_state(probe, 0, force=True)
            return 0

        segment_dir.mkdir(parents=True, exist_ok=True)
        completed_before = assembled // SEGMENT_BYTES
        for stale in segment_dir.glob("*.part"):
            try:
                index = int(stale.stem)
            except ValueError:
                stale.unlink(missing_ok=True)
                continue
            if index < completed_before:
                stale.unlink(missing_ok=True)
        return assembled

    def _download_one(self, probe: base.URLProbe, base_done: int, overall_total: int) -> Path:
        final = self.target_dir / probe.filename
        part = final.with_name(final.name + ".part")
        if final.exists() and probe.size and final.stat().st_size == probe.size:
            self.log(f"Zaten tamamlanmış dosya kullanılıyor: {final.name}")
            return final

        if probe.size <= 0 or not probe.ranges:
            return self._single_stream_fast(probe, final, part, base_done, overall_total)

        connections = recommended_connections(probe.size, self.connections)
        segment_dir = _segment_dir(self.state_dir, probe)
        assembled_bytes = self._prepare_resume(probe, part, segment_dir)

        segments: list[dict] = []
        index = 0
        start = 0
        while start < probe.size:
            end = min(probe.size - 1, start + SEGMENT_BYTES - 1)
            segments.append({"index": index, "start": start, "end": end})
            index += 1
            start = end + 1

        assembly_index = assembled_bytes // SEGMENT_BYTES
        if assembled_bytes == probe.size:
            assembly_index = len(segments)

        # Actual bytes currently present on disk: committed .part prefix plus
        # unassembled segment files. No preallocation is counted.
        file_done = assembled_bytes
        for segment in segments[assembly_index:]:
            seg_path = _segment_path(segment_dir, segment["index"])
            if not seg_path.exists():
                continue
            length = segment["end"] - segment["start"] + 1
            size = min(seg_path.stat().st_size, length)
            if seg_path.stat().st_size != size:
                with open(seg_path, "r+b") as handle:
                    handle.truncate(size)
            file_done += size

        if file_done:
            self.log(
                f"Yarım kalan gerçek veri bulundu: {probe.filename} • "
                f"{file_done} / {probe.size} byte devam edilecek."
            )

        total_for_stats = overall_total or probe.size
        meter = DownloadRateMeter(start_value=base_done + file_done)
        active_workers = 0
        progress_lock = self._lock

        self._emit_download(
            base_done + file_done,
            total_for_stats,
            meter,
            f"{probe.filename} • gerçek indirilen veri",
            connections,
            0,
            file_done,
            probe.size,
        )

        def try_assemble_locked():
            nonlocal assembled_bytes, assembly_index
            while assembly_index < len(segments):
                segment = segments[assembly_index]
                seg_path = _segment_path(segment_dir, segment["index"])
                length = segment["end"] - segment["start"] + 1
                if not seg_path.exists() or seg_path.stat().st_size != length:
                    break
                part.parent.mkdir(parents=True, exist_ok=True)
                with open(seg_path, "rb") as src, open(part, "ab") as dst:
                    shutil.copyfileobj(src, dst, length=ASSEMBLE_BLOCK)
                    dst.flush()
                assembled_bytes += length
                assembly_index += 1
                self._write_progressive_state(probe, assembled_bytes, force=True)
                seg_path.unlink(missing_ok=True)

        with progress_lock:
            try_assemble_locked()

        def worker(segment: dict):
            nonlocal file_done, active_workers
            seg_path = _segment_path(segment_dir, segment["index"])
            length = segment["end"] - segment["start"] + 1
            existing = seg_path.stat().st_size if seg_path.exists() else 0
            if existing > length:
                with open(seg_path, "r+b") as handle:
                    handle.truncate(length)
                existing = length
            if existing == length:
                with progress_lock:
                    try_assemble_locked()
                return

            attempts = 0
            while existing < length:
                if self.cancelled():
                    raise RuntimeError("İşlem iptal edildi.")
                attempts += 1
                current = segment["start"] + existing
                headers = {
                    "User-Agent": USER_AGENT,
                    "Accept-Encoding": "identity",
                    "Connection": "keep-alive",
                    "Range": f"bytes={current}-{segment['end']}",
                }
                try:
                    with progress_lock:
                        active_workers += 1
                    with requests.get(
                        probe.final_url,
                        headers=headers,
                        stream=True,
                        allow_redirects=True,
                        timeout=(20, 120),
                    ) as response:
                        if response.status_code != 206:
                            raise RuntimeError(
                                f"Sunucu paralel Range isteğini kabul etmedi (HTTP {response.status_code})."
                            )
                        seg_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(seg_path, "ab", buffering=0) as out:
                            for block in response.iter_content(chunk_size=NETWORK_BLOCK):
                                if self.cancelled():
                                    raise RuntimeError("İşlem iptal edildi.")
                                if not block:
                                    continue
                                remaining = length - existing
                                if len(block) > remaining:
                                    block = block[:remaining]
                                out.write(block)
                                existing += len(block)
                                with progress_lock:
                                    file_done += len(block)
                                    self._write_progressive_state(probe, assembled_bytes)
                                    self._emit_download(
                                        base_done + file_done,
                                        total_for_stats,
                                        meter,
                                        f"{probe.filename} • gerçek indirilen veri",
                                        connections,
                                        active_workers,
                                        file_done,
                                        probe.size,
                                    )
                                if existing >= length:
                                    break
                    with progress_lock:
                        active_workers = max(0, active_workers - 1)
                    if existing == length:
                        break
                except Exception as exc:
                    with progress_lock:
                        active_workers = max(0, active_workers - 1)
                    existing = seg_path.stat().st_size if seg_path.exists() else 0
                    if attempts >= MAX_RETRIES:
                        raise
                    wait = min(12, 2 ** (attempts - 1))
                    self.log(
                        f"Segment {segment['index'] + 1}/{len(segments)} bağlantısı kesildi: {exc} • "
                        f"{wait} sn sonra devam edilecek ({attempts}/{MAX_RETRIES})."
                    )
                    time.sleep(wait)

            if existing != length:
                raise RuntimeError(
                    f"Segment tamamlanamadı: {segment['index'] + 1}/{len(segments)}"
                )
            with progress_lock:
                try_assemble_locked()

        pending = [segment for segment in segments[assembly_index:]]
        try:
            with ThreadPoolExecutor(
                max_workers=connections,
                thread_name_prefix="drowned-gigabit",
            ) as pool:
                futures = [pool.submit(worker, segment) for segment in pending]
                for future in as_completed(futures):
                    future.result()
        except Exception:
            with progress_lock:
                self._write_progressive_state(probe, assembled_bytes, force=True)
            raise

        with progress_lock:
            try_assemble_locked()
            self._write_progressive_state(probe, assembled_bytes, force=True)

        if assembled_bytes != probe.size:
            raise RuntimeError(
                f"İndirme tamamlanamadı: assembled {assembled_bytes}, beklenen {probe.size}. "
                "Gerçek indirilen parçalar resume için korunuyor."
            )
        if not part.exists() or part.stat().st_size != probe.size:
            raise RuntimeError("Birleştirilmiş .part boyutu beklenen dosya boyutuyla uyuşmuyor.")

        os.replace(part, final)
        self._progressive_state_path(probe).unlink(missing_ok=True)
        shutil.rmtree(segment_dir, ignore_errors=True)
        self._emit_download(
            base_done + probe.size,
            total_for_stats,
            meter,
            f"{probe.filename} • indirme tamamlandı",
            connections,
            0,
            probe.size,
            probe.size,
        )
        return final

    def _single_stream_fast(
        self,
        probe: base.URLProbe,
        final: Path,
        part: Path,
        base_done: int,
        overall_total: int,
    ) -> Path:
        attempts = 0
        total_for_stats = overall_total or probe.size
        initial = part.stat().st_size if part.exists() and probe.ranges else 0
        meter = DownloadRateMeter(start_value=base_done + initial)

        while True:
            attempts += 1
            existing = part.stat().st_size if part.exists() and probe.ranges else 0
            headers = {
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "identity",
                "Connection": "keep-alive",
            }
            mode = "wb"
            if existing:
                headers["Range"] = f"bytes={existing}-"
                mode = "ab"
            try:
                with requests.get(
                    probe.final_url,
                    headers=headers,
                    stream=True,
                    allow_redirects=True,
                    timeout=(20, 120),
                ) as response:
                    if response.status_code >= 400:
                        raise RuntimeError(f"İndirme başarısız: HTTP {response.status_code}")
                    if existing and response.status_code != 206:
                        existing = 0
                        mode = "wb"
                    done = existing
                    with open(part, mode) as out:
                        for block in response.iter_content(chunk_size=NETWORK_BLOCK):
                            if self.cancelled():
                                raise RuntimeError("İşlem iptal edildi.")
                            if not block:
                                continue
                            out.write(block)
                            done += len(block)
                            self._emit_download(
                                base_done + done,
                                total_for_stats,
                                meter,
                                f"{probe.filename} • gerçek indirilen veri",
                                1,
                                1,
                                done,
                                probe.size,
                            )
                if probe.size and done != probe.size:
                    raise RuntimeError(
                        f"Dosya boyutu uyuşmuyor: beklenen {probe.size}, gelen {done}"
                    )
                os.replace(part, final)
                return final
            except Exception as exc:
                if attempts >= MAX_RETRIES:
                    raise
                wait = min(12, 2 ** (attempts - 1))
                self.log(
                    f"İndirme bağlantısı kesildi: {exc} • {wait} sn sonra devam edilecek "
                    f"({attempts}/{MAX_RETRIES})."
                )
                time.sleep(wait)
