from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import zipfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

import requests

try:
    import psutil
except ImportError:  # packaged builds install it, but keep the module importable in minimal environments
    psutil = None


TelemetryCallback = Callable[[dict], None]
LogCallback = Callable[[str], None]
CancelCallback = Callable[[], bool]


ARCHIVE_RE = re.compile(r"\.(?:zip|7z|rar)$", re.I)
MULTIPART_RAR_RE = re.compile(r"\.part0*1\.rar$", re.I)
ARCHIVE_VOLUME_RE = re.compile(
    r"(?:\.part\d+\.rar$|\.r\d\d$|\.7z\.\d{3}$|\.zip\.\d{3}$|\.(?:rar|7z|zip)$)",
    re.I,
)
BAD_EXE_TOKENS = {
    "unins", "uninstall", "setup", "installer", "redist", "vcredist", "vc_redist",
    "crash", "reporter", "diagnostic", "benchmark", "config", "support", "repair",
    "easyanticheat", "eac", "battleye", "prereq", "prerequisite", "updater", "update",
}
GOOD_EXE_TOKENS = {"shipping", "win64", "game", "client"}


def _noop(*_args, **_kwargs):
    return None


def _safe_name(value: str, fallback: str = "download.bin") -> str:
    value = unquote(value or "").strip().replace("\\", "_").replace("/", "_")
    value = re.sub(r'[<>:"|?*\x00-\x1f]', "_", value).strip(" .")
    return value[:180] or fallback


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    return text[:80] or "game"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _disk_free(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


class RateMeter:
    def __init__(self, window: float = 12.0):
        self.window = window
        self.samples: deque[tuple[float, int]] = deque()
        self.started = time.monotonic()

    def update(self, total_done: int) -> tuple[float, float, float]:
        now = time.monotonic()
        self.samples.append((now, total_done))
        while len(self.samples) > 2 and now - self.samples[0][0] > self.window:
            self.samples.popleft()
        if len(self.samples) > 1:
            dt = max(0.001, self.samples[-1][0] - self.samples[0][0])
            speed = max(0.0, (self.samples[-1][1] - self.samples[0][1]) / dt)
        else:
            speed = 0.0
        elapsed = max(0.001, now - self.started)
        avg = max(0.0, total_done / elapsed)
        return speed, avg, elapsed


@dataclass
class URLProbe:
    url: str
    final_url: str
    filename: str
    size: int
    ranges: bool
    etag: str
    last_modified: str


@dataclass
class PreparedGame:
    title: str
    download_dir: str
    extraction_root: str
    game_root: str
    executable: str
    downloaded_files: list[str]
    archives: list[str]
    created_at: float
    user_confirmed: bool = False
    test_pid: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def probe_url(url: str, timeout: int = 45) -> URLProbe:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Yalnızca doğrudan HTTP/HTTPS URL'leri desteklenir.")
    headers = {"User-Agent": "Drowned-Release-Manager/0.11"}
    response = None
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout, headers=headers)
        if response.status_code >= 400 or response.status_code in {405, 501}:
            response.close()
            response = None
    except requests.RequestException:
        response = None

    if response is None:
        response = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers={**headers, "Range": "bytes=0-0"},
            stream=True,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"URL erişilemedi: HTTP {response.status_code}")

    final_url = response.url
    content_range = response.headers.get("Content-Range", "")
    total = 0
    match = re.search(r"/(\d+)$", content_range)
    if match:
        total = int(match.group(1))
    elif response.headers.get("Content-Length", "").isdigit():
        total = int(response.headers["Content-Length"])

    disposition = response.headers.get("Content-Disposition", "")
    filename = ""
    star = re.search(r"filename\*=UTF-8''([^;]+)", disposition, re.I)
    normal = re.search(r'filename="?([^";]+)"?', disposition, re.I)
    if star:
        filename = unquote(star.group(1))
    elif normal:
        filename = normal.group(1)
    if not filename:
        filename = Path(urlparse(final_url).path).name or "download.bin"
    filename = _safe_name(filename)

    ranges = (
        response.status_code == 206
        or "bytes" in response.headers.get("Accept-Ranges", "").lower()
        or bool(content_range)
    )
    probe = URLProbe(
        url=url,
        final_url=final_url,
        filename=filename,
        size=max(0, total),
        ranges=ranges,
        etag=response.headers.get("ETag", ""),
        last_modified=response.headers.get("Last-Modified", ""),
    )
    response.close()
    return probe


