from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psutil

import game_prepare as base


FDM_PROCESS_NAMES = {"fdm.exe", "fdm"}
COMPLETE_WORDS = ("complete", "completed", "finished", "done", "success", "seeding")
ERROR_WORDS = ("error", "failed", "failure")


@dataclass
class FdmSnapshot:
    done: int = 0
    total: int = 0
    speed: float = 0.0
    eta: float | None = None
    status: str = ""
    path: str = ""
    connections: int = 0
    completed: bool = False
    error: str = ""
    table: str = ""


def find_fdm_executable() -> Path | None:
    candidates: list[Path] = []
    for env_name in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env_name)
        if not root:
            continue
        root_path = Path(root)
        candidates.extend(
            [
                root_path / "Programs" / "Free Download Manager" / "fdm.exe",
                root_path / "Softdeluxe" / "Free Download Manager" / "fdm.exe",
                root_path / "Free Download Manager" / "fdm.exe",
            ]
        )
    which = shutil.which("fdm.exe") or shutil.which("fdm")
    if which:
        candidates.insert(0, Path(which))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def find_fdm_database() -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    root = Path(local)
    candidates = [
        root / "Free Download Manager" / "fdm.sqlite",
        root / "Free Download Manager" / "db.sqlite",
        root / "Softdeluxe" / "Free Download Manager" / "fdm.sqlite",
        root / "Softdeluxe" / "Free Download Manager" / "db.sqlite",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for parent in (root / "Free Download Manager", root / "Softdeluxe" / "Free Download Manager"):
        if parent.exists():
            found = sorted(parent.glob("*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
            if found:
                return found[0]
    return None


def _flatten(prefix: str, value: Any, out: dict[str, Any], depth: int = 0):
    if depth > 4:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _flatten(f"{prefix}.{key}" if prefix else str(key), child, out, depth + 1)
    elif isinstance(value, list):
        for index, child in enumerate(value[:40]):
            _flatten(f"{prefix}[{index}]", child, out, depth + 1)
    else:
        out[prefix] = value
        if isinstance(value, str):
            text = value.strip()
            if text[:1] in {"{", "["}:
                try:
                    parsed = json.loads(text)
                except Exception:
                    return
                _flatten(prefix + ".json", parsed, out, depth + 1)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
            try:
                return float(text)
            except ValueError:
                pass
    return None


def _best_number(flat: dict[str, Any], patterns: tuple[str, ...], *, maximum: float | None = None) -> float:
    values: list[float] = []
    for key, value in flat.items():
        lower = key.lower()
        if not any(re.search(pattern, lower) for pattern in patterns):
            continue
        number = _number(value)
        if number is None or number < 0:
            continue
        if maximum is not None and number > maximum:
            continue
        values.append(number)
    return max(values, default=0.0)


def _best_text(flat: dict[str, Any], patterns: tuple[str, ...], filename: str = "") -> str:
    candidates: list[tuple[int, str]] = []
    for key, value in flat.items():
        if not isinstance(value, str) or not value.strip():
            continue
        lower_key = key.lower()
        if not any(re.search(pattern, lower_key) for pattern in patterns):
            continue
        text = value.strip()
        score = 0
        if filename and filename.lower() in text.lower():
            score += 100
        if ":\\" in text or text.startswith("/"):
            score += 20
        candidates.append((score, text))
    return max(candidates, default=(0, ""), key=lambda item: item[0])[1]


class FdmDatabaseReader:
    """Read FDM's own SQLite state without depending on one fixed schema.

    FDM has changed its internal database shape across releases. We therefore
    discover tables/columns and flatten JSON payloads, then match the row by URL
    and filename. Progress comes from the FDM record. If FDM does not expose a
    speed/ETA field in a particular build, speed is derived from successive FDM
    downloaded-byte values rather than from the filesystem.
    """

    def __init__(self, database: Path, url: str, filename: str, target_dir: Path):
        self.database = Path(database)
        self.url = url
        self.filename = filename
        self.target_dir = Path(target_dir)
        self._last_done = 0
        self._last_time = time.monotonic()
        self._smooth_speed = 0.0

    @staticmethod
    def _quoted(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def _candidate_rows(self) -> list[tuple[int, str, dict[str, Any]]]:
        if not self.database.exists():
            return []
        uri = self.database.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=1.0)
        connection.execute("PRAGMA busy_timeout=1000")
        connection.execute("PRAGMA read_uncommitted=1")
        try:
            tables = [
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            results: list[tuple[int, str, dict[str, Any]]] = []
            url_lower = self.url.lower()
            file_lower = self.filename.lower()
            target_lower = str(self.target_dir).lower()
            for table in tables:
                try:
                    columns = [str(row[1]) for row in connection.execute(f"PRAGMA table_info({self._quoted(table)})")]
                    if not columns:
                        continue
                    rows = connection.execute(
                        f"SELECT * FROM {self._quoted(table)} ORDER BY rowid DESC LIMIT 600"
                    ).fetchall()
                except sqlite3.DatabaseError:
                    continue
                for row in rows:
                    flat: dict[str, Any] = {}
                    for column, value in zip(columns, row):
                        _flatten(column, value, flat)
                    haystack = "\n".join(str(value).lower() for value in flat.values() if value is not None)
                    score = 0
                    if url_lower and url_lower in haystack:
                        score += 300
                    parsed_name = Path(urlparse(self.url).path).name.lower()
                    if parsed_name and parsed_name in haystack:
                        score += 100
                    if file_lower and file_lower in haystack:
                        score += 120
                    if target_lower and target_lower in haystack:
                        score += 40
                    if "download" in table.lower():
                        score += 15
                    if score:
                        results.append((score, table, flat))
            results.sort(key=lambda item: item[0], reverse=True)
            return results[:30]
        finally:
            connection.close()

    def snapshot(self, expected_total: int = 0) -> FdmSnapshot | None:
        rows = self._candidate_rows()
        if not rows:
            return None
        _score, table, flat = rows[0]
        total = int(
            _best_number(
                flat,
                (
                    r"(^|\.)(total|content).*(bytes|size|length)$",
                    r"(^|\.)(file_?size|filesize|total_?bytes|totalbytes)$",
                ),
            )
            or expected_total
            or 0
        )
        done = int(
            _best_number(
                flat,
                (
                    r"(^|\.)(downloaded|received|transferred|completed|current).*(bytes|size)$",
                    r"(^|\.)(downloaded_?bytes|received_?bytes|bytes_?downloaded|bytes_?received)$",
                ),
                maximum=float(total) * 1.05 if total else None,
            )
        )
        if not done and total:
            percent = _best_number(flat, (r"(^|\.)(progress|percent|percentage)$",), maximum=100.0)
            if percent:
                done = int(total * (percent / 100.0))

        direct_speed = _best_number(
            flat,
            (r"(^|\.)(speed|download_?speed|current_?speed|bytes_?per_?second)$",),
        )
        now = time.monotonic()
        dt = max(0.05, now - self._last_time)
        derived_speed = max(0.0, (done - self._last_done) / dt) if done >= self._last_done else 0.0
        self._last_done = done
        self._last_time = now
        raw_speed = direct_speed or derived_speed
        if raw_speed > 0:
            self._smooth_speed = raw_speed if self._smooth_speed <= 0 else self._smooth_speed * 0.72 + raw_speed * 0.28
        speed = float(direct_speed or self._smooth_speed or 0.0)

        eta_value = _best_number(flat, (r"(^|\.)(eta|remaining_?time|time_?remaining)$",), maximum=365 * 24 * 3600)
        eta = float(eta_value) if eta_value else ((total - done) / speed if total and speed > 0 and done <= total else None)
        status = _best_text(flat, (r"(^|\.)(status|state|download_?state)$",))
        path = _best_text(flat, (r"(^|\.)(path|file|filename|filepath|target|output|folder)",), self.filename)
        connections = int(_best_number(flat, (r"(^|\.)(connections|sections|threads|segments)$",), maximum=512))
        status_lower = status.lower()
        error = status if any(word in status_lower for word in ERROR_WORDS) else ""
        completed = any(word in status_lower for word in COMPLETE_WORDS)
        if total and done >= total:
            completed = True
        return FdmSnapshot(
            done=max(0, done),
            total=max(0, total),
            speed=max(0.0, speed),
            eta=eta,
            status=status,
            path=path,
            connections=max(0, connections),
            completed=completed,
            error=error,
            table=table,
        )


def _fdm_pids() -> list[int]:
    pids: list[int] = []
    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = str(process.info.get("name") or "").lower()
            exe = str(process.info.get("exe") or "").lower()
            if name in FDM_PROCESS_NAMES or exe.endswith("\\fdm.exe") or exe.endswith("/fdm"):
                pids.append(int(process.info["pid"]))
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    return pids


def _ensure_fdm_running(executable: Path) -> list[int]:
    pids = _fdm_pids()
    if pids:
        return pids
    subprocess.Popen([str(executable)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        pids = _fdm_pids()
        if pids:
            return pids
        time.sleep(0.25)
    raise RuntimeError("Free Download Manager başlatıldı ancak çalışan FDM işlemi bulunamadı.")


def submit_to_fdm(url: str, target_dir: Path, log=base._noop):
    if os.name != "nt":
        raise RuntimeError("FDM otomatik entegrasyonu şu anda Windows build'inde destekleniyor.")
    executable = find_fdm_executable()
    if not executable:
        raise RuntimeError("Free Download Manager bulunamadı. FDM 6.x kurulu olmalı.")
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    pids = _ensure_fdm_running(executable)

    try:
        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys
    except ImportError as exc:
        raise RuntimeError("FDM UI köprüsü için pywinauto paketi bulunamadı.") from exc

    desktop = Desktop(backend="uia")
    main = None
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline and main is None:
        for pid in pids + _fdm_pids():
            try:
                windows = desktop.windows(process=pid, visible_only=True)
            except Exception:
                continue
            if windows:
                main = max(windows, key=lambda window: max(1, window.rectangle().width()) * max(1, window.rectangle().height()))
                break
        if main is None:
            time.sleep(0.25)
    if main is None:
        raise RuntimeError("FDM ana penceresi UI Automation üzerinden bulunamadı.")

    try:
        main.set_focus()
        send_keys("^j")
    except Exception as exc:
        raise RuntimeError(f"FDM yeni indirme penceresi açılamadı: {exc}") from exc

    dialog = None
    edits = []
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        for pid in list(dict.fromkeys(pids + _fdm_pids())):
            try:
                for window in desktop.windows(process=pid, visible_only=True):
                    current_edits = window.descendants(control_type="Edit")
                    if current_edits:
                        dialog = window
                        edits = current_edits
                        break
            except Exception:
                continue
            if dialog is not None:
                break
        if dialog is not None:
            break
        time.sleep(0.2)
    if dialog is None or not edits:
        raise RuntimeError("FDM 'Add download' penceresi bulunamadı. FDM açıkken tekrar dene.")

    url_edit = None
    folder_edit = None
    for edit in edits:
        try:
            text = str(edit.get_value() or edit.window_text() or "")
        except Exception:
            text = ""
        lower = text.lower()
        if url_edit is None and ("http://" in lower or "https://" in lower or "url" in lower or "link" in lower):
            url_edit = edit
        if folder_edit is None and (re.search(r"[a-zA-Z]:\\", text) or text.startswith("\\\\")):
            folder_edit = edit
    if url_edit is None:
        url_edit = edits[0]
    if folder_edit is None and len(edits) >= 2:
        folder_edit = edits[-1]
    if folder_edit is url_edit:
        folder_edit = None

    try:
        url_edit.set_edit_text(url)
    except Exception:
        url_edit.set_focus()
        send_keys("^a")
        send_keys(url, with_spaces=True)

    if folder_edit is None:
        raise RuntimeError(
            "FDM hedef klasör alanı otomatik bulunamadı. Bu build dosyayı başka diske taşımaz; "
            "FDM'nin Add Download penceresinin standart hedef klasör alanı gerekli."
        )
    try:
        folder_edit.set_edit_text(str(target_dir))
    except Exception:
        folder_edit.set_focus()
        send_keys("^a")
        send_keys(str(target_dir), with_spaces=True)

    button = None
    preferred = ("download", "add", "start", "indir", "ekle", "başlat", "ok")
    try:
        buttons = dialog.descendants(control_type="Button")
    except Exception:
        buttons = []
    for token in preferred:
        for candidate in buttons:
            try:
                text = candidate.window_text().strip().lower()
            except Exception:
                continue
            if text == token or token in text:
                button = candidate
                break
        if button is not None:
            break
    if button is not None:
        button.click_input()
    else:
        dialog.set_focus()
        send_keys("{ENTER}")
    log(f"FDM job gönderildi • hedef: {target_dir}")


class FdmDownloader(base.ParallelDownloader):
    """Use Free Download Manager for transport and FDM's own database for telemetry."""

    def download_all(self, urls: list[str]):
        urls = [url.strip() for url in urls if url.strip()]
        if not urls:
            raise ValueError("En az bir indirme URL'si gerekli.")
        probes = [base.probe_url(url) for url in urls]
        overall_total = sum(probe.size for probe in probes)
        outputs: list[Path] = []
        done_before = 0
        for index, probe in enumerate(probes, 1):
            if self.cancelled():
                raise RuntimeError("İşlem iptal edildi.")
            self.log(f"[{index}/{len(probes)}] FDM'ye gönderiliyor: {probe.filename}")
            path = self._download_one_fdm(probe, done_before, overall_total)
            outputs.append(path)
            done_before += probe.size or path.stat().st_size
        return outputs, probes

    def _download_one_fdm(self, probe: base.URLProbe, base_done: int, overall_total: int) -> Path:
        expected = self.target_dir / probe.filename
        if expected.exists() and (not probe.size or expected.stat().st_size == probe.size):
            self.log(f"Zaten tamamlanmış dosya kullanılıyor: {expected.name}")
            return expected

        submit_to_fdm(probe.final_url, self.target_dir, self.log)
        db_deadline = time.monotonic() + 30
        database = find_fdm_database()
        while database is None and time.monotonic() < db_deadline:
            if self.cancelled():
                raise RuntimeError("İşlem iptal edildi. FDM'deki indirme ayrı olarak devam ediyor olabilir.")
            time.sleep(0.5)
            database = find_fdm_database()
        if database is None:
            raise RuntimeError("FDM yerel veritabanı bulunamadı; FDM istatistikleri okunamıyor.")

        self.log(f"FDM telemetry DB: {database}")
        reader = FdmDatabaseReader(database, probe.final_url, probe.filename, self.target_dir)
        start = time.monotonic()
        snapshot_deadline = start + 45
        last_snapshot: FdmSnapshot | None = None
        while True:
            if self.cancelled():
                raise RuntimeError("İşlem iptal edildi. FDM'deki indirme ayrı olarak devam ediyor olabilir.")
            try:
                snapshot = reader.snapshot(probe.size)
            except (sqlite3.DatabaseError, OSError):
                snapshot = None
            if snapshot is None:
                if time.monotonic() > snapshot_deadline:
                    raise RuntimeError("FDM download kaydı 45 saniye içinde SQLite veritabanında bulunamadı.")
                time.sleep(0.5)
                continue
            last_snapshot = snapshot
            done = max(0, snapshot.done)
            total = snapshot.total or probe.size
            speed = max(0.0, snapshot.speed)
            eta = snapshot.eta
            elapsed = max(0.0, time.monotonic() - start)
            progress = done / total if total else 0.0
            detail = f"FDM • {probe.filename}"
            if snapshot.status:
                detail += f" • {snapshot.status}"
            self.telemetry(
                {
                    "phase": "download",
                    "done": base_done + done,
                    "total": overall_total or total,
                    "progress": (base_done + done) / max(overall_total or total, 1),
                    "speed": speed,
                    "average_speed": speed,
                    "elapsed": elapsed,
                    "eta": eta,
                    "detail": detail,
                    "disk_free": base._disk_free(self.target_dir),
                    "connections": snapshot.connections,
                    "active_connections": snapshot.connections if not snapshot.completed else 0,
                    "file_done": done,
                    "file_total": total,
                }
            )
            if snapshot.error:
                raise RuntimeError(f"FDM indirme hatası: {snapshot.error}")

            output = Path(snapshot.path) if snapshot.path else expected
            if not output.is_absolute():
                output = self.target_dir / output.name
            try:
                output.resolve().relative_to(self.target_dir.resolve())
            except (OSError, ValueError):
                raise RuntimeError(
                    f"FDM dosyayı seçilen klasörün dışına kaydediyor: {output}. "
                    "Dosya otomatik taşınmadı; disk alanını korumak için işlem durduruldu."
                )
            if snapshot.completed:
                if not output.exists() and expected.exists():
                    output = expected
                if output.exists():
                    if probe.size and output.stat().st_size != probe.size:
                        time.sleep(0.5)
                        continue
                    self.log(f"✓ FDM indirme tamamlandı: {output.name}")
                    return output
            time.sleep(0.5)
