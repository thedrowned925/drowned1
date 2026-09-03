from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from game_prepare import RateMeter, _disk_free, _slug, _unique_extract_root, extract_archives


TelemetryCallback = Callable[[dict], None]
LogCallback = Callable[[str], None]
CancelCallback = Callable[[], bool]


def _find_7zip() -> str | None:
    for name in ("7z", "7z.exe"):
        found = shutil.which(name)
        if found:
            return found
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if not base:
            continue
        candidate = Path(base) / "7-Zip" / "7z.exe"
        if candidate.exists():
            return str(candidate)
    return None


def _find_winrar() -> str | None:
    # Prefer UnRAR because it exposes console progress cleanly; WinRAR.exe is a
    # compatible fallback and is present on standard WinRAR installations.
    for name in ("UnRAR.exe", "WinRAR.exe", "unrar", "winrar"):
        found = shutil.which(name)
        if found:
            return found

    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if not base:
            continue
        root = Path(base) / "WinRAR"
        for exe_name in ("UnRAR.exe", "WinRAR.exe"):
            candidate = root / exe_name
            if candidate.exists():
                return str(candidate)

    if os.name == "nt":
        try:
            import winreg

            for exe_name in ("UnRAR.exe", "WinRAR.exe"):
                key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
                for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    try:
                        with winreg.OpenKey(hive, key_path) as key:
                            value, _ = winreg.QueryValueEx(key, None)
                            candidate = Path(str(value).strip('"'))
                            if candidate.exists():
                                return str(candidate)
                    except OSError:
                        continue
        except Exception:
            pass
    return None


def extract_archive_remote(
    archive: Path,
    target_dir: Path,
    title: str,
    telemetry: TelemetryCallback,
    log: LogCallback,
    cancelled: CancelCallback,
) -> Path:
    archive = archive.resolve()
    target_dir = target_dir.resolve()

    if archive.suffix.lower() == ".zip" or _find_7zip():
        root, _entries = extract_archives(
            [archive], target_dir, title, telemetry=telemetry, log=log, cancelled=cancelled
        )
        return root

    winrar = _find_winrar()
    if not winrar:
        raise RuntimeError(
            f"{archive.suffix.upper()} çıkartmak için 7-Zip veya WinRAR bulunamadı. "
            "PC'de WinRAR ya da 7-Zip kurulu olmalı."
        )

    extract_root = _unique_extract_root(target_dir, title)
    extract_root.mkdir(parents=True, exist_ok=False)
    executable_name = Path(winrar).name.lower()
    if executable_name.startswith("unrar"):
        command = [winrar, "x", "-o+", "-y", str(archive), str(extract_root) + os.sep]
        label = "UnRAR"
    else:
        command = [winrar, "x", "-o+", "-y", str(archive), str(extract_root) + os.sep]
        label = "WinRAR"

    log(f"{label} kullanılıyor: {winrar}")
    archive_size = max(1, int(archive.stat().st_size))
    meter = RateMeter()
    telemetry({
        "phase": "extract",
        "done": 0,
        "total": archive_size,
        "progress": 0.0,
        "speed": 0.0,
        "average_speed": 0.0,
        "eta": None,
        "detail": archive.name,
        "disk_free": _disk_free(target_dir),
    })

    process = subprocess.Popen(
        command,
        cwd=str(archive.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
        creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0),
    )
    last_percent = 0
    last_emit = 0.0
    assert process.stdout is not None

    while True:
        if cancelled():
            process.kill()
            raise RuntimeError("İşlem iptal edildi.")

        line = process.stdout.readline()
        if line:
            for match in re.findall(r"(?<!\d)(\d{1,3})%", line):
                last_percent = max(last_percent, min(100, int(match)))
        now = time.monotonic()
        if now - last_emit >= 0.5:
            last_emit = now
            done = int(archive_size * last_percent / 100)
            speed, average, _elapsed = meter.update(done)
            eta = (archive_size - done) / speed if speed > 0 and done < archive_size else None
            telemetry({
                "phase": "extract",
                "done": done,
                "total": archive_size,
                "progress": last_percent / 100.0,
                "speed": speed,
                "average_speed": average,
                "eta": eta,
                "detail": archive.name,
                "disk_free": _disk_free(target_dir),
            })

        if process.poll() is not None:
            break
        if not line:
            time.sleep(0.1)

    if process.returncode != 0:
        raise RuntimeError(f"{label} çıkartma hatası ({process.returncode}): {archive.name}")

    telemetry({
        "phase": "extract",
        "done": archive_size,
        "total": archive_size,
        "progress": 1.0,
        "speed": 0.0,
        "average_speed": 0.0,
        "eta": 0,
        "detail": "Extraction tamamlandı",
        "disk_free": _disk_free(target_dir),
    })
    return extract_root