class ParallelDownloader:
    def __init__(
        self,
        target_dir: Path,
        connections: int = 0,
        telemetry: TelemetryCallback = _noop,
        log: LogCallback = _noop,
        cancelled: CancelCallback = lambda: False,
    ):
        self.target_dir = Path(target_dir)
        self.connections = max(0, int(connections))
        self.telemetry = telemetry
        self.log = log
        self.cancelled = cancelled
        self.state_dir = self.target_dir / ".drowned"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._last_emit = 0.0
        self._last_state_save = 0.0

    def download_all(self, urls: list[str]) -> tuple[list[Path], list[URLProbe]]:
        urls = [u.strip() for u in urls if u.strip()]
        if not urls:
            raise ValueError("En az bir indirme URL'si gerekli.")

        self.log("URL'ler doğrulanıyor...")
        probes = [probe_url(url) for url in urls]
        known_total = sum(p.size for p in probes)
        done_before = 0
        output: list[Path] = []
        for index, probe in enumerate(probes, 1):
            if self.cancelled():
                raise RuntimeError("İşlem iptal edildi.")
            self.log(
                f"[{index}/{len(probes)}] {probe.filename} • "
                f"{probe.size if probe.size else '?'} byte • "
                f"Range: {'evet' if probe.ranges else 'hayır'}"
            )
            path = self._download_one(probe, done_before, known_total)
            output.append(path)
            done_before += probe.size or path.stat().st_size
        return output, probes

    def _emit(self, phase: str, done: int, total: int, meter: RateMeter, detail: str = "", **extra):
        now = time.monotonic()
        if now - self._last_emit < 0.20 and done < total:
            return
        self._last_emit = now
        speed, avg, elapsed = meter.update(done)
        remaining = max(0, total - done) if total else 0
        eta = remaining / speed if speed > 0 and total else None
        snapshot = {
            "phase": phase,
            "done": int(done),
            "total": int(total),
            "progress": (done / total) if total else 0.0,
            "speed": speed,
            "average_speed": avg,
            "elapsed": elapsed,
            "eta": eta,
            "detail": detail,
            "disk_free": _disk_free(self.target_dir),
        }
        snapshot.update(extra)
        self.telemetry(snapshot)

    def _state_path(self, probe: URLProbe) -> Path:
        return self.state_dir / f"{_slug(probe.filename)}.download.json"

    def _load_state(self, probe: URLProbe, segments: list[dict]) -> list[dict]:
        state_path = self._state_path(probe)
        if not state_path.exists():
            return segments
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return segments
        identity_ok = (
            state.get("url") == probe.final_url
            and int(state.get("size") or 0) == probe.size
            and (not probe.etag or state.get("etag") == probe.etag)
            and len(state.get("segments") or []) == len(segments)
        )
        if not identity_ok:
            return segments
        restored = []
        for fresh, old in zip(segments, state["segments"]):
            if int(old.get("start", -1)) != fresh["start"] or int(old.get("end", -1)) != fresh["end"]:
                return segments
            fresh["done"] = max(0, min(int(old.get("done") or 0), fresh["end"] - fresh["start"] + 1))
            restored.append(fresh)
        return restored

    def _save_state(self, probe: URLProbe, segments: list[dict], force: bool = False):
        now = time.monotonic()
        if not force and now - self._last_state_save < 1.5:
            return
        self._last_state_save = now
        payload = {
            "url": probe.final_url,
            "size": probe.size,
            "etag": probe.etag,
            "last_modified": probe.last_modified,
            "segments": segments,
            "updated_at": time.time(),
        }
        path = self._state_path(probe)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _download_one(self, probe: URLProbe, base_done: int, overall_total: int) -> Path:
        final = self.target_dir / probe.filename
        part = final.with_name(final.name + ".part")
        if final.exists() and probe.size and final.stat().st_size == probe.size:
            self.log(f"Zaten tamamlanmış dosya kullanılıyor: {final.name}")
            return final

        if probe.size <= 0 or not probe.ranges:
            return self._single_stream(probe, final, part, base_done, overall_total)

        connections = self.connections or min(16, max(4, math.ceil(probe.size / (512 * 1024 * 1024))))
        connections = min(connections, 32)
        segment_size = math.ceil(probe.size / connections)
        segments = []
        for i in range(connections):
            start = i * segment_size
            if start >= probe.size:
                break
            end = min(probe.size - 1, start + segment_size - 1)
            segments.append({"start": start, "end": end, "done": 0})
        segments = self._load_state(probe, segments)

        resumed = sum(int(s["done"]) for s in segments)
        if resumed:
            self.log(f"Yarım kalan indirme bulundu: {probe.filename} • {resumed} byte devam edilecek.")

        part.parent.mkdir(parents=True, exist_ok=True)
        mode = "r+b" if part.exists() else "w+b"
        with open(part, mode) as handle:
            handle.truncate(probe.size)

        meter = RateMeter()
        file_done = resumed
        total_for_stats = overall_total or probe.size
        self._emit(
            "download",
            base_done + file_done,
            total_for_stats,
            meter,
            probe.filename,
            connections=len(segments),
            active_connections=0,
            file_done=file_done,
            file_total=probe.size,
        )

        def worker(seg_index: int):
            nonlocal file_done
            segment = segments[seg_index]
            length = segment["end"] - segment["start"] + 1
            if segment["done"] >= length:
                return
            current = segment["start"] + segment["done"]
            headers = {
                "User-Agent": "Drowned-Release-Manager/0.11",
                "Range": f"bytes={current}-{segment['end']}",
            }
            with requests.get(
                probe.final_url,
                headers=headers,
                stream=True,
                allow_redirects=True,
                timeout=(30, 90),
            ) as r:
                if r.status_code != 206:
                    raise RuntimeError(
                        f"Sunucu paralel Range isteğini kabul etmedi (HTTP {r.status_code})."
                    )
                with open(part, "r+b", buffering=0) as out:
                    out.seek(current)
                    for block in r.iter_content(chunk_size=1024 * 1024):
                        if self.cancelled():
                            raise RuntimeError("İşlem iptal edildi.")
                        if not block:
                            continue
                        out.write(block)
                        with self._lock:
                            segment["done"] += len(block)
                            file_done += len(block)
                            self._save_state(probe, segments)
                            active = sum(
                                1
                                for s in segments
                                if 0 < int(s["done"]) < (int(s["end"]) - int(s["start"]) + 1)
                            )
                            self._emit(
                                "download",
                                base_done + file_done,
                                total_for_stats,
                                meter,
                                probe.filename,
                                connections=len(segments),
                                active_connections=max(1, active),
                                file_done=file_done,
                                file_total=probe.size,
                            )

        try:
            with ThreadPoolExecutor(max_workers=len(segments), thread_name_prefix="drowned-download") as pool:
                futures = [pool.submit(worker, i) for i in range(len(segments))]
                for future in as_completed(futures):
                    future.result()
        except Exception:
            with self._lock:
                self._save_state(probe, segments, force=True)
            raise

        with self._lock:
            self._save_state(probe, segments, force=True)
        if part.stat().st_size != probe.size or sum(int(s["done"]) for s in segments) != probe.size:
            raise RuntimeError("İndirme segmentleri tamamlanmadı; dosya korunarak işlem durduruldu.")
        os.replace(part, final)
        self._state_path(probe).unlink(missing_ok=True)
        self._emit(
            "download",
            base_done + probe.size,
            total_for_stats,
            meter,
            probe.filename,
            connections=len(segments),
            active_connections=0,
            file_done=probe.size,
            file_total=probe.size,
        )
        return final

    def _single_stream(
        self,
        probe: URLProbe,
        final: Path,
        part: Path,
        base_done: int,
        overall_total: int,
    ) -> Path:
        existing = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": "Drowned-Release-Manager/0.11"}
        mode = "wb"
        if existing and probe.ranges:
            headers["Range"] = f"bytes={existing}-"
            mode = "ab"
        else:
            existing = 0
        meter = RateMeter()
        total_for_stats = overall_total or probe.size
        with requests.get(
            probe.final_url,
            headers=headers,
            stream=True,
            allow_redirects=True,
            timeout=(30, 90),
        ) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"İndirme başarısız: HTTP {r.status_code}")
            if mode == "ab" and r.status_code != 206:
                existing = 0
                mode = "wb"
            done = existing
            with open(part, mode) as out:
                for block in r.iter_content(chunk_size=1024 * 1024):
                    if self.cancelled():
                        raise RuntimeError("İşlem iptal edildi.")
                    if not block:
                        continue
                    out.write(block)
                    done += len(block)
                    self._emit(
                        "download",
                        base_done + done,
                        total_for_stats,
                        meter,
                        probe.filename,
                        connections=1,
                        active_connections=1,
                        file_done=done,
                        file_total=probe.size,
                    )
        if probe.size and done != probe.size:
            raise RuntimeError(f"Dosya boyutu uyuşmuyor: beklenen {probe.size}, gelen {done}")
        os.replace(part, final)
        return final


