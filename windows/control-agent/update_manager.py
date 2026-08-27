from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from build_info import BUILD_NUMBER, BUILD_SHA, BUILD_VERSION

REPO = "thedrowned925/drowned1"
UPDATE_TAG = "control-nightly"
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/tags/{UPDATE_TAG}"
MANIFEST_ASSET = "control-update.json"
USER_AGENT = "Drowned-Agent-Updater/1.0"


class UpdateError(RuntimeError):
    pass


def _request_json(url: str, timeout: int = 8) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, destination: Path, timeout: int = 30) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def fetch_manifest() -> dict | None:
    try:
        release = _request_json(RELEASE_API)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError(f"GitHub güncelleme kanalı okunamadı: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UpdateError(f"GitHub güncelleme kanalı okunamadı: {exc}") from exc

    asset = next((item for item in release.get("assets", []) if item.get("name") == MANIFEST_ASSET), None)
    if not asset:
        return None

    url = str(asset.get("browser_download_url") or "")
    if not url.startswith("https://github.com/"):
        raise UpdateError("Güncelleme manifest adresi beklenen GitHub alanında değil.")

    separator = "&" if "?" in url else "?"
    manifest_url = f"{url}{separator}nocache={time.time_ns()}"
    try:
        return _request_json(manifest_url)
    except Exception as exc:
        raise UpdateError(f"Güncelleme manifesti okunamadı: {exc}") from exc


def windows_update(manifest: dict | None) -> dict | None:
    if not manifest:
        return None
    windows = manifest.get("windows") or {}
    if not windows.get("available", False):
        return None

    try:
        remote_number = int(windows.get("build_number", 0))
    except (TypeError, ValueError):
        return None

    if remote_number <= int(BUILD_NUMBER or 0):
        return None

    url = str(windows.get("url") or "")
    sha256 = str(windows.get("sha256") or "").lower()
    if not url.startswith(f"https://github.com/{REPO}/releases/download/{UPDATE_TAG}/"):
        raise UpdateError("Windows güncelleme adresi beklenen GitHub release kanalında değil.")
    if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
        raise UpdateError("Windows güncelleme SHA-256 bilgisi geçersiz.")

    return {
        "build_number": remote_number,
        "build_sha": str(manifest.get("build_sha") or windows.get("build_sha") or ""),
        "version": str(manifest.get("version") or windows.get("version") or remote_number),
        "url": url,
        "sha256": sha256,
    }


def check_for_windows_update() -> dict | None:
    return windows_update(fetch_manifest())


def download_windows_update(update: dict) -> Path:
    destination = Path(tempfile.gettempdir()) / f"Drowned-Agent-{update['build_number']}.update.exe"
    partial = destination.with_suffix(destination.suffix + ".part")
    for candidate in (partial, destination):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        _download(update["url"], partial)
        actual = _sha256(partial)
        if actual != update["sha256"]:
            raise UpdateError(
                "İndirilen EXE doğrulanamadı. "
                f"Beklenen SHA-256 {update['sha256']}, gelen {actual}."
            )
        partial.replace(destination)
        return destination
    except Exception:
        try:
            partial.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def can_self_replace() -> bool:
    return os.name == "nt" and bool(getattr(sys, "frozen", False)) and Path(sys.executable).suffix.lower() == ".exe"


def schedule_windows_replace(downloaded: Path) -> None:
    if not can_self_replace():
        raise UpdateError("Otomatik EXE değiştirme yalnızca paketlenmiş Drowned-Agent.exe içinde kullanılabilir.")

    downloaded = downloaded.resolve()
    current = Path(sys.executable).resolve()
    if downloaded == current:
        raise UpdateError("Güncelleme dosyası çalışan EXE ile aynı olamaz.")

    script = Path(tempfile.gettempdir()) / f"drowned-agent-update-{os.getpid()}.cmd"
    script.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        f'set "NEW={downloaded}"\r\n'
        f'set "TARGET={current}"\r\n'
        "for /L %%I in (1,1,60) do (\r\n"
        "  copy /Y \"%NEW%\" \"%TARGET%\" >nul 2>&1\r\n"
        "  if not errorlevel 1 goto restart\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        ")\r\n"
        "exit /b 1\r\n"
        ":restart\r\n"
        "del /Q \"%NEW%\" >nul 2>&1\r\n"
        "start \"\" \"%TARGET%\"\r\n"
        "del \"%~f0\"\r\n",
        encoding="utf-8",
    )

    creation_flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
    )
    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        creationflags=creation_flags,
        close_fds=True,
        cwd=str(current.parent),
    )


def current_build_label() -> str:
    short_sha = BUILD_SHA[:8] if BUILD_SHA and BUILD_SHA != "dev" else "dev"
    return f"{BUILD_VERSION} · build {BUILD_NUMBER} · {short_sha}"