def _collect_files(source: Path) -> tuple[list[tuple[Path, Path, int]], int]:
    if source.is_file():
        size = int(source.stat().st_size)
        return [(source, Path(source.name), size)], size

    rows: list[tuple[Path, Path, int]] = []
    total = 0
    for root, _dirs, files in os.walk(source):
        root_path = Path(root)
        relative_root = root_path.relative_to(source)
        for name in files:
            path = root_path / name
            try:
                size = int(path.stat().st_size)
            except OSError:
                size = 0
            relative = relative_root / name
            rows.append((path, relative, size))
            total += size
    return rows, total


def _copy_file_with_progress(
    source: Path,
    destination: Path,
    *,
    base_done: int,
    total: int,
    meter: RateMeter,
    telemetry: TelemetryCallback,
    cancelled: CancelCallback,
    phase: str,
) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    current = 0
    with open(source, "rb") as src, open(destination, "wb") as dst:
        while True:
            if cancelled():
                raise RuntimeError("İşlem iptal edildi.")
            block = src.read(4 * 1024 * 1024)
            if not block:
                break
            dst.write(block)
            current += len(block)
            done = base_done + current
            speed, average, _elapsed = meter.update(done)
            eta = (total - done) / speed if speed > 0 and done < total else None
            telemetry({
                "phase": phase,
                "done": done,
                "total": max(total, 1),
                "progress": done / max(total, 1),
                "speed": speed,
                "average_speed": average,
                "eta": eta,
                "detail": str(source),
                "current_item": str(source),
                "disk_free": _disk_free(destination.parent),
            })
    try:
        shutil.copystat(source, destination)
    except OSError:
        pass
    return current


def run_file_operation(
    source: Path,
    target_dir: Path,
    *,
    move: bool,
    telemetry: TelemetryCallback,
    log: LogCallback,
    cancelled: CancelCallback,
) -> Path:
    source = source.resolve()
    target_dir = target_dir.resolve()
    if not source.exists():
        raise RuntimeError("Kaynak dosya/klasör bulunamadı.")
    if not target_dir.is_dir():
        raise RuntimeError("Hedef klasör bulunamadı.")

    destination = target_dir / source.name
    if destination.exists():
        raise RuntimeError(f"Hedefte aynı isim zaten var: {destination.name}")
    if source.is_dir():
        try:
            destination.relative_to(source)
            raise RuntimeError("Bir klasör kendi içine kopyalanamaz/taşınamaz.")
        except ValueError:
            pass

    phase = "move" if move else "copy"
    same_drive = os.path.splitdrive(str(source))[0].casefold() == os.path.splitdrive(str(target_dir))[0].casefold()
    if move and same_drive:
        telemetry({
            "phase": phase,
            "done": 0,
            "total": 1,
            "progress": 0.0,
            "speed": 0.0,
            "average_speed": 0.0,
            "eta": None,
            "detail": str(source),
        })
        shutil.move(str(source), str(destination))
        telemetry({
            "phase": phase,
            "done": 1,
            "total": 1,
            "progress": 1.0,
            "speed": 0.0,
            "average_speed": 0.0,
            "eta": 0,
            "detail": str(destination),
        })
        return destination

    files, total = _collect_files(source)
    meter = RateMeter()
    done = 0
    try:
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=False)
            # Preserve empty directories too.
            for root, dirs, _files in os.walk(source):
                relative_root = Path(root).relative_to(source)
                for dirname in dirs:
                    (destination / relative_root / dirname).mkdir(parents=True, exist_ok=True)
        for src, relative, _size in files:
            dst = destination if source.is_file() else destination / relative
            copied = _copy_file_with_progress(
                src,
                dst,
                base_done=done,
                total=max(total, 1),
                meter=meter,
                telemetry=telemetry,
                cancelled=cancelled,
                phase=phase,
            )
            done += copied
        if source.is_dir():
            try:
                shutil.copystat(source, destination)
            except OSError:
                pass
    except Exception:
        try:
            if destination.is_dir():
                shutil.rmtree(destination)
            elif destination.exists():
                destination.unlink()
        except OSError:
            pass
        raise

    if move:
        if source.is_dir():
            shutil.rmtree(source)
        else:
            source.unlink()

    telemetry({
        "phase": phase,
        "done": max(total, 1),
        "total": max(total, 1),
        "progress": 1.0,
        "speed": 0.0,
        "average_speed": 0.0,
        "eta": 0,
        "detail": str(destination),
        "current_item": str(destination),
    })
    log(f"{'Taşındı' if move else 'Kopyalandı'}: {source} -> {destination}")
    return destination