def _archive_entry_points(paths: list[Path]) -> list[Path]:
    archives = [p for p in paths if p.is_file() and ARCHIVE_RE.search(p.name)]
    if not archives:
        return []
    multipart = [p for p in archives if MULTIPART_RAR_RE.search(p.name)]
    if multipart:
        return [sorted(multipart, key=lambda p: p.name.lower())[0]]
    rars = sorted([p for p in archives if p.suffix.lower() == ".rar"], key=lambda p: p.name.lower())
    non_rars = sorted([p for p in archives if p.suffix.lower() != ".rar"], key=lambda p: p.name.lower())
    return ([rars[0]] if rars else []) + non_rars


def _safe_extract_target(root: Path, member_name: str) -> Path:
    target = (root / member_name).resolve()
    if not _inside(target, root):
        raise RuntimeError(f"Arşiv güvenlik kontrolü başarısız: {member_name}")
    return target


def _unique_extract_root(target_dir: Path, title: str) -> Path:
    base = target_dir / f"_extracted_{_slug(title)}"
    if not base.exists():
        return base
    for i in range(2, 1000):
        candidate = target_dir / f"_extracted_{_slug(title)}_{i}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Extraction klasörü için benzersiz ad oluşturulamadı.")


def _find_7zip() -> str | None:
    for name in ("7z", "7z.exe"):
        found = shutil.which(name)
        if found:
            return found
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "7-Zip" / "7z.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "7-Zip" / "7z.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def extract_archives(
    files: list[Path],
    target_dir: Path,
    title: str,
    telemetry: TelemetryCallback = _noop,
    log: LogCallback = _noop,
    cancelled: CancelCallback = lambda: False,
) -> tuple[Path, list[Path]]:
    entries = _archive_entry_points(files)
    if not entries:
        log("Arşiv bulunmadı; indirilen klasör doğrudan taranacak.")
        return target_dir, []

    extract_root = _unique_extract_root(target_dir, title)
    extract_root.mkdir(parents=True, exist_ok=False)
    meter = RateMeter()
    total_proxy = sum(max(1, p.stat().st_size) for p in entries)
    base = 0

    for archive in entries:
        if cancelled():
            raise RuntimeError("İşlem iptal edildi.")
        log(f"Arşiv çıkartılıyor: {archive.name}")
        if archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive) as zf:
                infos = [info for info in zf.infolist() if not info.is_dir()]
                total_unpacked = sum(max(0, info.file_size) for info in infos)
                unpacked = 0
                for index, info in enumerate(infos, 1):
                    if cancelled():
                        raise RuntimeError("İşlem iptal edildi.")
                    destination = _safe_extract_target(extract_root, info.filename)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(destination, "wb") as dst:
                        while True:
                            block = src.read(1024 * 1024)
                            if not block:
                                break
                            dst.write(block)
                            unpacked += len(block)
                            speed, avg, elapsed = meter.update(base + unpacked)
                            eta = (total_unpacked - unpacked) / speed if speed > 0 and total_unpacked > unpacked else 0
                            telemetry({
                                "phase": "extract",
                                "done": unpacked,
                                "total": total_unpacked,
                                "progress": unpacked / max(total_unpacked, 1),
                                "speed": speed,
                                "average_speed": avg,
                                "elapsed": elapsed,
                                "eta": eta,
                                "detail": info.filename,
                                "files_done": index - 1,
                                "files_total": len(infos),
                                "disk_free": _disk_free(target_dir),
                            })
            base += total_unpacked
            continue

        seven = _find_7zip()
        if not seven:
            raise RuntimeError(
                f"{archive.suffix.upper()} çıkartmak için 7-Zip bulunamadı. "
                "7-Zip kurulduktan sonra işlem tekrar denenebilir."
            )
        cmd = [seven, "x", str(archive), f"-o{extract_root}", "-y", "-bsp1", "-bb0"]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        )
        last_pct = 0
        assert proc.stdout is not None
        while True:
            if cancelled():
                proc.kill()
                raise RuntimeError("İşlem iptal edildi.")
            chunk = proc.stdout.readline()
            if chunk:
                for pct_text in re.findall(r"(\d{1,3})%", chunk):
                    last_pct = max(last_pct, min(100, int(pct_text)))
                    processed = base + int(archive.stat().st_size * last_pct / 100)
                    speed, avg, elapsed = meter.update(processed)
                    total_done_proxy = base + archive.stat().st_size
                    eta = (total_done_proxy - processed) / speed if speed > 0 else None
                    telemetry({
                        "phase": "extract",
                        "done": processed,
                        "total": total_proxy,
                        "progress": processed / max(total_proxy, 1),
                        "speed": speed,
                        "average_speed": avg,
                        "elapsed": elapsed,
                        "eta": eta,
                        "detail": archive.name,
                        "files_done": 0,
                        "files_total": 0,
                        "disk_free": _disk_free(target_dir),
                    })
            if proc.poll() is not None:
                break
        if proc.returncode != 0:
            raise RuntimeError(f"7-Zip çıkartma hatası ({proc.returncode}): {archive.name}")
        base += archive.stat().st_size

    telemetry({
        "phase": "extract",
        "done": total_proxy,
        "total": total_proxy,
        "progress": 1.0,
        "speed": 0.0,
        "average_speed": 0.0,
        "elapsed": 0.0,
        "eta": 0.0,
        "detail": "Extraction tamamlandı",
        "disk_free": _disk_free(target_dir),
    })
    return extract_root, entries


