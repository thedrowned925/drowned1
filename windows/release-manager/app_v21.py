from __future__ import annotations

import re
import sys
import threading
from pathlib import Path

from PySide6.QtWidgets import QApplication

import app_v20 as previous
from drowned_shared.realtime_status import LiveStatusPublisher
from game_prepare import extract_archives


APP_VERSION = "0.21.0"
_ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z"}
_MULTIPART_RAR = re.compile(r"\.part(\d+)\.rar$", re.I)


class Manager(previous.Manager):
    """v0.21: Android-controlled archive browsing/extraction with live telemetry."""

    def __init__(self):
        self._remote_extract_thread: threading.Thread | None = None
        self._remote_extract_cancel = threading.Event()
        self._remote_extract_archive = ""
        self._remote_extract_target = ""
        self._remote_extract_output = ""
        self._remote_extract_error = ""
        self._remote_extract_live: LiveStatusPublisher | None = None
        super().__init__()
        self.setWindowTitle(
            f"Drowned Release Manager {APP_VERSION} • Android Remote Extract + Upload"
        )

    def _extract_running(self) -> bool:
        return bool(self._remote_extract_thread is not None and self._remote_extract_thread.is_alive())

    def _remote_state(self) -> dict:
        state = super()._remote_state()
        state.update(
            {
                # Android uses the existing Supabase Realtime row as the canonical
                # activity source. Keeping this false prevents a one-shot command
                # response from leaving the UI stuck on "extracting" after the
                # worker finishes. The PC still checks _extract_running() before
                # accepting another extraction/upload command.
                "extract_running": False,
                "extract_archive": self._remote_extract_archive,
                "extract_target": self._remote_extract_target,
                "extract_output": self._remote_extract_output,
                "extract_error": self._remote_extract_error,
            }
        )
        return state

    @classmethod
    def _validated_archive(cls, raw_path: str) -> Path:
        path = Path(str(raw_path or "")).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError("Arşiv dosyası bulunamadı.")
        if path.suffix.lower() not in _ARCHIVE_SUFFIXES:
            raise RuntimeError("Yalnızca ZIP, RAR ve 7z arşivleri destekleniyor.")
        cls._validated_directory(str(path.parent))
        match = _MULTIPART_RAR.search(path.name)
        if match and int(match.group(1)) != 1:
            raise RuntimeError("Çok parçalı RAR için ilk parçayı (.part1.rar / .part01.rar) seç.")
        return path

    @classmethod
    def _list_directory(cls, raw_path: str) -> dict:
        result = super()._list_directory(raw_path)
        path = cls._validated_directory(raw_path)
        archives: list[dict] = []
        try:
            entries = sorted(path.iterdir(), key=lambda p: p.name.casefold())
        except PermissionError as exc:
            raise RuntimeError("Bu klasöre erişim izni yok.") from exc
        for item in entries:
            if len(archives) >= 160:
                break
            try:
                if not item.is_file() or item.suffix.lower() not in _ARCHIVE_SUFFIXES:
                    continue
                size = int(item.stat().st_size)
            except OSError:
                continue
            match = _MULTIPART_RAR.search(item.name)
            first_part = not match or int(match.group(1)) == 1
            archives.append(
                {
                    "name": item.name,
                    "path": str(item),
                    "size": size,
                    "kind": item.suffix.lower().lstrip("."),
                    "first_part": first_part,
                }
            )
        result["archives"] = archives
        return result

    def _new_extract_publisher(self, title: str) -> LiveStatusPublisher | None:
        publisher = self._new_live_publisher("extract")
        if publisher is None:
            return None
        publisher.set_context(kind="extract", title=title)
        return publisher

    def _start_remote_extract(self, command_id: str, payload: dict) -> None:
        if self._extract_running():
            raise RuntimeError("Zaten aktif bir arşiv çıkarma işlemi var.")
        upload_thread = getattr(self, "thread", None)
        if upload_thread is not None and hasattr(upload_thread, "isRunning") and upload_thread.isRunning():
            raise RuntimeError("Upload devam ederken arşiv çıkarma başlatılamaz.")

        archive = self._validated_archive(str(payload.get("archive") or ""))
        target_raw = str(payload.get("target") or "").strip() or str(archive.parent)
        target = self._validated_directory(target_raw)
        title = str(payload.get("title") or "").strip()
        if not title:
            title = self.game_title.text().strip() or self.prep_title.text().strip() or archive.stem

        self._remote_extract_cancel.clear()
        self._remote_extract_archive = str(archive)
        self._remote_extract_target = str(target)
        self._remote_extract_output = ""
        self._remote_extract_error = ""

        if self._remote_extract_live is not None:
            self._remote_extract_live.close()
        publisher = self._new_extract_publisher(title)
        self._remote_extract_live = publisher

        def telemetry(snapshot: dict) -> None:
            if publisher is not None:
                publisher.update(dict(snapshot), active=True)

        def log(message: str) -> None:
            try:
                self.log(f"[Android Extract] {message}")
            except Exception:
                pass

        def worker() -> None:
            try:
                if publisher is not None:
                    publisher.update(
                        {
                            "phase": "extract",
                            "done": 0,
                            "total": max(1, int(archive.stat().st_size)),
                            "progress": 0.0,
                            "speed": 0.0,
                            "eta": None,
                            "detail": archive.name,
                            "current_item": str(archive),
                        },
                        force=True,
                        active=True,
                    )
                extract_root, _entries = extract_archives(
                    [archive],
                    target,
                    title,
                    telemetry=telemetry,
                    log=log,
                    cancelled=self._remote_extract_cancel.is_set,
                )
                self._remote_extract_output = str(extract_root)
                self._remote_extract_error = ""
                if publisher is not None:
                    publisher.finish(
                        "complete",
                        f"Arşiv çıkarıldı: {extract_root}",
                    )
            except Exception as exc:
                message = str(exc)
                self._remote_extract_error = message
                if publisher is not None:
                    if self._remote_extract_cancel.is_set():
                        publisher.update(
                            {
                                "phase": "cancelled",
                                "done": 0,
                                "total": 1,
                                "progress": 0.0,
                                "speed": 0.0,
                                "eta": None,
                                "detail": "Arşiv çıkarma kullanıcı tarafından iptal edildi",
                            },
                            force=True,
                            active=False,
                        )
                    else:
                        publisher.fail(message)
            finally:
                self._remote_extract_thread = None

        thread = threading.Thread(target=worker, name="drowned-remote-extract", daemon=True)
        self._remote_extract_thread = thread
        thread.start()
        result = self._remote_state()
        result["accepted"] = True
        result["archive"] = str(archive)
        result["target"] = str(target)
        self._remote_complete(command_id, result)

    def _cancel_remote_extract(self, command_id: str) -> None:
        if not self._extract_running():
            result = self._remote_state()
            result["accepted"] = False
            result["message"] = "Aktif arşiv çıkarma işlemi yok."
            self._remote_complete(command_id, result)
            return
        self._remote_extract_cancel.set()
        result = self._remote_state()
        result["accepted"] = True
        result["message"] = "İptal sinyali PC'ye gönderildi."
        self._remote_complete(command_id, result)

    def _handle_remote_command(self, command: dict) -> None:
        command_id = str(command.get("id") or "")
        command_type = str(command.get("command_type") or "")
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        if not command_id:
            return
        try:
            if command_type == "start_extract":
                self._start_remote_extract(command_id, payload)
                return
            if command_type == "cancel_extract":
                self._cancel_remote_extract(command_id)
                return
            if command_type == "start_upload" and self._extract_running():
                raise RuntimeError("Arşiv çıkarma bitmeden upload başlatılamaz.")
        except Exception as exc:
            self._remote_fail(command_id, str(exc))
            return
        super()._handle_remote_command(command)

    def closeEvent(self, event):
        self._remote_extract_cancel.set()
        if self._remote_extract_live is not None:
            self._remote_extract_live.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Drowned Release Manager")
    app.setOrganizationName("Drowned")
    app.setStyle("Fusion")

    style_module = previous
    visited = set()
    while style_module and id(style_module) not in visited:
        visited.add(id(style_module))
        if hasattr(style_module, "MODERN_STYLE"):
            app.setStyleSheet(style_module.MODERN_STYLE)
            break
        style_module = getattr(style_module, "previous", None)

    win = Manager()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