def score_executable(path: Path, game_title: str = "") -> int:
    stem = path.stem.lower()
    score = 10
    title_tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", game_title) if len(t) >= 3]
    for token in title_tokens:
        if token in stem:
            score += 18
    for token in GOOD_EXE_TOKENS:
        if token in stem:
            score += 10
    for token in BAD_EXE_TOKENS:
        if token in stem:
            score -= 55
    if "launcher" in stem:
        score -= 12
    lower_parts = [p.lower() for p in path.parts]
    if "binaries" in lower_parts:
        score += 12
    if any(p in {"win64", "x64", "win32"} for p in lower_parts):
        score += 8
    try:
        size = path.stat().st_size
        if size >= 100 * 1024 * 1024:
            score += 18
        elif size >= 10 * 1024 * 1024:
            score += 10
        elif size < 200 * 1024:
            score -= 8
    except OSError:
        pass
    return score


def detect_game_root(search_root: Path, game_title: str = "") -> Path:
    candidates: dict[Path, int] = {}
    for exe in search_root.rglob("*.exe"):
        try:
            rel_parts = exe.relative_to(search_root).parts
        except ValueError:
            continue
        if len(rel_parts) > 9:
            continue
        parent = exe.parent
        score = max(0, score_executable(exe, game_title))
        names = {p.name.lower() for p in parent.iterdir()} if parent.exists() else set()
        if any(name.endswith("_data") for name in names):
            score += 25
        if {"engine", "content"} & names:
            score += 18
        if "steam_api64.dll" in names or "steam_api.dll" in names:
            score += 20
        candidates[parent] = max(candidates.get(parent, -999), score)
        current = parent.parent
        for depth in range(1, 4):
            if not _inside(current, search_root):
                break
            candidates[current] = max(candidates.get(current, -999), score - depth * 3)
            if current == search_root:
                break
            current = current.parent
    if not candidates:
        raise RuntimeError("Oyun klasöründe çalıştırılabilir EXE bulunamadı.")
    return max(candidates.items(), key=lambda pair: pair[1])[0]


def detect_executable(game_root: Path, game_title: str = "") -> tuple[Path, list[tuple[int, Path]]]:
    candidates = []
    for exe in game_root.rglob("*.exe"):
        try:
            if len(exe.relative_to(game_root).parts) > 8:
                continue
        except ValueError:
            continue
        candidates.append((score_executable(exe, game_title), exe))
    if not candidates:
        raise RuntimeError("Ana oyun EXE'si bulunamadı.")
    candidates.sort(key=lambda pair: (pair[0], pair[1].stat().st_size if pair[1].exists() else 0), reverse=True)
    return candidates[0][1], candidates


def save_job(prepared: PreparedGame):
    download_dir = Path(prepared.download_dir)
    state_dir = download_dir / ".drowned"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "job.json").write_text(
        json.dumps(prepared.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def prepare_game(
    title: str,
    urls: list[str],
    download_dir: str,
    connections: int = 0,
    telemetry: TelemetryCallback = _noop,
    log: LogCallback = _noop,
    cancelled: CancelCallback = lambda: False,
) -> PreparedGame:
    target = Path(download_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    downloader = ParallelDownloader(target, connections, telemetry, log, cancelled)
    downloaded, _probes = downloader.download_all(urls)
    if cancelled():
        raise RuntimeError("İşlem iptal edildi.")

    total_downloaded = sum(p.stat().st_size for p in downloaded if p.exists())
    telemetry({
        "phase": "verify",
        "done": total_downloaded,
        "total": total_downloaded,
        "progress": 1.0,
        "speed": 0.0,
        "average_speed": 0.0,
        "elapsed": 0.0,
        "eta": 0.0,
        "detail": "İndirme dosyaları doğrulandı",
        "disk_free": _disk_free(target),
    })
    extract_root, archives = extract_archives(downloaded, target, title, telemetry, log, cancelled)
    log("Oyun kök klasörü aranıyor...")
    game_root = detect_game_root(extract_root, title)
    executable, ranked = detect_executable(game_root, title)
    log(f"Oyun kökü: {game_root}")
    log(f"Ana EXE: {executable}")
    for score, path in ranked[:8]:
        log(f"EXE adayı [{score:+d}] {path}")
    prepared = PreparedGame(
        title=title.strip(),
        download_dir=str(target),
        extraction_root=str(extract_root),
        game_root=str(game_root),
        executable=str(executable),
        downloaded_files=[str(p) for p in downloaded],
        archives=[str(p) for p in archives],
        created_at=time.time(),
    )
    save_job(prepared)
    telemetry({
        "phase": "ready_test",
        "done": 1,
        "total": 1,
        "progress": 1.0,
        "speed": 0.0,
        "average_speed": 0.0,
        "elapsed": 0.0,
        "eta": 0.0,
        "detail": executable.name,
        "disk_free": _disk_free(target),
    })
    return prepared


def launch_game(executable: str) -> int:
    exe = Path(executable)
    if not exe.exists():
        raise FileNotFoundError(exe)
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(
        [str(exe)],
        cwd=str(exe.parent),
        creationflags=flags,
    )
    return int(proc.pid)


def _window_for_pids(pids: set[int]) -> bool:
    if os.name != "nt" or not pids:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = {"value": False}
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def enum_window(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) in pids:
                found["value"] = True
                return False
            return True

        user32.EnumWindows(enum_window, 0)
        return found["value"]
    except Exception:
        return False


def process_snapshot(pid: int) -> dict:
    if psutil is None:
        return {"alive": True, "pid": pid, "children": 0, "memory": 0, "cpu": 0.0, "window": False}
    try:
        root = psutil.Process(pid)
        processes = [root] + root.children(recursive=True)
        alive = [p for p in processes if p.is_running() and p.status() != psutil.STATUS_ZOMBIE]
        pids = {p.pid for p in alive}
        rss = 0
        cpu = 0.0
        for p in alive:
            try:
                rss += p.memory_info().rss
                cpu += p.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return {
            "alive": bool(alive),
            "pid": pid,
            "children": max(0, len(alive) - 1),
            "memory": rss,
            "cpu": cpu,
            "window": _window_for_pids(pids),
            "pids": sorted(pids),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {"alive": False, "pid": pid, "children": 0, "memory": 0, "cpu": 0.0, "window": False}


def terminate_process_tree(pid: int):
    if not pid:
        return
    if psutil is not None:
        try:
            root = psutil.Process(pid)
            children = root.children(recursive=True)
            for proc in reversed(children):
                try:
                    proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            try:
                root.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            _gone, alive = psutil.wait_procs(children + [root], timeout=3)
            for proc in alive:
                try:
                    proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)


def confirm_test_success(prepared: PreparedGame, log: LogCallback = _noop) -> int:
    prepared.user_confirmed = True
    if prepared.test_pid:
        terminate_process_tree(prepared.test_pid)
        prepared.test_pid = None

    freed = 0
    owned_dir = Path(prepared.download_dir).resolve()
    candidates = [Path(p) for p in prepared.archives]
    for raw in prepared.downloaded_files:
        p = Path(raw)
        if ARCHIVE_VOLUME_RE.search(p.name):
            candidates.append(p)
        candidates.append(p.with_name(p.name + ".part"))
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not _inside(resolved, owned_dir):
            continue
        seen.add(resolved)
        if resolved.exists() and resolved.is_file():
            size = resolved.stat().st_size
            resolved.unlink()
            freed += size
            log(f"Temizlendi: {resolved.name}")
    state_dir = owned_dir / ".drowned"
    for state in state_dir.glob("*.download.json"):
        state.unlink(missing_ok=True)
    save_job(prepared)
    return freed


def cleanup_after_verified_publish(prepared: PreparedGame, upload_source: str, log: LogCallback = _noop) -> int:
    extract_root = Path(prepared.extraction_root).resolve()
    source = Path(upload_source).resolve()
    if extract_root == Path(prepared.download_dir).resolve():
        raise RuntimeError("Otomatik final cleanup güvenli değil: özel extraction kökü oluşturulmamış.")
    if not _inside(source, extract_root):
        raise RuntimeError("Yükleme kaynağı bu job'ın oluşturduğu extraction klasöründe değil; otomatik silme yapılmadı.")
    if not prepared.user_confirmed:
        raise RuntimeError("Oyun testi kullanıcı tarafından başarılı olarak onaylanmamış.")

    size = 0
    if extract_root.exists():
        for p in extract_root.rglob("*"):
            try:
                if p.is_file():
                    size += p.stat().st_size
            except OSError:
                pass
        shutil.rmtree(extract_root)
        log(f"Remote yayın doğrulandı; yerel oyun temizlendi: {extract_root}")
    state_dir = Path(prepared.download_dir) / ".drowned"
    job_file = state_dir / "job.json"
    job_file.unlink(missing_ok=True)
    try:
        if state_dir.exists() and not any(state_dir.iterdir()):
            state_dir.rmdir()
    except OSError:
        pass
    return size
